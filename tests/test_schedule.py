"""Agenda: CRUD, validações, transições de estado, conclusão e resumo."""
from datetime import date

import pytest

from app.models import Road, Segment
from tests.conftest import TODAY, add_event, add_inspection, days_ago, event_payload

pytestmark = pytest.mark.usefixtures("frozen_clock")


def create(client, segment, **overrides):
    return client.post("/schedule", json=event_payload(segment, **overrides))


def window(client, start="2026-10-01", end="2026-10-31", **params):
    return client.get("/schedule", params={"from": start, "to": end, **params})


@pytest.fixture
def other_road_segment(db):
    road = Road(name="SP-111 (Outra)")
    db.add(road)
    db.commit()
    seg = Segment(road_id=road.id, km_start=0.0, km_end=5.0)
    db.add(seg)
    db.commit()
    return seg


# --- criação -----------------------------------------------------------------

def test_create_returns_201_with_the_full_contract(client, segment):
    response = create(client, segment, start_time="08:00", end_time="10:30", assignee="Ana", notes="x")

    assert response.status_code == 201
    event = response.json()
    assert event["status"] == "PLANNED" and event["source"] == "MANUAL"
    assert event["start_time"] == "08:00" and event["assignee"] == "Ana"
    assert event["scheduled_date"] == "2026-10-22"
    assert event["is_overdue"] is False
    assert event["completed_at"] is None and event["inspection_id"] is None
    assert event["created_at"].endswith("Z") and event["updated_at"].endswith("Z")


@pytest.mark.parametrize("overrides", [
    {"km_start": 11.0, "km_end": 11.0},                   # início = fim
    {"km_start": 12.0, "km_end": 11.0},                   # início depois do fim
    {"start_time": "10:00", "end_time": "09:00"},          # fim antes do início
    {"start_time": "25:00"},                               # hora inválida
    {"start_time": "8:00"},                                # sem zero à esquerda
    {"type": "PAINTING"},                                  # tipo desconhecido
    {"direction": "NORTE"},                                # sentido desconhecido
    {"scheduled_date": "22/10/2026"},                      # data fora do formato
])
def test_invalid_payload_is_rejected_with_422(client, segment, overrides):
    assert create(client, segment, **overrides).status_code == 422


def test_unknown_road_returns_404(client, segment):
    assert create(client, segment, road_id=9999).status_code == 404


def test_segment_of_another_road_is_rejected(client, segment, other_road_segment):
    assert create(client, segment, segment_id=other_road_segment.id).status_code == 422


def test_interval_must_touch_a_segment_of_the_road(client, segment):
    response = create(client, segment, km_start=50.0, km_end=51.0)

    assert response.status_code == 422 and "toca" in response.json()["detail"]


def test_interval_that_only_partially_overlaps_a_segment_is_accepted(client, segment):
    # o segmento vai até km 12; o evento passa do limite (os blocos das pontas passam)
    assert create(client, segment, km_start=11.8, km_end=12.4).status_code == 201


# --- duplicata ---------------------------------------------------------------

def test_duplicate_returns_409_unless_forced(client, segment):
    create(client, segment)

    again = create(client, segment, km_start=10.5, km_end=11.5)  # mesmo dia/tipo, km sobreposto

    assert again.status_code == 409
    assert client.post("/schedule?force=true", json=event_payload(segment, km_start=10.5, km_end=11.5)).status_code == 201


@pytest.mark.parametrize("overrides", [
    {"km_start": 11.0, "km_end": 12.0},          # km sem sobreposição (11.0 já é outro bloco)
    {"direction": "INTERIOR"},                   # outro sentido
    {"scheduled_date": "2026-10-23"},            # outro dia
    {"type": "MOWING"},                          # outro tipo
])
def test_events_that_differ_are_not_duplicates(client, segment, overrides):
    create(client, segment)

    assert create(client, segment, **overrides).status_code == 201


def test_event_without_direction_conflicts_with_any_direction(client, segment):
    create(client, segment, direction=None)

    assert create(client, segment, direction="CAPITAL").status_code == 409


def test_canceled_events_do_not_count_as_duplicates(client, segment):
    first = create(client, segment).json()
    client.patch(f"/schedule/{first['id']}", json={"status": "CANCELED"})

    assert create(client, segment).status_code == 201


# --- listagem ----------------------------------------------------------------

def test_list_requires_from_and_to(client, segment):
    assert client.get("/schedule").status_code == 422


def test_list_rejects_windows_larger_than_93_days(client, segment):
    assert window(client, "2026-01-01", "2026-04-30").status_code == 422
    assert window(client, "2026-01-01", "2026-04-03").status_code == 200  # exatamente 93 dias


def test_list_rejects_inverted_window(client, segment):
    assert window(client, "2026-10-31", "2026-10-01").status_code == 422


def test_list_filters_and_ordering(client, segment, db, other_road_segment):
    add_event(db, segment, scheduled_date=date(2026, 10, 25), start_time="14:00")
    add_event(db, segment, scheduled_date=date(2026, 10, 25), start_time="08:00", direction="INTERIOR")
    add_event(db, segment, type="MOWING", scheduled_date=date(2026, 10, 22), direction=None)
    add_event(db, other_road_segment, scheduled_date=date(2026, 10, 23), km_start=0, km_end=1)
    add_event(db, segment, scheduled_date=date(2026, 11, 20))  # fora da janela

    everything = window(client).json()
    assert [e["scheduled_date"] for e in everything] == ["2026-10-22", "2026-10-23", "2026-10-25", "2026-10-25"]
    assert [e["start_time"] for e in everything[2:]] == ["08:00", "14:00"]  # mesmo dia: por horário

    assert len(window(client, type="MOWING").json()) == 1
    assert len(window(client, road_id=segment.road_id).json()) == 3
    # filtro de sentido inclui o evento sem sentido (vale para os dois)
    assert len(window(client, road_id=segment.road_id, direction="INTERIOR").json()) == 2


# --- detalhe, edição, remoção -----------------------------------------------

def test_get_and_delete(client, segment):
    event_id = create(client, segment).json()["id"]

    assert client.get(f"/schedule/{event_id}").json()["id"] == event_id
    assert client.delete(f"/schedule/{event_id}").status_code == 204
    assert client.get(f"/schedule/{event_id}").status_code == 404
    assert client.delete(f"/schedule/{event_id}").status_code == 404


def test_patch_updates_only_the_given_fields(client, segment):
    event = create(client, segment, assignee="Ana", start_time="08:00", end_time="09:00").json()

    response = client.patch(f"/schedule/{event['id']}", json={"scheduled_date": "2026-10-28", "notes": "trocou"})

    updated = response.json()
    assert updated["scheduled_date"] == "2026-10-28" and updated["notes"] == "trocou"
    assert updated["assignee"] == "Ana" and updated["start_time"] == "08:00"  # intactos


def test_patch_can_clear_a_field_with_null(client, segment):
    event = create(client, segment, assignee="Ana").json()

    assert client.patch(f"/schedule/{event['id']}", json={"assignee": None}).json()["assignee"] is None


def test_patch_rejects_fields_that_are_not_editable(client, segment):
    event_id = create(client, segment).json()["id"]

    assert client.patch(f"/schedule/{event_id}", json={"km_start": 1.0}).status_code == 422
    assert client.patch(f"/schedule/{event_id}", json={"type": "MOWING"}).status_code == 422


def test_patch_validates_times_against_the_stored_values(client, segment):
    event_id = create(client, segment, start_time="08:00", end_time="09:00").json()["id"]

    assert client.patch(f"/schedule/{event_id}", json={"end_time": "07:00"}).status_code == 422


def test_status_transitions(client, segment):
    event_id = create(client, segment).json()["id"]
    patch = lambda status: client.patch(f"/schedule/{event_id}", json={"status": status})  # noqa: E731

    assert patch("IN_PROGRESS").json()["status"] == "IN_PROGRESS"
    assert patch("PLANNED").json()["status"] == "PLANNED"
    assert patch("CANCELED").json()["status"] == "CANCELED"
    assert patch("IN_PROGRESS").status_code == 409  # cancelado só volta a PLANNED
    assert patch("PLANNED").json()["status"] == "PLANNED"


def test_patch_with_status_done_completes_like_the_complete_route(client, segment):
    event_id = create(client, segment).json()["id"]

    done = client.patch(f"/schedule/{event_id}", json={"status": "DONE"}).json()

    assert done["status"] == "DONE" and done["completion_source"] == "MANUAL"
    assert done["completed_at"] == "2026-10-20T15:00:00Z"


def test_done_events_are_immutable(client, segment):
    event_id = create(client, segment).json()["id"]
    client.post(f"/schedule/{event_id}/complete", json={})

    assert client.patch(f"/schedule/{event_id}", json={"notes": "x"}).status_code == 409
    assert client.patch(f"/schedule/{event_id}", json={"status": "PLANNED"}).status_code == 409  # concluído à mão


# --- conclusão ---------------------------------------------------------------

def test_complete_defaults_to_now_and_appends_notes(client, segment):
    event_id = create(client, segment, notes="antes").json()["id"]

    done = client.post(f"/schedule/{event_id}/complete", json={"notes": "feito"}).json()

    assert done["status"] == "DONE" and done["completed_at"] == "2026-10-20T15:00:00Z"
    assert done["notes"] == "antes\nfeito"


def test_complete_accepts_an_explicit_instant(client, segment):
    event_id = create(client, segment).json()["id"]

    done = client.post(f"/schedule/{event_id}/complete", json={"completed_at": "2026-10-19T12:30:00Z"}).json()

    assert done["completed_at"] == "2026-10-19T12:30:00Z"


def test_complete_links_an_inspection_of_the_same_road(client, segment, db):
    inspection = add_inspection(db, segment)
    event_id = create(client, segment).json()["id"]

    done = client.post(f"/schedule/{event_id}/complete", json={"inspection_id": inspection.id}).json()

    assert done["inspection_id"] == inspection.id


def test_complete_rejects_invalid_inspection_links(client, segment, db, other_road_segment):
    foreign = add_inspection(db, other_road_segment, frames=[(0.1, 5.0, "LOW")])
    inspection_event = create(client, segment).json()["id"]
    mowing_event = create(client, segment, type="MOWING").json()["id"]
    own = add_inspection(db, segment)

    assert client.post(f"/schedule/{inspection_event}/complete", json={"inspection_id": 9999}).status_code == 422
    assert client.post(f"/schedule/{inspection_event}/complete", json={"inspection_id": foreign.id}).status_code == 422
    assert client.post(f"/schedule/{mowing_event}/complete", json={"inspection_id": own.id}).status_code == 422


def test_complete_twice_returns_409(client, segment):
    event_id = create(client, segment).json()["id"]
    client.post(f"/schedule/{event_id}/complete", json={})

    assert client.post(f"/schedule/{event_id}/complete", json={}).status_code == 409


def test_canceled_event_cannot_be_completed(client, segment):
    event_id = create(client, segment).json()["id"]
    client.patch(f"/schedule/{event_id}", json={"status": "CANCELED"})

    assert client.post(f"/schedule/{event_id}/complete", json={}).status_code == 409


# --- atraso e resumo ---------------------------------------------------------

def test_is_overdue_only_for_planned_events_in_the_past(client, segment, db):
    add_event(db, segment, scheduled_date=date(2026, 10, 19))                            # ontem, PLANNED
    add_event(db, segment, scheduled_date=date(2026, 10, 19), status="IN_PROGRESS", direction="INTERIOR")
    add_event(db, segment, scheduled_date=TODAY, direction=None, km_start=11, km_end=12)  # hoje: não atrasa

    overdue = {e["id"]: e["is_overdue"] for e in window(client).json()}

    assert sorted(overdue.values()) == [False, False, True]


def test_summary_counts(client, segment, db):
    add_event(db, segment, scheduled_date=date(2026, 10, 19), km_start=10.0, km_end=10.5)  # atrasado (semana atual), só o bloco 20
    add_event(db, segment, type="MOWING", scheduled_date=date(2026, 10, 23), direction="INTERIOR")
    add_event(db, segment, scheduled_date=date(2026, 10, 29), direction=None, km_start=11, km_end=12)  # próxima semana
    add_event(db, segment, type="MOWING", scheduled_date=date(2026, 11, 3), direction=None, km_start=11, km_end=12)
    add_inspection(db, segment, frames=[(10.1, 20.0, "HIGH"), (10.6, 20.0, "HIGH")])  # blocos 20 e 21 CAPITAL: HIGH
    # o bloco 20 (CAPITAL) tem o evento atrasado planejado; o 21 não tem nada

    summary = client.get("/schedule/summary").json()

    assert summary["planned_this_week"] == 2          # seg 19/10 e sex 23/10
    assert summary["overdue"] == 1
    assert summary["critical_unscheduled"] == 1        # só o bloco 21 está crítico sem evento
    assert summary["next_mowing"]["scheduled_date"] == "2026-10-23"


def test_summary_with_nothing_scheduled(client, segment):
    assert client.get("/schedule/summary").json() == {
        "planned_this_week": 0, "overdue": 0, "critical_unscheduled": 0, "next_mowing": None,
    }


def test_fixed_routes_are_not_swallowed_by_the_id_route(client, segment):
    # se /{event_id} viesse antes de /summary, "summary" daria 422 (não é um inteiro)
    assert client.get("/schedule/summary").status_code == 200
    assert client.get("/schedule/suggestions").status_code == 200
