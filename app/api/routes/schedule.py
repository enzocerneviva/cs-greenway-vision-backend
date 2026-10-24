from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.schedule import (
    CompleteRequest,
    DismissRequest,
    DismissResponse,
    ScheduleEventCreate,
    ScheduleEventResponse,
    ScheduleEventUpdate,
    ScheduleSuggestionResponse,
    ScheduleSummaryResponse,
)
from app.schemas.types import Direction, ScheduleStatus, ScheduleType
from app.services import schedule_service, suggestion_service

router = APIRouter(prefix="/schedule", tags=["schedule"])

# ATENÇÃO À ORDEM: as rotas fixas ("/summary", "/suggestions") vêm ANTES de
# "/{event_id}". O FastAPI testa as rotas na ordem em que foram declaradas; se
# "/{event_id}" viesse primeiro, "summary" seria lido como um id (e daria 422).


@router.get("", response_model=List[ScheduleEventResponse])
def list_events(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    type: Optional[ScheduleType] = None,
    status: Optional[ScheduleStatus] = None,
    road_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    db: Session = Depends(get_db),
):
    """Eventos do período (`from` e `to` obrigatórios, janela máxima de 93 dias)."""
    return schedule_service.list_events(db, date_from, date_to, type, status, road_id, direction)


@router.post("", response_model=ScheduleEventResponse, status_code=201)
def create_event(payload: ScheduleEventCreate, force: bool = False, db: Session = Depends(get_db)):
    """409 se já existe um evento igual (mesmo tipo, data, sentido e trecho); `?force=true` cria mesmo assim."""
    return schedule_service.create_event(db, payload, force=force)


@router.get("/summary", response_model=ScheduleSummaryResponse)
def get_summary(
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """Números do topo da tela. Sem `from`/`to`, "esta semana" é a semana atual (segunda a domingo)."""
    return schedule_service.summary(db, date_from, date_to)


@router.get("/suggestions", response_model=List[ScheduleSuggestionResponse])
def get_suggestions(
    type: Optional[ScheduleType] = None,
    road_id: Optional[int] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    limit: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """Poucas sugestões, as mais urgentes primeiro; blocos contíguos vêm agrupados num intervalo."""
    return suggestion_service.get_suggestions(db, type, road_id, date_from, date_to, limit)


@router.post("/suggestions/dismiss", response_model=DismissResponse)
def dismiss_suggestion(payload: DismissRequest, db: Session = Depends(get_db)):
    """Esconde uma sugestão até `until` (padrão: 14 dias)."""
    return suggestion_service.dismiss(db, payload.key, payload.until)


@router.get("/{event_id}", response_model=ScheduleEventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return schedule_service.get_event(db, event_id)


@router.patch("/{event_id}", response_model=ScheduleEventResponse)
def update_event(event_id: int, payload: ScheduleEventUpdate, db: Session = Depends(get_db)):
    """Edição parcial (data, horários, responsável, observação, status). `status=DONE` conclui, como /complete."""
    return schedule_service.update_event(db, event_id, payload)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    schedule_service.delete_event(db, event_id)
    return Response(status_code=204)


@router.post("/{event_id}/complete", response_model=ScheduleEventResponse)
def complete_event(event_id: int, payload: CompleteRequest, db: Session = Depends(get_db)):
    return schedule_service.complete_event(
        db, event_id, payload.completed_at, payload.inspection_id, payload.notes
    )
