"""Sugestões: cálculo na hora, agrupamento de blocos contíguos, urgência e descartes."""
from datetime import date, datetime, timezone

import pytest

from app.core import clock
from tests.conftest import TODAY, add_event, add_inspection, days_ago

pytestmark = pytest.mark.usefixtures("frozen_clock")

WEDNESDAY = "2026-10-21"  # próximo dia útil depois de terça-feira, 20/10


def suggestions(client, **params):
    response = client.get("/schedule/suggestions", params=params)
    assert response.status_code == 200
    return response.json()


def of_type(items, type_, direction="CAPITAL"):
    return [s for s in items if s["type"] == type_ and s["direction"] == direction]


# --- nunca inspecionado + agrupamento ---------------------------------------

def test_never_inspected_blocks_become_one_suggestion_per_direction(client, segment):
    items = suggestions(client)

    # 8 blocos viram 2 sugestões (uma por sentido), não 8
    assert len(items) == 2
    capital = of_type(items, "INSPECTION")[0]
    assert (capital["km_start"], capital["km_end"]) == (10.0, 12.0)
    assert capital["reason_code"] == "NEVER_INSPECTED"
    assert capital["suggested_date"] == WEDNESDAY
    assert capital["urgency"] == 35
    assert "nunca inspecionado" in capital["reason"] and "4 blocos de 0,5 km" in capital["reason"]
    assert capital["key"] == f"INSPECTION:{segment.road_id}:CAPITAL:10:12"
    assert capital["segment_id"] == segment.id


def test_contiguous_blocks_are_grouped_and_gaps_split_the_runs(client, segment, db):
    add_inspection(db, segment, when=days_ago(1), frames=[(10.6, 6.0, "LOW")])  # bloco 21 (CAPITAL) inspecionado

    capital = of_type(suggestions(client), "INSPECTION")
    ranges = sorted((s["km_start"], s["km_end"]) for s in capital if s["direction"] == "CAPITAL")

    assert ranges == [(10.0, 10.5), (11.0, 12.0)]  # blocos 20 | 22-23
    assert len(of_type(suggestions(client), "INSPECTION", "INTERIOR")) == 1


def test_limit_and_type_filter(client, segment, db):
    add_inspection(db, segment, frames=[(10.1, 20.0, "HIGH")])  # gera também uma sugestão de roçada

    assert len(suggestions(client, limit=1)) == 1
    assert {s["type"] for s in suggestions(client, type="MOWING")} == {"MOWING"}
    assert client.get("/schedule/suggestions", params={"limit": 0}).status_code == 422


def test_suggestions_are_ordered_by_urgency(client, segment, db):
    add_inspection(db, segment, frames=[(10.1, 20.0, "HIGH")])

    items = suggestions(client)

    assert items[0]["reason_code"] == "CRITICAL_NOW"
    assert [s["urgency"] for s in items] == sorted((s["urgency"] for s in items), reverse=True)


def test_date_window_filters_by_suggested_date(client, segment):
    assert suggestions(client, **{"from": "2026-10-22", "to": "2026-10-30"}) == []
    assert len(suggestions(client, **{"from": WEDNESDAY, "to": WEDNESDAY})) == 2


# --- inspeção vencida --------------------------------------------------------

def test_stale_inspection_uses_the_limit_of_the_last_priority(client, segment, db):
    # 20 dias sem inspeção: vence para MEDIUM (limite 15), mas não para LOW (limite 30)
    add_inspection(db, segment, direction="CAPITAL", when=days_ago(20), frames=[(10.1, 9.0, "MEDIUM")] * 1)
    add_inspection(db, segment, direction="INTERIOR", when=days_ago(20), frames=[(10.1, 5.0, "LOW")])

    items = suggestions(client, road_id=segment.road_id)

    stale = [s for s in items if s["reason_code"] == "STALE_INSPECTION"]
    assert [(s["direction"], s["km_start"], s["km_end"]) for s in stale] == [("CAPITAL", 10.0, 10.5)]
    assert stale[0]["urgency"] == 40 + 5 + 5  # base + 5 dias de atraso + peso da prioridade média
    assert "há 20 dias" in stale[0]["reason"] and "prioridade média" in stale[0]["reason"] and "15 dias" in stale[0]["reason"]


# --- roçada ------------------------------------------------------------------

def test_critical_block_suggests_mowing_on_the_next_business_day(client, segment, db):
    add_inspection(db, segment, when=days_ago(3), frames=[(10.1, 20.0, "HIGH")])

    mowing = of_type(suggestions(client), "MOWING")

    assert len(mowing) == 1
    assert mowing[0]["reason_code"] == "CRITICAL_NOW" and mowing[0]["suggested_date"] == WEDNESDAY
    assert mowing[0]["urgency"] == 91  # 90 + 3 dias sem inspeção // 3
    assert "alto" in mowing[0]["reason"] and "17/10/2026" in mowing[0]["reason"]


def test_mowing_skips_days_that_already_have_a_mowing(client, segment, db):
    add_inspection(db, segment, frames=[(10.1, 20.0, "HIGH")])
    add_event(db, segment, type="MOWING", scheduled_date=date(2026, 10, 21), km_start=11.0, km_end=12.0)  # outro trecho

    mowing = of_type(suggestions(client), "MOWING")

    assert mowing[0]["suggested_date"] == "2026-10-22"  # quarta ocupada -> quinta


def test_mowing_skips_the_weekend(client, segment, db, monkeypatch):
    friday = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, "utc_now", lambda: friday)
    add_inspection(db, segment, when=days_ago(0), frames=[(10.1, 20.0, "HIGH")])

    mowing = of_type(suggestions(client), "MOWING")

    assert mowing[0]["suggested_date"] == "2026-10-26"  # segunda-feira


def test_block_already_mowed_after_the_last_reading_is_not_suggested_again(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 20.0, "HIGH")])
    add_event(db, segment, type="MOWING", status="DONE", completed_at=days_ago(5), km_start=10.0, km_end=10.5, direction=None)

    assert of_type(suggestions(client), "MOWING") == []  # a leitura "alta" é anterior à roçada


def test_planned_events_suppress_suggestions_of_the_same_type_only(client, segment, db):
    add_inspection(db, segment, frames=[(10.1, 20.0, "HIGH")])
    add_event(db, segment, type="INSPECTION", km_start=10.0, km_end=12.0)  # inspeção planejada

    items = suggestions(client)

    assert of_type(items, "INSPECTION") == []          # já planejada: não sugere de novo
    assert len(of_type(items, "MOWING")) == 1          # a roçada do bloco crítico continua sugerida


def test_predicted_critical_growth_suggests_mowing_ahead_of_time(client, segment, db):
    for days, green in ((14, 6.0), (7, 8.0), (0, 10.0)):
        add_inspection(db, segment, when=days_ago(days), frames=[(10.1, green, "LOW")])

    mowing = of_type(suggestions(client), "MOWING")

    assert len(mowing) == 1
    assert mowing[0]["reason_code"] == "PREDICTED_CRITICAL"
    # previsto para 02/11 (13 dias); a roçada é sugerida 7 dias antes: 26/10 (segunda-feira)
    assert mowing[0]["suggested_date"] == "2026-10-26"
    assert mowing[0]["urgency"] == 72  # 60 + (25 - 13)
    assert "~13 dias" in mowing[0]["reason"] and "estimativa" in mowing[0]["reason"]
    assert "0,3 pontos" in mowing[0]["reason"]  # vírgula decimal, formato brasileiro


# --- descartes ---------------------------------------------------------------

def test_dismissed_suggestion_disappears_and_comes_back_after_the_date(client, segment, monkeypatch):
    key = suggestions(client)[0]["key"]

    response = client.post("/schedule/suggestions/dismiss", json={"key": key, "until": "2026-10-25"})

    assert response.json() == {"key": key, "until": "2026-10-25"}
    assert key not in [s["key"] for s in suggestions(client)]

    monkeypatch.setattr(clock, "utc_now", lambda: datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc))
    assert key in [s["key"] for s in suggestions(client)]


def test_dismiss_defaults_to_14_days_and_can_be_renewed(client, segment):
    key = suggestions(client)[0]["key"]

    first = client.post("/schedule/suggestions/dismiss", json={"key": key}).json()
    second = client.post("/schedule/suggestions/dismiss", json={"key": key, "until": "2026-12-01"}).json()

    assert first["until"] == "2026-11-03"  # 20/10 + 14 dias
    assert second["until"] == "2026-12-01"


def test_keys_are_stable_between_calls(client, segment):
    assert [s["key"] for s in suggestions(client)] == [s["key"] for s in suggestions(client)]
