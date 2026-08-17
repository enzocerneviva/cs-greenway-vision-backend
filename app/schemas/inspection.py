from typing import Optional
from pydantic import BaseModel
from datetime import datetime


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

    class Config:
        from_attributes = True


class VideoUploadResponse(BaseModel):
    original_filename: str
    stored_path: str
