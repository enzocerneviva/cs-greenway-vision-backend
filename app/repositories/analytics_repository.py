from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import FrameAnalysis, Inspection, Segment, Video


def list_segments(db: Session, road_id: Optional[int] = None) -> List[Segment]:
    query = db.query(Segment)
    if road_id is not None:
        query = query.filter(Segment.road_id == road_id)
    return query.order_by(Segment.road_id, Segment.km_start).all()


def list_frame_rows(db: Session, road_id: Optional[int] = None, direction: Optional[str] = None):
    """
    Uma linha por frame de inspeção CONCLUÍDA e com sentido definido (as FAILED,
    PROCESSING e as antigas sem direction não entram), já com a rodovia e o
    instante da inspeção. É a matéria-prima de todas as leituras por bloco.
    """
    query = (
        db.query(
            Inspection.id.label("inspection_id"),
            Inspection.analyzed_at,
            Inspection.created_at,
            Inspection.priority.label("inspection_priority"),
            Inspection.direction,
            Segment.road_id,
            FrameAnalysis.estimated_km,
            FrameAnalysis.green_percent,
            FrameAnalysis.priority.label("frame_priority"),
        )
        .join(Video, Inspection.video_id == Video.id)
        .join(Segment, Video.segment_id == Segment.id)
        .join(FrameAnalysis, FrameAnalysis.inspection_id == Inspection.id)
        .filter(Inspection.status == "DONE", Inspection.direction.isnot(None))
    )
    if road_id is not None:
        query = query.filter(Segment.road_id == road_id)
    if direction:
        query = query.filter(Inspection.direction == direction)
    return query.all()
