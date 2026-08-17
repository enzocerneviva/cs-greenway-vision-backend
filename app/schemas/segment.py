from pydantic import BaseModel


class SegmentCreate(BaseModel):
    road_id: int
    km_start: float
    km_end: float
    direction: str


class SegmentResponse(BaseModel):
    id: int
    road_id: int
    km_start: float
    km_end: float
    direction: str

    class Config:
        from_attributes = True
