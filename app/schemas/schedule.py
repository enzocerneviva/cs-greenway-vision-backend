from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.types import (
    CompletionSource,
    Direction,
    EventSource,
    ScheduleStatus,
    ScheduleType,
    SuggestionReason,
    UtcDatetime,
)

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"  # "HH:MM"


def _check_times(start_time: Optional[str], end_time: Optional[str]) -> None:
    # "HH:MM" com zero à esquerda compara corretamente como texto.
    if start_time and end_time and end_time <= start_time:
        raise ValueError("end_time deve ser depois de start_time")


class ScheduleEventCreate(BaseModel):
    type: ScheduleType
    road_id: int
    segment_id: Optional[int] = None
    direction: Optional[Direction] = None  # null = os dois sentidos
    km_start: float
    km_end: float
    scheduled_date: date  # YYYY-MM-DD
    start_time: Optional[str] = Field(None, pattern=TIME_PATTERN)
    end_time: Optional[str] = Field(None, pattern=TIME_PATTERN)
    assignee: Optional[str] = None
    notes: Optional[str] = None
    source: EventSource = "MANUAL"

    @model_validator(mode="after")
    def _validate(self):
        if self.km_start >= self.km_end:
            raise ValueError("km_start deve ser menor que km_end")
        _check_times(self.start_time, self.end_time)
        return self


class ScheduleEventUpdate(BaseModel):
    """Edição parcial: só o que vier no corpo muda. Tipo, rodovia e km não são editáveis."""

    model_config = ConfigDict(extra="forbid")

    scheduled_date: Optional[date] = None
    start_time: Optional[str] = Field(None, pattern=TIME_PATTERN)
    end_time: Optional[str] = Field(None, pattern=TIME_PATTERN)
    assignee: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[ScheduleStatus] = None


class ScheduleEventResponse(BaseModel):
    id: int
    type: ScheduleType
    status: ScheduleStatus
    road_id: int
    segment_id: Optional[int]
    direction: Optional[Direction]
    km_start: float
    km_end: float
    scheduled_date: date
    start_time: Optional[str]
    end_time: Optional[str]
    assignee: Optional[str]
    notes: Optional[str]
    source: EventSource
    completed_at: Optional[UtcDatetime]
    inspection_id: Optional[int]
    completion_source: Optional[CompletionSource]
    is_overdue: bool
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)


class CompleteRequest(BaseModel):
    completed_at: Optional[datetime] = None  # padrão: agora
    inspection_id: Optional[int] = None  # só para eventos de inspeção
    notes: Optional[str] = None


class NextMowing(BaseModel):
    id: int
    scheduled_date: date
    road_id: int


class ScheduleSummaryResponse(BaseModel):
    planned_this_week: int
    overdue: int
    critical_unscheduled: int
    next_mowing: Optional[NextMowing]


class ScheduleSuggestionResponse(BaseModel):
    key: str
    type: ScheduleType
    road_id: int
    segment_id: Optional[int]
    direction: Direction
    km_start: float
    km_end: float
    suggested_date: date
    urgency: int  # 0 a 100
    reason_code: SuggestionReason
    reason: str  # texto pronto em pt-BR

    model_config = ConfigDict(from_attributes=True)


class DismissRequest(BaseModel):
    key: str
    until: Optional[date] = None  # padrão: hoje + DISMISS_DEFAULT_DAYS


class DismissResponse(BaseModel):
    key: str
    until: date

    model_config = ConfigDict(from_attributes=True)
