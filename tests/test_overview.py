"""Visão geral, série temporal e eficácia da roçada."""
import pytest

from tests.conftest import add_event, add_inspection, days_ago

pytestmark = pytest.mark.usefixtures("frozen_clock")


def overview(client, **params):
    response = client.get("/analytics/overview", params=params)
    assert response.status_code == 200
    return response.json()


# --- visão geral -------------------------------------------------------------

def test_overview_of_a_network_with_no_inspections(client, segment):
    data = overview(client)

    assert data["blocks_total"] == 8
    assert data["blocks_by_priority"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 8}
    assert data["coverage_pct"] == 0.0
    assert data["avg_days_since_inspection"] is None
    assert data["stale_blocks"] == 8  # nunca inspecionado também conta como desatualizado


def test_default_period_is_the_last_30_days_and_the_previous_one_comes_along(client, segment):
    data = overview(client)

    assert data["period"] == {"from": "2026-09-21", "to": "2026-10-20"}
    assert set(data["previous"]) == {
        "blocks_total", "blocks_by_priority", "coverage_pct", "avg_days_since_inspection", "stale_blocks",
    }


def test_current_period_is_compared_with_the_previous_one(client, segment, db):
    add_inspection(db, segment, when=days_ago(5), frames=[(10.1, 20.0, "HIGH")])   # bloco 20, período atual
    add_inspection(db, segment, when=days_ago(40), frames=[(10.6, 6.0, "LOW")])    # bloco 21, período anterior

    data = overview(client)

    # período atual (21/09 a 20/10): só o bloco 20 foi inspecionado dentro dele
    assert data["coverage_pct"] == 12.5
    assert data["blocks_by_priority"] == {"HIGH": 1, "MEDIUM": 0, "LOW": 1, "NONE": 6}
    assert data["avg_days_since_inspection"] == 22.5          # (5 + 40) / 2
    assert data["stale_blocks"] == 7                          # bloco 21 (40 dias) + 6 nunca inspecionados

    # período anterior (22/08 a 20/09): estado até 20/09, só o bloco 21
    previous = data["previous"]
    assert previous["coverage_pct"] == 12.5
    assert previous["blocks_by_priority"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 1, "NONE": 7}
    assert previous["avg_days_since_inspection"] == 10.0      # 20/09 - 10/09
    assert previous["stale_blocks"] == 7                      # os 7 sem leitura até então


def test_overview_filters_by_direction_and_road(client, segment, db):
    add_inspection(db, segment, direction="INTERIOR", when=days_ago(2), frames=[(10.1, 20.0, "HIGH")])

    capital = overview(client, direction="CAPITAL")
    interior = overview(client, direction="INTERIOR", road_id=segment.road_id)

    assert capital["blocks_total"] == 4 and capital["blocks_by_priority"]["HIGH"] == 0
    assert interior["blocks_by_priority"]["HIGH"] == 1


def test_overview_with_explicit_period(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 6.0, "LOW")])

    data = overview(client, **{"from": "2026-10-01", "to": "2026-10-15"})

    assert data["period"] == {"from": "2026-10-01", "to": "2026-10-15"}
    assert data["coverage_pct"] == 12.5  # 1 dos 8 blocos teve leitura dentro do período


def test_overview_rejects_an_inverted_period(client, segment):
    assert client.get("/analytics/overview", params={"from": "2026-10-20", "to": "2026-10-01"}).status_code == 422


# --- série temporal ----------------------------------------------------------

def test_timeseries_has_one_point_per_week_for_the_default_window(client, segment):
    points = client.get("/analytics/timeseries").json()

    assert len(points) == 12
    assert points[-1]["week_start"] == "2026-10-19"  # segunda-feira da semana atual
    assert all(p["inspections"] == 0 and p["avg_green_percent"] is None for p in points)


def test_timeseries_counts_inspections_and_averages_green_per_week(client, segment, db):
    add_inspection(db, segment, when=days_ago(1), frames=[(10.1, 10.0, "LOW"), (10.6, 20.0, "HIGH")])    # semana de 19/10
    add_inspection(db, segment, when=days_ago(0), frames=[(10.1, 30.0, "HIGH")])                         # semana de 19/10
    add_inspection(db, segment, when=days_ago(7), frames=[(10.1, 6.0, "LOW")])                           # semana de 12/10 (terça 13/10)

    points = {p["week_start"]: p for p in client.get("/analytics/timeseries").json()}

    current, earlier = points["2026-10-19"], points["2026-10-12"]
    assert current["inspections"] == 2
    assert current["avg_green_percent"] == 20.0                         # (10 + 20 + 30) / 3 frames
    assert current["by_priority"] == {"HIGH": 2, "MEDIUM": 0, "LOW": 0}  # prioridade é da inspeção (a pior)
    assert earlier["inspections"] == 1 and earlier["by_priority"]["LOW"] == 1


def test_timeseries_only_accepts_weekly_buckets(client, segment):
    assert client.get("/analytics/timeseries", params={"bucket": "month"}).status_code == 422


def test_timeseries_limits_the_number_of_weeks(client, segment):
    response = client.get("/analytics/timeseries", params={"from": "2020-01-01", "to": "2026-10-20"})

    assert response.status_code == 422


# --- eficácia da roçada ------------------------------------------------------

def test_mowing_effectiveness_compares_green_before_and_after(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 12.0, "HIGH")])
    add_inspection(db, segment, when=days_ago(2), frames=[(10.1, 5.0, "LOW")])
    event = add_event(db, segment, type="MOWING", status="DONE", completed_at=days_ago(6), km_start=10.0, km_end=10.5)

    items = client.get("/analytics/mowing-effectiveness").json()

    assert len(items) == 1
    assert items[0]["event_id"] == event.id
    assert items[0]["blocks_compared"] == 1
    assert (items[0]["green_before"], items[0]["green_after"], items[0]["delta"]) == (12.0, 5.0, -7.0)


def test_mowing_effectiveness_needs_readings_on_both_sides(client, segment, db):
    add_inspection(db, segment, when=days_ago(10), frames=[(10.1, 12.0, "HIGH")])  # só antes
    add_event(db, segment, type="MOWING", status="DONE", completed_at=days_ago(6), km_start=10.0, km_end=10.5)
    add_event(db, segment, type="MOWING", status="PLANNED", km_start=10.0, km_end=10.5)  # não concluída

    assert client.get("/analytics/mowing-effectiveness").json() == []
