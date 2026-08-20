from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.session import Base


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, unique=True)

    measurement_value = Column(Float, nullable=True)  # nulo se a análise falhar
    measurement_unit = Column(String, nullable=True)
    priority = Column(String, nullable=True)  # LOW / MEDIUM / HIGH

    model_version = Column(String, nullable=True)
    status = Column(String, nullable=False)  # DONE / FAILED
    analyzed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    frame_analyses = relationship("FrameAnalysis", order_by="FrameAnalysis.frame_index")
    video = relationship("Video")

    @property
    def segment_id(self) -> int:
        return self.video.segment_id
