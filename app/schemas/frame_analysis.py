from typing import Optional
from pydantic import BaseModel

from app.schemas.types import Priority


class FrameAnalysisResponse(BaseModel):
    frame_index: int
    timestamp_seconds: float
    estimated_km: float
    green_percent: float
    priority: Priority
    image_path: Optional[str]

    class Config:
        from_attributes = True
