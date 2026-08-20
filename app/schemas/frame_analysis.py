from pydantic import BaseModel


class FrameAnalysisResponse(BaseModel):
    frame_index: int
    timestamp_seconds: float
    estimated_km: float
    green_percent: float
    priority: str

    class Config:
        from_attributes = True
