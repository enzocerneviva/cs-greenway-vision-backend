from pydantic import BaseModel
from datetime import datetime

class InspectionCreate(BaseModel):
    measurement_value: float
    measurement_unit: str = "cm"

class InspectionResponse(BaseModel):
    id: int
    measurement_value: float
    measurement_unit: str
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True


class VideoUploadResponse(BaseModel):
    original_filename: str
    stored_path: str
