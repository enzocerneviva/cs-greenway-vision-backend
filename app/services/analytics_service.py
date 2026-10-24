"""
Indicadores agregados (visão geral, série temporal, eficácia da roçada).

Tudo aqui é leitura: calcula a partir dos blocos (block_service) e das linhas de
frames, sem gravar nada.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import STALE_INSPECTION_DAYS
from app.repositories import analytics_repository
from app.services import block_service

MAX_TIMESERIES_WEEKS = 104


# --- visão geral -------------------------------------------------------------

def _metrics(blocks: list[block_service.BlockData], period_from: date, period_to: date) -> dict:
    """Indicadores da malha como ela estava no fim do período."""
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    covered = 0
    stale = 0
    days_since = []

    for block in blocks:
        state = block_service.state_at(block, period_to)
        counts[state.priority or "NONE"] += 1

        # cobertura: o bloco teve alguma leitura DENTRO do período
        if any(period_from <= reading.local_date <= period_to for reading in block.readings):
            covered += 1

        if state.last_inspected_date is None:
            stale += 1  # nunca inspecionado também conta como desatualizado
        else:
            age = (period_to - state.last_inspected_date).days
            days_since.append(age)
            if age > STALE_INSPECTION_DAYS:
                stale += 1

    total = len(blocks)
    return {
        "blocks_total": total,
        "blocks_by_priority": counts,
        "coverage_pct": round(100 * covered / total, 1) if total else 0.0,
        "avg_days_since_inspection": round(sum(days_since) / len(days_since), 1) if days_since else None,
        "stale_blocks": stale,
    }


def overview(
    db: Session,
    road_id: Optional[int] = None,
    direction: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict:
    date_to = date_to or clock.today()
    date_from = date_from or date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="'from' deve ser igual ou antes de 'to'")

    # O "período anterior" tem o mesmo tamanho e termina na véspera do atual.
    length = (date_to - date_from).days + 1
    previous_to = date_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=length - 1)

    blocks = block_service.load_blocks(db, road_id, direction)
    return {
        **_metrics(blocks, date_from, date_to),
        "period": {"from": date_from, "to": date_to},
        "previous": _metrics(blocks, previous_from, previous_to),
    }


# --- série temporal ----------------------------------------------------------

def timeseries(
    db: Session,
    bucket: str = "week",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    road_id: Optional[int] = None,
    direction: Optional[str] = None,
) -> list[dict]:
    if bucket != "week":
        raise HTTPException(status_code=422, detail="Só bucket=week é suportado")

    date_to = date_to or clock.today()
    first_week = clock.start_of_week(date_from) if date_from else clock.start_of_week(date_to) - timedelta(weeks=11)
    last_week = clock.start_of_week(date_to)
    if first_week > last_week:
        raise HTTPException(status_code=422, detail="'from' deve ser igual ou antes de 'to'")
    if (last_week - first_week).days // 7 + 1 > MAX_TIMESERIES_WEEKS:
        raise HTTPException(status_code=422, detail=f"Máximo de {MAX_TIMESERIES_WEEKS} semanas")

    weeks: dict[date, dict] = {}
    week = first_week
    while week <= last_week:
        weeks[week] = {"inspections": set(), "greens": [], "by_priority": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}}
        week += timedelta(weeks=1)

    counted_priority: set[int] = set()
    for row in analytics_repository.list_frame_rows(db, road_id, direction):
        bucket_start = clock.start_of_week(clock.to_local_date(row.analyzed_at or row.created_at))
        data = weeks.get(bucket_start)
        if data is None:
            continue
        data["greens"].append(row.green_percent)
        data["inspections"].add(row.inspection_id)
        if row.inspection_id not in counted_priority:  # a prioridade é da inspeção, conta uma vez
            counted_priority.add(row.inspection_id)
            if row.inspection_priority in data["by_priority"]:
                data["by_priority"][row.inspection_priority] += 1

    return [
        {
            "week_start": week_start,
            "inspections": len(data["inspections"]),
            "avg_green_percent": round(sum(data["greens"]) / len(data["greens"]), 2) if data["greens"] else None,
            "by_priority": data["by_priority"],
        }
        for week_start, data in weeks.items()
    ]


# --- eficácia da roçada ------------------------------------------------------

def mowing_effectiveness(db: Session, road_id: Optional[int] = None, direction: Optional[str] = None) -> list[dict]:
    """
    Para cada roçada concluída: o verde médio dos blocos ANTES (última leitura até
    a conclusão) e DEPOIS (primeira leitura depois dela). Só entram blocos que têm
    as duas leituras.
    """
    pairs: dict[int, dict] = {}
    for block in block_service.load_blocks(db, road_id, direction):
        for event in block.events:
            if event.type != "MOWING" or event.status != "DONE" or event.completed_at is None:
                continue
            before = [r for r in block.readings if r.time <= event.completed_at]
            after = [r for r in block.readings if r.time > event.completed_at]
            if before and after:
                entry = pairs.setdefault(event.id, {"event": event, "before": [], "after": []})
                entry["before"].append(before[-1].green_percent)
                entry["after"].append(after[0].green_percent)

    results = []
    for entry in pairs.values():
        event = entry["event"]
        green_before = sum(entry["before"]) / len(entry["before"])
        green_after = sum(entry["after"]) / len(entry["after"])
        results.append({
            "event_id": event.id,
            "road_id": event.road_id,
            "direction": event.direction,
            "km_start": event.km_start,
            "km_end": event.km_end,
            "completed_at": event.completed_at,
            "blocks_compared": len(entry["before"]),
            "green_before": round(green_before, 2),
            "green_after": round(green_after, 2),
            "delta": round(green_after - green_before, 2),
        })
    return sorted(results, key=lambda item: item["completed_at"])
