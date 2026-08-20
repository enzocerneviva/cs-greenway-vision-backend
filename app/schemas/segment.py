from typing import Optional
from pydantic import BaseModel


class SegmentCreate(BaseModel):
    road_id: int
    km_start: float
    km_end: float
    direction: str
    lat_start: Optional[float] = None
    lng_start: Optional[float] = None
    lat_end: Optional[float] = None
    lng_end: Optional[float] = None


class SegmentResponse(BaseModel):
    id: int
    road_id: int
    km_start: float
    km_end: float
    direction: str
    lat_start: Optional[float]
    lng_start: Optional[float]
    lat_end: Optional[float]
    lng_end: Optional[float]

    class Config:
        from_attributes = True
