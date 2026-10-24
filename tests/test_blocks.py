"""Estado dos blocos (GET /analytics/blocks) e a matemática de blocos de 0,5 km."""
from datetime import date

import pytest

from app.services import block_service
from tests.conftest import TODAY, add_event, add_inspection, days_ago

pytestmark = pytest.mark.usefixtures("frozen_clock")


def get_blocks(client, **params):
    response = client.get("/analytics/blocks", params=params)
    assert response.status_code == 200
    return response.json()


def block(blocks, direction, index):
    return next(b for b in blocks if b["direction"] == direction and b["block_index"] == index)


# --- matemática de blocos ---------------------------------------------------

@pytest.mark.parametrize("km, expected", [(11.0, 22), (11.49, 22), (11.5, 23), (0.0, 0), (0.1 + 0.4, 1)])
def test_block_index(km, expected):
    assert block_service.block_index(km) == expected


def test_block_bounds_and_covering():
    assert block_service.block_bounds(22) == (11.0, 11.5)
    assert list(block_service.blocks_covering(10.0, 12.0)) == [20, 21, 22, 23]
    assert list(block_service.blocks_covering(11.0, 11.5)) == [22]  # fim exclusivo
    assert list(block_service.blocks_covering(11.2, 11.2)) == [22]  # ponto (foto) = um bloco
    assert list(block_service.blocks_covering(11.4, 11.6)) == [22, 23]


# --- grade -------------------------------------------------------------------

def test_every_block_of_both_directions_appears_even_if_never_inspected(client, segment):
    blocks = get_blocks(client)

    assert len(blocks) == 8  # 4 blocos (km 10 a 12) x 2 sentidos
    never = block(blocks, "CAPITAL", 20)
    assert never["km_start"] == 10.0 and never["km_end"] == 10.5
    assert never["priority"] is None and never["green_percent"] is None
    assert never["readings_count"] == 0 and never["last_inspection_id"] is None
    assert never["segment_id"] == segment.id


def test_direction_filter_returns_only_that_direction(client, segment):
    blocks = get_blocks(client, direction="INTERIOR")

    assert len(blocks) == 4 and {b["direction"] for b in blocks} == {"INTERIOR"}


# --- leitura de um bloco -----------------------------------------------------

def test_reading_is_the_average_green_and_the_worst_priority_of_the_frames(client, segment, db):
    add_inspection(db, segment, frames=[(10.1, 10.0, "LOW"), (10.3, 20.0, "HIGH")])  # os dois no bloco 20

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["priority"] == "HIGH"
    assert state["green_percent"] == 15.0
    assert state["readings_count"] == 1
    assert state["last_inspected_at"].endswith("Z")


def test_the_most_recent_inspection_defines_the_current_state(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 20.0, "HIGH")])
    newer = add_inspection(db, segment, when=days_ago(2), frames=[(10.1, 5.0, "LOW")])

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["priority"] == "LOW" and state["green_percent"] == 5.0
    assert state["readings_count"] == 2
    assert state["last_inspection_id"] == newer.id


def test_directions_are_independent(client, segment, db):
    add_inspection(db, segment, direction="INTERIOR", frames=[(10.1, 20.0, "HIGH")])

    blocks = get_blocks(client)

    assert block(blocks, "INTERIOR", 20)["priority"] == "HIGH"
    assert block(blocks, "CAPITAL", 20)["priority"] is None


def test_failed_and_directionless_inspections_are_ignored(client, segment, db):
    add_inspection(db, segment, status="FAILED", frames=[(10.1, 20.0, "HIGH")])
    add_inspection(db, segment, direction=None, frames=[(10.1, 20.0, "HIGH")])

    assert block(get_blocks(client), "CAPITAL", 20)["priority"] is None


def test_blocks_outside_the_segments_appear_when_they_have_readings(client, segment, db):
    add_inspection(db, segment, frames=[(12.2, 8.0, "LOW")])  # bloco 24: passa do fim do segmento

    state = block(get_blocks(client), "CAPITAL", 24)

    assert state["priority"] == "LOW" and state["segment_id"] is None


def test_history_is_only_included_on_request(client, segment, db):
    add_inspection(db, segment, when=days_ago(5), frames=[(10.1, 6.0, "LOW")])
    add_inspection(db, segment, when=days_ago(1), frames=[(10.1, 9.0, "LOW")])

    assert block(get_blocks(client), "CAPITAL", 20)["history"] is None
    history = block(get_blocks(client, include="history"), "CAPITAL", 20)["history"]
    assert history == [{"date": "2026-10-15", "green_percent": 6.0}, {"date": "2026-10-19", "green_percent": 9.0}]


def test_state_as_of_ignores_later_readings(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 6.0, "LOW")])
    add_inspection(db, segment, when=days_ago(1), frames=[(10.1, 20.0, "HIGH")])
    target = next(b for b in block_service.load_blocks(db) if b.direction == "CAPITAL" and b.index == 20)

    past = block_service.state_at(target, date(2026, 10, 15))

    assert past.priority == "LOW" and past.readings_count == 1


# --- roçada e agenda ---------------------------------------------------------

def test_last_mowed_at_comes_only_from_completed_mowing_events(client, segment, db):
    add_event(db, segment, type="MOWING", status="DONE", completed_at=days_ago(3), direction=None)
    add_event(db, segment, type="MOWING", status="PLANNED")
    add_event(db, segment, type="INSPECTION", status="DONE", completed_at=days_ago(1))

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["last_mowed_at"].startswith("2026-10-17")


def test_next_scheduled_ignores_canceled_and_picks_the_earliest(client, segment, db):
    add_event(db, segment, scheduled_date=date(2026, 10, 30))
    soon = add_event(db, segment, type="MOWING", scheduled_date=date(2026, 10, 25))
    add_event(db, segment, status="CANCELED", scheduled_date=date(2026, 10, 21))

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["next_scheduled"] == {"id": soon.id, "type": "MOWING", "date": "2026-10-25"}


def test_event_without_direction_applies_to_both_directions(client, segment, db):
    add_event(db, segment, direction=None, km_start=10.0, km_end=10.5)

    blocks = get_blocks(client)

    assert block(blocks, "CAPITAL", 20)["next_scheduled"] is not None
    assert block(blocks, "INTERIOR", 20)["next_scheduled"] is not None
    assert block(blocks, "CAPITAL", 21)["next_scheduled"] is None  # fora do intervalo do evento


# --- crescimento e previsão --------------------------------------------------

def readings(db, segment, points, direction="CAPITAL"):
    """points: (dias atrás, verde %, prioridade) — uma inspeção por ponto, no bloco 20."""
    for days, green, priority in points:
        add_inspection(db, segment, direction=direction, when=days_ago(days), frames=[(10.1, green, priority)])


def test_growth_and_predicted_date_from_a_linear_trend(client, segment, db):
    readings(db, segment, [(14, 6.0, "LOW"), (7, 8.0, "LOW"), (0, 10.0, "LOW")])

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["growth_per_day"] == 0.286  # 2 pontos por semana
    # (13,7 - 10) / 0,286 = 12,9 dias -> arredonda pra cima
    assert state["predicted_critical_date"] == "2026-11-02"


def test_growth_only_uses_readings_after_the_last_mowing(client, segment, db):
    readings(db, segment, [(30, 20.0, "HIGH"), (14, 4.0, "LOW"), (7, 6.0, "LOW"), (0, 8.0, "LOW")])
    add_event(db, segment, type="MOWING", status="DONE", completed_at=days_ago(20), direction=None)

    state = block(get_blocks(client), "CAPITAL", 20)

    # se a leitura de 20 % de antes da roçada entrasse, a reta seria decrescente
    assert state["growth_per_day"] == 0.286


@pytest.mark.parametrize("points", [
    [(7, 6.0, "LOW"), (0, 8.0, "LOW")],                     # só 2 leituras
    [(5, 6.0, "LOW"), (3, 7.0, "LOW"), (0, 8.0, "LOW")],     # 3 leituras, mas só 5 dias de intervalo
])
def test_no_growth_estimate_without_enough_data(client, segment, db, points):
    readings(db, segment, points)

    state = block(get_blocks(client), "CAPITAL", 20)

    assert state["growth_per_day"] is None and state["predicted_critical_date"] is None


def test_critical_blocks_and_falling_trends_have_no_prediction(client, segment, db):
    readings(db, segment, [(14, 6.0, "LOW"), (7, 8.0, "LOW"), (0, 10.0, "HIGH")])  # já está HIGH
    readings(db, segment, [(14, 12.0, "LOW"), (7, 10.0, "LOW"), (0, 8.0, "LOW")], direction="INTERIOR")  # caindo

    blocks = get_blocks(client)

    assert block(blocks, "CAPITAL", 20)["predicted_critical_date"] is None
    assert block(blocks, "INTERIOR", 20)["growth_per_day"] < 0
    assert block(blocks, "INTERIOR", 20)["predicted_critical_date"] is None
