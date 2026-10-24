"""Conclusão automática de eventos de inspeção, ao fim da análise."""
from datetime import date

import pytest

from app.services import schedule_service
from app.vision.analysis_result import AnalysisError
from tests.conftest import TODAY, add_event, post_upload

pytestmark = pytest.mark.usefixtures("frozen_clock")


def upload(client, segment, km_start="10", km_end="12", direction="CAPITAL"):
    """Envia uma inspeção (o engine falso devolve 4 frames) e espera a análise terminar."""
    response = post_upload(client, segment.id, km_start=km_start, km_end=km_end, direction=direction)
    assert response.status_code == 202
    return response.json()["id"]


def event(client, event_id):
    return client.get(f"/schedule/{event_id}").json()


def test_inspection_covering_the_event_completes_it_automatically(client, segment, db, fake_engine):
    planned = add_event(db, segment)  # CAPITAL, km 10-12, hoje

    inspection_id = upload(client, segment)  # frames em km 10, 10.5, 11, 11.5: blocos 20 a 23

    done = event(client, planned.id)
    assert done["status"] == "DONE"
    assert done["completion_source"] == "AUTO"
    assert done["inspection_id"] == inspection_id
    assert done["completed_at"] == "2026-10-20T15:00:00Z"


def test_an_automatically_completed_event_can_be_reopened(client, segment, db, fake_engine):
    planned = add_event(db, segment)
    upload(client, segment)

    reopened = client.patch(f"/schedule/{planned.id}", json={"status": "PLANNED"}).json()

    assert reopened["status"] == "PLANNED"
    assert reopened["inspection_id"] is None and reopened["completed_at"] is None
    assert reopened["completion_source"] is None


def test_coverage_below_80_percent_does_not_complete(client, segment, db, fake_engine):
    planned = add_event(db, segment)  # 4 blocos

    upload(client, segment, km_start="10", km_end="10.9")  # frames só nos blocos 20 e 21 (50 %)

    assert event(client, planned.id)["status"] == "PLANNED"


def test_exactly_80_percent_coverage_completes(client, segment, db, fake_engine):
    planned = add_event(db, segment, km_start=10.0, km_end=12.5)  # 5 blocos; a inspeção cobre 4

    upload(client, segment)

    assert event(client, planned.id)["status"] == "DONE"


@pytest.mark.parametrize("event_kwargs", [
    {"direction": "INTERIOR"},       # outro sentido
    {"direction": None},             # evento sem sentido fica manual
    {"type": "MOWING"},              # roçada nunca é concluída automaticamente
    {"status": "IN_PROGRESS"},       # só PLANNED
    {"status": "CANCELED"},
])
def test_events_that_do_not_qualify_are_left_alone(client, segment, db, fake_engine, event_kwargs):
    planned = add_event(db, segment, **event_kwargs)

    upload(client, segment)

    assert event(client, planned.id)["status"] == event_kwargs.get("status", "PLANNED")


def test_inspection_must_not_be_too_early_for_the_scheduled_date(client, segment, db, fake_engine):
    on_the_limit = add_event(db, segment, scheduled_date=date(2026, 10, 23), km_start=10.0, km_end=10.5)  # 3 dias depois
    too_early = add_event(db, segment, scheduled_date=date(2026, 10, 24), km_start=10.0, km_end=10.5)     # 4 dias depois

    upload(client, segment)

    assert event(client, on_the_limit.id)["status"] == "DONE"
    assert event(client, too_early.id)["status"] == "PLANNED"


def test_inspection_after_the_scheduled_date_still_completes(client, segment, db, fake_engine):
    late = add_event(db, segment, scheduled_date=date(2026, 10, 1))

    upload(client, segment)

    assert event(client, late.id)["status"] == "DONE"


def test_failed_inspection_completes_nothing(client, segment, db, fake_engine):
    planned = add_event(db, segment)
    fake_engine.result = AnalysisError("arquivo corrompido")

    upload(client, segment)

    assert event(client, planned.id)["status"] == "PLANNED"


def test_a_failure_in_the_auto_complete_step_does_not_fail_the_analysis(client, segment, db, fake_engine, monkeypatch):
    planned = add_event(db, segment)

    def boom(db_, inspection_id):
        raise RuntimeError("falha na agenda")

    monkeypatch.setattr(schedule_service, "auto_complete_for_inspection", boom)

    inspection_id = upload(client, segment)

    assert client.get(f"/inspections/{inspection_id}").json()["status"] == "DONE"  # a análise ficou
    assert event(client, planned.id)["status"] == "PLANNED"


def test_reset_detaches_inspections_from_events(client, segment, db, fake_engine):
    automatic = add_event(db, segment, km_start=10.0, km_end=10.5)
    manual = add_event(db, segment, direction=None, km_start=11.0, km_end=11.5)  # sem sentido: só conclui à mão
    inspection_id = upload(client, segment)
    assert event(client, automatic.id)["status"] == "DONE"
    assert client.post(f"/schedule/{manual.id}/complete", json={"inspection_id": inspection_id}).status_code == 200

    assert client.delete("/inspections").status_code == 204

    # concluído automaticamente volta a PLANNED (a inspeção que o concluiu sumiu)
    back = event(client, automatic.id)
    assert back["status"] == "PLANNED" and back["inspection_id"] is None
    # concluído à mão continua concluído, só perde o vínculo
    kept = event(client, manual.id)
    assert kept["status"] == "DONE" and kept["inspection_id"] is None
