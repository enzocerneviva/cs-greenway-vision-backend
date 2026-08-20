from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Road
from app.schemas.road import RoadCreate, RoadResponse
from app.repositories import road_repository
from app.services import geocoding_service

router = APIRouter(prefix="/roads", tags=["roads"])


@router.post("", response_model=RoadResponse)
def create_road(payload: RoadCreate, db: Session = Depends(get_db)):
    road = Road(name=payload.name, concessionaire=payload.concessionaire)
    # Busca automática do traçado no OpenStreetMap — melhor esforço, nunca
    # impede o cadastro (ver app/services/geocoding_service.py).
    road.geometry = geocoding_service.fetch_road_geometry(payload.name)
    return road_repository.create(db, road)


@router.get("", response_model=List[RoadResponse])
def list_roads(db: Session = Depends(get_db)):
    return road_repository.list_all(db)
