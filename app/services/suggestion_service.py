"""
Sugestões de agenda ("inspecionar este trecho", "roçar este trecho").

São CALCULADAS NA HORA a partir do estado dos blocos — nada fica gravado, exceto
os descartes do usuário (tabela suggestion_dismissals).

Como evitar centenas de cartões: o cálculo é por bloco de 0,5 km, mas blocos
CONTÍGUOS (mesma rodovia, sentido, tipo e motivo) viram UMA sugestão com o
intervalo [km_start, km_end), e a lista é limitada (`limit`).

Valores de regra (intervalos máximos, antecedência, horizonte) vêm de
app/core/config.py.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import (
    BLOCK_SIZE_KM,
    DISMISS_DEFAULT_DAYS,
    INSPECTION_MAX_DAYS,
    MOWING_LEAD_DAYS,
    PREDICTION_HORIZON_DAYS,
    SUGGESTIONS_DEFAULT_LIMIT,
    SUGGESTIONS_MAX_LIMIT,
)
from app.models import SuggestionDismissal
from app.repositories import schedule_repository, suggestion_dismissal_repository
from app.services import block_service

ACTIVE = schedule_repository.ACTIVE_STATUSES
PRIORITY_PT = {"HIGH": "alta", "MEDIUM": "média", "LOW": "baixa"}
# Quanto a prioridade da última leitura pesa na urgência de uma inspeção vencida.
PRIORITY_URGENCY_BONUS = {"HIGH": 10, "MEDIUM": 5, "LOW": 0}


@dataclass
class Suggestion:
    key: str
    type: str
    road_id: int
    segment_id: Optional[int]
    direction: str
    km_start: float
    km_end: float
    suggested_date: date
    urgency: int
    reason_code: str
    reason: str


@dataclass
class _Candidate:
    """Sugestão para UM bloco, antes de agrupar."""
    block: block_service.BlockData
    state: block_service.BlockState
    type: str
    reason_code: str
    suggested_date: date
    urgency: int
    reason: str


# --- texto -------------------------------------------------------------------

def _pt_number(value: float, decimals: int = 1) -> str:
    """Número no formato brasileiro: vírgula decimal (os motivos são texto pronto em pt-BR)."""
    return f"{value:.{decimals}f}".replace(".", ",")


# --- datas -------------------------------------------------------------------

def next_business_day(after: date) -> date:
    """Primeiro dia útil (segunda a sexta) depois de `after`. Feriados ficam para depois."""
    day = after + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _business_day_on_or_before(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _first_free_mowing_day(today: date, busy: set[date]) -> date:
    """Próximo dia útil que ainda não tem outra roçada naquela rodovia/sentido."""
    day = next_business_day(today)
    while day in busy:
        day = next_business_day(day)
    return day


# --- candidatos por bloco ----------------------------------------------------

def _block_candidates(block, state, today: date, busy: set[date]) -> list[_Candidate]:
    candidates = []
    # "Nunca sugerir bloco que já tenha evento planejado" — vale por TIPO: uma
    # inspeção planejada não impede sugerir a roçada de um bloco crítico.
    planned_types = {event.type for event in block.events if event.status in ACTIVE}

    def candidate(type_, code, day, urgency, reason):
        return _Candidate(block, state, type_, code, day, max(0, min(100, int(urgency))), reason)

    last_date = state.last_inspected_date
    age = (today - last_date).days if last_date else None

    if "INSPECTION" not in planned_types:
        if state.priority is None:
            candidates.append(candidate(
                "INSPECTION", "NEVER_INSPECTED", next_business_day(today), 35,
                "Trecho nunca inspecionado.",
            ))
        else:
            limit = INSPECTION_MAX_DAYS[state.priority]
            if age > limit:
                candidates.append(candidate(
                    "INSPECTION", "STALE_INSPECTION", next_business_day(today),
                    40 + min(20, age - limit) + PRIORITY_URGENCY_BONUS[state.priority],
                    f"Última inspeção há {age} dias (limite para prioridade {PRIORITY_PT[state.priority]}: {limit} dias).",
                ))

    if "MOWING" not in planned_types and state.priority is not None:
        # Se já houve roçada DEPOIS da última leitura, a leitura "alta" está velha:
        # o que falta é inspecionar de novo, não roçar.
        mowed_after_reading = state.last_mowed_at is not None and state.last_mowed_at >= state.last_inspected_at
        if not mowed_after_reading:
            if state.priority == "HIGH":
                candidates.append(candidate(
                    "MOWING", "CRITICAL_NOW", _first_free_mowing_day(today, busy),
                    90 + min(10, age // 3),
                    f"Vegetação em nível alto na última inspeção ({last_date.strftime('%d/%m/%Y')}).",
                ))
            elif state.predicted_critical_date is not None:
                days_to = (state.predicted_critical_date - today).days
                if days_to <= PREDICTION_HORIZON_DAYS:
                    target = _business_day_on_or_before(state.predicted_critical_date - timedelta(days=MOWING_LEAD_DAYS))
                    candidates.append(candidate(
                        "MOWING", "PREDICTED_CRITICAL", max(target, next_business_day(today)),
                        min(85, 60 + max(0, 25 - days_to)),
                        f"Cresce {_pt_number(state.growth_per_day)} pontos de verde por dia; "
                        f"deve chegar ao nível alto em ~{max(days_to, 0)} dias (estimativa).",
                    ))
    return candidates


# --- agrupamento -------------------------------------------------------------

def _make_key(type_: str, road_id: int, direction: str, km_start: float, km_end: float) -> str:
    return f"{type_}:{road_id}:{direction}:{km_start:g}:{km_end:g}"


def _group(candidates: list[_Candidate]) -> list[Suggestion]:
    """Junta blocos contíguos (mesma rodovia, sentido, tipo e motivo) numa sugestão só."""
    groups: dict[tuple, list[_Candidate]] = defaultdict(list)
    for item in candidates:
        groups[(item.block.road_id, item.block.direction, item.type, item.reason_code)].append(item)

    suggestions = []
    for (road_id, direction, type_, reason_code), items in groups.items():
        items.sort(key=lambda item: item.block.index)
        runs: list[list[_Candidate]] = []
        for item in items:
            if runs and item.block.index == runs[-1][-1].block.index + 1:
                runs[-1].append(item)
            else:
                runs.append([item])

        for run in runs:
            km_start, km_end = run[0].block.km_start, run[-1].block.km_end
            strongest = max(run, key=lambda item: item.urgency)
            reason = strongest.reason
            if len(run) > 1:
                reason += f" Abrange {len(run)} blocos de {_pt_number(BLOCK_SIZE_KM)} km."
            suggestions.append(Suggestion(
                key=_make_key(type_, road_id, direction, km_start, km_end),
                type=type_,
                road_id=road_id,
                segment_id=run[0].state.segment_id,
                direction=direction,
                km_start=km_start,
                km_end=km_end,
                suggested_date=min(item.suggested_date for item in run),
                urgency=strongest.urgency,
                reason_code=reason_code,
                reason=reason,
            ))
    return suggestions


# --- API do service ----------------------------------------------------------

def get_suggestions(
    db: Session,
    type: Optional[str] = None,
    road_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = None,
) -> list[Suggestion]:
    today = clock.today()
    limit = min(limit or SUGGESTIONS_DEFAULT_LIMIT, SUGGESTIONS_MAX_LIMIT)

    blocks = block_service.load_blocks(db, road_id)
    busy_mowing_days: dict[tuple[int, str], set[date]] = defaultdict(set)
    for block in blocks:
        for event in block.events:
            if event.type == "MOWING" and event.status in ACTIVE:
                busy_mowing_days[(block.road_id, block.direction)].add(event.scheduled_date)

    candidates = []
    for block in blocks:
        state = block_service.state_at(block, today)
        candidates.extend(_block_candidates(block, state, today, busy_mowing_days[(block.road_id, block.direction)]))

    hidden = suggestion_dismissal_repository.active_keys(db, today)
    suggestions = [
        s for s in _group(candidates)
        if s.key not in hidden
        and (type is None or s.type == type)
        and (date_from is None or s.suggested_date >= date_from)
        and (date_to is None or s.suggested_date <= date_to)
    ]
    suggestions.sort(key=lambda s: (-s.urgency, s.suggested_date, s.road_id, s.km_start))
    return suggestions[:limit]


def dismiss(db: Session, key: str, until: Optional[date] = None) -> SuggestionDismissal:
    until = until or clock.today() + timedelta(days=DISMISS_DEFAULT_DAYS)
    dismissal = suggestion_dismissal_repository.upsert(db, key, until)
    db.commit()
    db.refresh(dismissal)
    return dismissal
