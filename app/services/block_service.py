"""
Blocos de rodovia e o estado de cada um.

Um BLOCO é um pedaço de BLOCK_SIZE_KM (0,5 km) de uma rodovia, num sentido. Ele
não existe no banco: é derivado do `estimated_km` de cada frame. Como esse km é
interpolado (não é GPS), tudo aqui é aproximado.

Fluxo:  load_blocks()  -> monta os blocos com suas leituras e eventos (1 consulta)
        state_at(...)  -> calcula o estado de um bloco numa data de referência

Separar os dois passos permite calcular o estado em datas diferentes (hoje e
no período anterior, na visão geral) carregando os dados uma vez só.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import (
    BLOCK_SIZE_KM,
    CRITICAL_GREEN_PERCENT,
    MIN_DAYS_FOR_GROWTH,
    MIN_READINGS_FOR_GROWTH,
)
from app.models import ScheduleEvent, Segment
from app.repositories import analytics_repository, schedule_repository

DIRECTIONS = ("CAPITAL", "INTERIOR")
PRIORITY_SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


# --- aritmética de blocos ---------------------------------------------------

def block_index(km: float) -> int:
    """Bloco que contém o km. round(...) evita que 11.5 / 0.5 = 22.999999 vire 22."""
    return math.floor(round(km / BLOCK_SIZE_KM, 9))


def block_bounds(index: int) -> tuple[float, float]:
    return round(index * BLOCK_SIZE_KM, 3), round((index + 1) * BLOCK_SIZE_KM, 3)


def blocks_covering(km_start: float, km_end: float) -> range:
    """Índices dos blocos que o intervalo semiaberto [km_start, km_end) toca (no mínimo um)."""
    first = block_index(km_start)
    last = math.ceil(round(km_end / BLOCK_SIZE_KM, 9)) - 1
    return range(first, max(first, last) + 1)


def event_blocks(event: ScheduleEvent) -> set[int]:
    return set(blocks_covering(event.km_start, event.km_end))


# --- estruturas --------------------------------------------------------------

@dataclass
class Reading:
    """Resultado de UMA inspeção num bloco: média do verde e pior prioridade dos frames que caíram nele."""
    time: datetime  # UTC, sem tzinfo (como o banco devolve)
    inspection_id: int
    green_percent: float
    priority: str

    @property
    def local_date(self) -> date:
        return clock.to_local_date(self.time)


@dataclass
class BlockData:
    road_id: int
    direction: str
    index: int
    segment_id: Optional[int]
    readings: list[Reading] = field(default_factory=list)
    events: list[ScheduleEvent] = field(default_factory=list)

    @property
    def km_start(self) -> float:
        return block_bounds(self.index)[0]

    @property
    def km_end(self) -> float:
        return block_bounds(self.index)[1]


@dataclass
class NextScheduled:
    id: int
    type: str
    date: date


@dataclass
class HistoryPoint:
    date: date
    green_percent: float


@dataclass
class BlockState:
    road_id: int
    segment_id: Optional[int]
    direction: str
    km_start: float
    km_end: float
    block_index: int
    priority: Optional[str]
    green_percent: Optional[float]
    last_inspected_at: Optional[datetime]
    last_mowed_at: Optional[datetime]
    growth_per_day: Optional[float]
    predicted_critical_date: Optional[date]
    next_scheduled: Optional[NextScheduled]
    readings_count: int
    last_inspection_id: Optional[int]
    history: Optional[list[HistoryPoint]] = None

    @property
    def last_inspected_date(self) -> Optional[date]:
        return clock.to_local_date(self.last_inspected_at) if self.last_inspected_at else None


# --- carregamento -----------------------------------------------------------

def load_blocks(db: Session, road_id: Optional[int] = None, direction: Optional[str] = None) -> list[BlockData]:
    """
    Blocos = os que os Segments cobrem (inclusive os nunca inspecionados) mais os
    que têm leitura mesmo fora dos segmentos (as pontas passam do limite).
    """
    directions = (direction,) if direction else DIRECTIONS
    segments = analytics_repository.list_segments(db, road_id)
    segments_by_road: dict[int, list[Segment]] = defaultdict(list)
    for segment in segments:
        segments_by_road[segment.road_id].append(segment)

    def segment_id_for(road: int, index: int) -> Optional[int]:
        for segment in segments_by_road.get(road, []):
            if index in blocks_covering(segment.km_start, segment.km_end):
                return segment.id
        return None

    blocks: dict[tuple[int, str, int], BlockData] = {}

    def get_block(road: int, dir_: str, index: int) -> BlockData:
        key = (road, dir_, index)
        if key not in blocks:
            blocks[key] = BlockData(road, dir_, index, segment_id_for(road, index))
        return blocks[key]

    for segment in segments:
        for index in blocks_covering(segment.km_start, segment.km_end):
            for dir_ in directions:
                get_block(segment.road_id, dir_, index)

    # Leituras: junta os frames de cada (inspeção, bloco).
    grouped: dict[tuple[int, str, int, int], dict] = {}
    for row in analytics_repository.list_frame_rows(db, road_id, direction):
        index = block_index(row.estimated_km)
        entry = grouped.setdefault(
            (row.road_id, row.direction, index, row.inspection_id),
            {"time": row.analyzed_at or row.created_at, "greens": [], "priorities": []},
        )
        entry["greens"].append(row.green_percent)
        entry["priorities"].append(row.frame_priority)

    for (road, dir_, index, inspection_id), entry in grouped.items():
        get_block(road, dir_, index).readings.append(Reading(
            time=entry["time"],
            inspection_id=inspection_id,
            green_percent=sum(entry["greens"]) / len(entry["greens"]),
            priority=max(entry["priorities"], key=PRIORITY_SEVERITY.__getitem__),
        ))

    for event in schedule_repository.list_not_canceled(db, road_id):
        covered = event_blocks(event)
        for dir_ in directions:
            if event.direction not in (None, dir_):
                continue
            for index in covered:
                block = blocks.get((event.road_id, dir_, index))
                if block is not None:
                    block.events.append(event)

    for block in blocks.values():
        block.readings.sort(key=lambda reading: reading.time)
    return sorted(blocks.values(), key=lambda b: (b.road_id, b.direction, b.index))


# --- estado de um bloco ------------------------------------------------------

def estimate_growth(readings: list[Reading]) -> Optional[float]:
    """
    Pontos percentuais de verde por dia: inclinação da reta que melhor ajusta
    (mínimos quadrados) as leituras ao longo do tempo. Sem leituras suficientes
    ou sem intervalo de tempo suficiente, não estima (None).
    """
    if len(readings) < MIN_READINGS_FOR_GROWTH:
        return None
    first = readings[0].time
    xs = [(reading.time - first).total_seconds() / 86400 for reading in readings]
    if xs[-1] < MIN_DAYS_FOR_GROWTH:
        return None
    ys = [reading.green_percent for reading in readings]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return round(sxy / sxx, 3)


def state_at(block: BlockData, as_of: date, include_history: bool = False) -> BlockState:
    cutoff = clock.end_of_day_utc(as_of)
    readings = [reading for reading in block.readings if reading.time <= cutoff]
    latest = readings[-1] if readings else None

    mowed_times = [
        event.completed_at for event in block.events
        if event.type == "MOWING" and event.status == "DONE"
        and event.completed_at is not None and event.completed_at <= cutoff
    ]
    last_mowed_at = max(mowed_times) if mowed_times else None

    # Só vale o crescimento DEPOIS da última roçada: antes dela o verde caiu, e a
    # reta sairia com inclinação negativa.
    since_mowing = [r for r in readings if last_mowed_at is None or r.time > last_mowed_at]
    growth = estimate_growth(since_mowing)

    predicted = None
    if (
        latest is not None and latest.priority != "HIGH" and growth is not None and growth > 0
        and latest.green_percent < CRITICAL_GREEN_PERCENT
    ):
        days = (CRITICAL_GREEN_PERCENT - latest.green_percent) / growth
        if days <= 3650:
            predicted = as_of + timedelta(days=math.ceil(days))

    scheduled = sorted(
        (e for e in block.events if e.status in schedule_repository.ACTIVE_STATUSES),
        key=lambda e: (e.scheduled_date, e.id),
    )
    next_scheduled = NextScheduled(scheduled[0].id, scheduled[0].type, scheduled[0].scheduled_date) if scheduled else None

    return BlockState(
        road_id=block.road_id,
        segment_id=block.segment_id,
        direction=block.direction,
        km_start=block.km_start,
        km_end=block.km_end,
        block_index=block.index,
        priority=latest.priority if latest else None,
        green_percent=round(latest.green_percent, 2) if latest else None,
        last_inspected_at=latest.time if latest else None,
        last_mowed_at=last_mowed_at,
        growth_per_day=growth,
        predicted_critical_date=predicted,
        next_scheduled=next_scheduled,
        readings_count=len(readings),
        last_inspection_id=latest.inspection_id if latest else None,
        history=(
            [HistoryPoint(reading.local_date, round(reading.green_percent, 2)) for reading in readings]
            if include_history else None
        ),
    )


def get_block_states(
    db: Session,
    as_of: date,
    road_id: Optional[int] = None,
    direction: Optional[str] = None,
    include_history: bool = False,
) -> list[BlockState]:
    return [state_at(block, as_of, include_history) for block in load_blocks(db, road_id, direction)]
