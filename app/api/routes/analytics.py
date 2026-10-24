from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import clock
from app.database.session import get_db
from app.schemas.analytics import (
    BlockStateResponse,
    MowingEffectivenessItem,
    OverviewResponse,
    TimeSeriesPoint,
)
from app.schemas.types import Direction
from app.services import analytics_service, block_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/blocks", response_model=List[BlockStateResponse])
def get_blocks(
    road_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    include: Optional[str] = Query(None, description="'history' inclui as leituras de cada bloco"),
    db: Session = Depends(get_db),
):
    """
    Estado atual de cada bloco de 0,5 km (por rodovia e sentido), inclusive os
    nunca inspecionados (priority = null). Base da fila de ação, das barras por
    rodovia e das previsões. Valores por bloco são APROXIMADOS: o km de cada
    frame é interpolado, não é GPS.
    """
    include_history = include is not None and "history" in include.split(",")
    return block_service.get_block_states(db, clock.today(), road_id, direction, include_history)


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    road_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """Indicadores do período (padrão: últimos 30 dias) e do período anterior, para comparação."""
    return analytics_service.overview(db, road_id, direction, date_from, date_to)


@router.get("/timeseries", response_model=List[TimeSeriesPoint])
def get_timeseries(
    bucket: Literal["week"] = "week",
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    road_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    db: Session = Depends(get_db),
):
    return analytics_service.timeseries(db, bucket, date_from, date_to, road_id, direction)


@router.get("/mowing-effectiveness", response_model=List[MowingEffectivenessItem])
def get_mowing_effectiveness(
    road_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    db: Session = Depends(get_db),
):
    """Verde médio antes e depois de cada roçada concluída."""
    return analytics_service.mowing_effectiveness(db, road_id, direction)
