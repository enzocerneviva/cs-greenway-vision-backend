from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.schemas.frame_analysis import FrameAnalysisResponse


class InspectionResponse(BaseModel):
    id: int
    video_id: int
    measurement_value: Optional[float]
    measurement_unit: Optional[str]
    priority: Optional[str]
    model_version: Optional[str]
    status: str
    analyzed_at: Optional[datetime]
    created_at: datetime
    frame_analyses: List[FrameAnalysisResponse] = []

    class Config:
        from_attributes = True
