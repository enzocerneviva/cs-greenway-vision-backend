from typing import List, Optional
from pydantic import BaseModel

from app.schemas.frame_analysis import FrameAnalysisResponse
from app.schemas.types import Direction, InspectionStatus, Priority, UtcDatetime


class InspectionResponse(BaseModel):
    id: int
    video_id: int
    segment_id: int
    measurement_value: Optional[float]
    measurement_unit: Optional[str]
    priority: Optional[Priority]
    model_version: Optional[str]
    direction: Optional[Direction]
    status: InspectionStatus
    failure_reason: Optional[str]
    analyzed_at: Optional[UtcDatetime]
    created_at: UtcDatetime
    frame_analyses: List[FrameAnalysisResponse] = []

    class Config:
        from_attributes = True
