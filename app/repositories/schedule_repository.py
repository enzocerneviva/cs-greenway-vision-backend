from datetime import date
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import ScheduleEvent

# Eventos que ainda "valem" no calendário (ainda não concluídos nem cancelados).
ACTIVE_STATUSES = ("PLANNED", "IN_PROGRESS")


def create(db: Session, event: ScheduleEvent) -> ScheduleEvent:
    db.add(event)
    db.flush()
    return event


def get_by_id(db: Session, event_id: int) -> Optional[ScheduleEvent]:
    return db.get(ScheduleEvent, event_id)


def delete(db: Session, event: ScheduleEvent) -> None:
    db.delete(event)
    db.flush()


def list_between(
    db: Session,
    date_from: date,
    date_to: date,
    type: Optional[str] = None,
    status: Optional[str] = None,
    road_id: Optional[int] = None,
    direction: Optional[str] = None,
) -> List[ScheduleEvent]:
    query = db.query(ScheduleEvent).filter(
        ScheduleEvent.scheduled_date >= date_from, ScheduleEvent.scheduled_date <= date_to
    )
    if type:
        query = query.filter(ScheduleEvent.type == type)
    if status:
        query = query.filter(ScheduleEvent.status == status)
    if road_id is not None:
        query = query.filter(ScheduleEvent.road_id == road_id)
    if direction:
        # evento sem sentido (null) vale para os dois
        query = query.filter(or_(ScheduleEvent.direction == direction, ScheduleEvent.direction.is_(None)))
    return query.order_by(ScheduleEvent.scheduled_date, ScheduleEvent.start_time, ScheduleEvent.id).all()


def list_not_canceled(db: Session, road_id: Optional[int] = None) -> List[ScheduleEvent]:
    """Base do cálculo de blocos: eventos que importam (planejados, em andamento e concluídos)."""
    query = db.query(ScheduleEvent).filter(ScheduleEvent.status != "CANCELED")
    if road_id is not None:
        query = query.filter(ScheduleEvent.road_id == road_id)
    return query.all()


def list_active_on(db: Session, type: str, scheduled_date: date, road_id: int) -> List[ScheduleEvent]:
    return (
        db.query(ScheduleEvent)
        .filter(
            ScheduleEvent.type == type,
            ScheduleEvent.scheduled_date == scheduled_date,
            ScheduleEvent.road_id == road_id,
            ScheduleEvent.status.in_(ACTIVE_STATUSES),
        )
        .all()
    )


def list_planned_inspections(db: Session, road_id: int, direction: str) -> List[ScheduleEvent]:
    return (
        db.query(ScheduleEvent)
        .filter(
            ScheduleEvent.type == "INSPECTION",
            ScheduleEvent.status == "PLANNED",
            ScheduleEvent.road_id == road_id,
            ScheduleEvent.direction == direction,
        )
        .all()
    )


def count_active_between(db: Session, date_from: date, date_to: date) -> int:
    return (
        db.query(ScheduleEvent)
        .filter(
            ScheduleEvent.status.in_(ACTIVE_STATUSES),
            ScheduleEvent.scheduled_date >= date_from,
            ScheduleEvent.scheduled_date <= date_to,
        )
        .count()
    )


def count_overdue(db: Session, today: date) -> int:
    return (
        db.query(ScheduleEvent)
        .filter(ScheduleEvent.status == "PLANNED", ScheduleEvent.scheduled_date < today)
        .count()
    )


def next_mowing(db: Session, today: date) -> Optional[ScheduleEvent]:
    return (
        db.query(ScheduleEvent)
        .filter(
            ScheduleEvent.type == "MOWING",
            ScheduleEvent.status.in_(ACTIVE_STATUSES),
            ScheduleEvent.scheduled_date >= today,
        )
        .order_by(ScheduleEvent.scheduled_date, ScheduleEvent.id)
        .first()
    )


def detach_inspections(db: Session) -> None:
    """
    Usado quando todas as inspeções são apagadas (reset): nenhum evento pode
    continuar apontando para uma inspeção que não existe mais. Os concluídos
    automaticamente voltam a PLANNED (a inspeção que os concluiu sumiu); os
    concluídos à mão continuam concluídos, só perdem o vínculo.
    """
    for event in db.query(ScheduleEvent).filter(ScheduleEvent.inspection_id.isnot(None)).all():
        if event.completion_source == "AUTO":
            event.status = "PLANNED"
            event.completed_at = None
            event.completion_source = None
        event.inspection_id = None
    db.flush()
