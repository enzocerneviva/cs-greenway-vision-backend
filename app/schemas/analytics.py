from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import Direction, Priority, ScheduleType, UtcDatetime


class NextScheduledResponse(BaseModel):
    id: int
    type: ScheduleType
    date: date

    model_config = ConfigDict(from_attributes=True)


class HistoryPointResponse(BaseModel):
    date: date
    green_percent: float

    model_config = ConfigDict(from_attributes=True)


class BlockStateResponse(BaseModel):
    road_id: int
    segment_id: Optional[int]
    direction: Direction
    km_start: float
    km_end: float
    block_index: int
    priority: Optional[Priority]  # null = nunca inspecionado
    green_percent: Optional[float]
    last_inspected_at: Optional[UtcDatetime]
    last_mowed_at: Optional[UtcDatetime]
    growth_per_day: Optional[float]  # pontos percentuais de verde por dia (estimativa)
    predicted_critical_date: Optional[date]  # estimativa grosseira
    next_scheduled: Optional[NextScheduledResponse]
    readings_count: int
    last_inspection_id: Optional[int]
    history: Optional[list[HistoryPointResponse]] = None  # só com ?include=history

    model_config = ConfigDict(from_attributes=True)


class Period(BaseModel):
    from_: date = Field(alias="from")
    to: date

    model_config = ConfigDict(populate_by_name=True)


class PriorityCounts(BaseModel):
    HIGH: int
    MEDIUM: int
    LOW: int
    NONE: int  # nunca inspecionado


class OverviewMetrics(BaseModel):
    blocks_total: int
    blocks_by_priority: PriorityCounts
    coverage_pct: float
    avg_days_since_inspection: Optional[float]
    stale_blocks: int


class OverviewResponse(OverviewMetrics):
    period: Period
    previous: OverviewMetrics  # mesmo tamanho de período, imediatamente antes


class TimeSeriesPoint(BaseModel):
    week_start: date  # segunda-feira
    inspections: int
    avg_green_percent: Optional[float]
    by_priority: dict[str, int]  # contagem de inspeções por prioridade


class MowingEffectivenessItem(BaseModel):
    event_id: int
    road_id: int
    direction: Optional[Direction]
    km_start: float
    km_end: float
    completed_at: UtcDatetime
    blocks_compared: int
    green_before: float
    green_after: float
    delta: float  # depois - antes (negativo = o verde caiu)
