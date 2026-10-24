"""
Agenda: eventos de inspeção e roçada planejados para trechos de rodovia.

Regra de transação (ver app/repositories/__init__.py): os repositories só fazem
flush; cada função pública deste service que altera dados faz UM commit no fim.
As funções com prefixo "_" não fazem commit — são peças reusadas por mais de
um caso de uso (ex.: a conclusão, usada pelo /complete, pelo PATCH e pela
conclusão automática).
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import (
    AUTO_COMPLETE_DAYS_BEFORE,
    AUTO_COMPLETE_MIN_COVERAGE,
    SCHEDULE_MAX_WINDOW_DAYS,
)
from app.models import ScheduleEvent
from app.repositories import (
    analytics_repository,
    frame_analysis_repository,
    inspection_repository,
    road_repository,
    schedule_repository,
    segment_repository,
)
from app.schemas.schedule import ScheduleEventCreate, ScheduleEventUpdate, _check_times
from app.services import block_service

ACTIVE = schedule_repository.ACTIVE_STATUSES

# De qual estado para quais é permitido ir. DONE -> PLANNED (reabrir) só vale
# para o concluído automaticamente; essa checagem extra está em update_event.
ALLOWED_TRANSITIONS = {
    "PLANNED": {"IN_PROGRESS", "DONE", "CANCELED"},
    "IN_PROGRESS": {"PLANNED", "DONE", "CANCELED"},
    "CANCELED": {"PLANNED"},
    "DONE": {"PLANNED"},
}


# --- consulta ----------------------------------------------------------------

def get_event(db: Session, event_id: int) -> ScheduleEvent:
    event = schedule_repository.get_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Schedule event not found")
    return event


def list_events(
    db: Session,
    date_from: date,
    date_to: date,
    type: Optional[str] = None,
    status: Optional[str] = None,
    road_id: Optional[int] = None,
    direction: Optional[str] = None,
) -> list[ScheduleEvent]:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' deve ser igual ou depois de 'from'")
    if (date_to - date_from).days + 1 > SCHEDULE_MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=422, detail=f"A janela máxima é de {SCHEDULE_MAX_WINDOW_DAYS} dias"
        )
    return schedule_repository.list_between(db, date_from, date_to, type, status, road_id, direction)


# --- criação -----------------------------------------------------------------

def _validate_location(db: Session, payload: ScheduleEventCreate) -> None:
    if road_repository.get_by_id(db, payload.road_id) is None:
        raise HTTPException(status_code=404, detail="Road not found")

    segments = analytics_repository.list_segments(db, payload.road_id)
    if payload.segment_id is not None and payload.segment_id not in {s.id for s in segments}:
        raise HTTPException(status_code=422, detail="segment_id não pertence a esta rodovia")

    # O evento precisa TOCAR algum trecho cadastrado (não precisa caber nele: os
    # blocos das pontas passam do limite do segmento).
    wanted = set(block_service.blocks_covering(payload.km_start, payload.km_end))
    touches = any(
        wanted & set(block_service.blocks_covering(s.km_start, s.km_end)) for s in segments
    )
    if not touches:
        raise HTTPException(
            status_code=422, detail="O intervalo de km informado não toca nenhum trecho desta rodovia"
        )


def _check_duplicate(db: Session, payload: ScheduleEventCreate) -> None:
    """Duplicata = mesmo tipo e data, sentido compatível e blocos em comum (entre eventos ativos)."""
    wanted = set(block_service.blocks_covering(payload.km_start, payload.km_end))
    for other in schedule_repository.list_active_on(db, payload.type, payload.scheduled_date, payload.road_id):
        same_direction = other.direction is None or payload.direction is None or other.direction == payload.direction
        if same_direction and wanted & block_service.event_blocks(other):
            raise HTTPException(
                status_code=409,
                detail=f"Já existe um evento igual (id {other.id}) neste dia e trecho. "
                       "Use force=true para criar mesmo assim.",
            )


def create_event(db: Session, payload: ScheduleEventCreate, force: bool = False) -> ScheduleEvent:
    _validate_location(db, payload)
    if not force:
        _check_duplicate(db, payload)

    event = ScheduleEvent(**payload.model_dump(), status="PLANNED")
    schedule_repository.create(db, event)
    db.commit()
    db.refresh(event)
    return event


# --- edição ------------------------------------------------------------------

def update_event(db: Session, event_id: int, payload: ScheduleEventUpdate) -> ScheduleEvent:
    event = get_event(db, event_id)
    changes = payload.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)

    if changes and event.status in ("DONE", "CANCELED"):
        raise HTTPException(
            status_code=409, detail="Evento concluído ou cancelado não pode ser editado (só reaberto, se permitido)"
        )

    start = changes.get("start_time", event.start_time)
    end = changes.get("end_time", event.end_time)
    try:
        _check_times(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    for field_name, value in changes.items():
        setattr(event, field_name, value)

    if new_status and new_status != event.status:
        _change_status(db, event, new_status)

    db.commit()
    db.refresh(event)
    return event


def _change_status(db: Session, event: ScheduleEvent, new_status: str) -> None:
    if new_status not in ALLOWED_TRANSITIONS[event.status]:
        raise HTTPException(status_code=409, detail=f"Transição inválida: {event.status} -> {new_status}")

    if event.status == "DONE":
        # Reabrir: só o que foi concluído automaticamente (a inspeção pode ter sido
        # associada por engano). Um concluído à mão é um registro do usuário.
        if event.completion_source != "AUTO":
            raise HTTPException(status_code=409, detail="Só eventos concluídos automaticamente podem ser reabertos")
        event.status = "PLANNED"
        event.completed_at = None
        event.inspection_id = None
        event.completion_source = None
    elif new_status == "DONE":
        # A MESMA regra de conclusão do POST /{id}/complete.
        _complete(db, event, completed_at=None, inspection_id=None, notes=None, source="MANUAL")
    else:
        event.status = new_status


# --- conclusão ---------------------------------------------------------------

def _complete(
    db: Session,
    event: ScheduleEvent,
    completed_at: Optional[datetime],
    inspection_id: Optional[int],
    notes: Optional[str],
    source: str,
) -> None:
    """Única regra de conclusão (sem commit; quem chama confirma)."""
    if event.status not in ACTIVE:
        raise HTTPException(status_code=409, detail=f"Evento {event.status} não pode ser concluído")

    if inspection_id is not None:
        if event.type != "INSPECTION":
            raise HTTPException(status_code=422, detail="inspection_id só vale para eventos de inspeção")
        inspection = inspection_repository.get_by_id(db, inspection_id)
        if inspection is None:
            raise HTTPException(status_code=422, detail="Inspeção não encontrada")
        segment = segment_repository.get_by_id(db, inspection.video.segment_id)
        if segment.road_id != event.road_id:
            raise HTTPException(status_code=422, detail="A inspeção é de outra rodovia")

    event.status = "DONE"
    event.completed_at = clock.to_naive_utc(completed_at or clock.utc_now())
    event.inspection_id = inspection_id
    event.completion_source = source
    if notes:
        event.notes = f"{event.notes}\n{notes}" if event.notes else notes


def complete_event(
    db: Session,
    event_id: int,
    completed_at: Optional[datetime] = None,
    inspection_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> ScheduleEvent:
    event = get_event(db, event_id)
    _complete(db, event, completed_at, inspection_id, notes, source="MANUAL")
    db.commit()
    db.refresh(event)
    return event


def delete_event(db: Session, event_id: int) -> None:
    schedule_repository.delete(db, get_event(db, event_id))
    db.commit()


# --- resumo ------------------------------------------------------------------

def summary(db: Session, date_from: Optional[date] = None, date_to: Optional[date] = None) -> dict:
    today = clock.today()
    if date_from is None or date_to is None:
        date_from = clock.start_of_week(today)
        date_to = date_from + timedelta(days=6)

    states = block_service.get_block_states(db, today)
    next_mowing = schedule_repository.next_mowing(db, today)
    return {
        "planned_this_week": schedule_repository.count_active_between(db, date_from, date_to),
        "overdue": schedule_repository.count_overdue(db, today),
        # bloco crítico (última leitura HIGH) sem nenhum evento planejado
        "critical_unscheduled": sum(1 for s in states if s.priority == "HIGH" and s.next_scheduled is None),
        "next_mowing": (
            {"id": next_mowing.id, "scheduled_date": next_mowing.scheduled_date, "road_id": next_mowing.road_id}
            if next_mowing else None
        ),
    }


# --- conclusão automática ----------------------------------------------------

def auto_complete_for_inspection(db: Session, inspection_id: int) -> list[ScheduleEvent]:
    """
    Chamada ao fim de uma análise bem-sucedida. Conclui sozinho os eventos de
    INSPEÇÃO planejados que esta inspeção cobre, se as três condições valerem:
      1. mesmo sentido (evento com direction nulo fica manual);
      2. a inspeção cobre pelo menos AUTO_COMPLETE_MIN_COVERAGE dos blocos do evento;
      3. foi feita até AUTO_COMPLETE_DAYS_BEFORE dias antes da data agendada, ou depois.
    Roçada nunca é concluída automaticamente. Não faz commit (quem chama confirma).
    """
    inspection = inspection_repository.get_by_id(db, inspection_id)
    if inspection is None or inspection.status != "DONE" or inspection.direction is None:
        return []

    segment = segment_repository.get_by_id(db, inspection.video.segment_id)
    inspection_blocks = {
        block_service.block_index(frame.estimated_km)
        for frame in frame_analysis_repository.list_by_inspection(db, inspection_id)
    }
    finished_at = inspection.analyzed_at or inspection.created_at
    inspection_date = clock.to_local_date(finished_at)

    completed = []
    for event in schedule_repository.list_planned_inspections(db, segment.road_id, inspection.direction):
        event_blocks = block_service.event_blocks(event)
        coverage = len(event_blocks & inspection_blocks) / len(event_blocks)
        too_early = inspection_date < event.scheduled_date - timedelta(days=AUTO_COMPLETE_DAYS_BEFORE)
        if coverage >= AUTO_COMPLETE_MIN_COVERAGE and not too_early:
            _complete(
                db, event, completed_at=finished_at, inspection_id=inspection_id,
                notes=None, source="AUTO",
            )
            completed.append(event)
    return completed
