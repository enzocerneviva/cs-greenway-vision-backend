from sqlalchemy import Column, Integer, Float, String, ForeignKey
from app.database.session import Base


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, index=True)
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=False)
    km_start = Column(Float, nullable=False)
    km_end = Column(Float, nullable=False)
    direction = Column(String, nullable=False)  # sentido da pista, ex.: "NORTE"/"SUL"
