from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Segment
from app.schemas.segment import SegmentCreate, SegmentLocationUpdate, SegmentResponse
from app.repositories import segment_repository, road_repository

router = APIRouter(prefix="/segments", tags=["segments"])


@router.post("", response_model=SegmentResponse)
def create_segment(payload: SegmentCreate, db: Session = Depends(get_db)):
    road = road_repository.get_by_id(db, payload.road_id)
    if road is None:
        raise HTTPException(status_code=404, detail="Road not found")

    segment = Segment(
        road_id=payload.road_id,
        km_start=payload.km_start,
        km_end=payload.km_end,
        direction=payload.direction,
        lat_start=payload.lat_start,
        lng_start=payload.lng_start,
        lat_end=payload.lat_end,
        lng_end=payload.lng_end,
    )
    return segment_repository.create(db, segment)


@router.get("", response_model=List[SegmentResponse])
def list_segments(db: Session = Depends(get_db)):
    return segment_repository.list_all(db)


@router.patch("/{segment_id}/location", response_model=SegmentResponse)
def update_segment_location(
    segment_id: int, payload: SegmentLocationUpdate, db: Session = Depends(get_db)
):
    segment = segment_repository.get_by_id(db, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    segment.lat_start = payload.lat_start
    segment.lng_start = payload.lng_start
    segment.lat_end = payload.lat_end
    segment.lng_end = payload.lng_end
    return segment_repository.update(db, segment)
