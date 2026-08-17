from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Segment
from app.schemas.segment import SegmentCreate, SegmentResponse
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
    )
    return segment_repository.create(db, segment)


@router.get("", response_model=List[SegmentResponse])
def list_segments(db: Session = Depends(get_db)):
    return segment_repository.list_all(db)
