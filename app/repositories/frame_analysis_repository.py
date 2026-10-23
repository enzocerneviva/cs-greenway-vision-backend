from typing import List
from sqlalchemy.orm import Session
from app.models import FrameAnalysis


def create(db: Session, frame_analysis: FrameAnalysis) -> FrameAnalysis:
    db.add(frame_analysis)
    db.flush()  # envia o INSERT (gera o id) sem confirmar a transação
    return frame_analysis


def create_many(db: Session, frame_analyses: List[FrameAnalysis]) -> None:
    db.add_all(frame_analyses)
    db.flush()


def list_by_inspection(db: Session, inspection_id: int) -> List[FrameAnalysis]:
    return (
        db.query(FrameAnalysis)
        .filter(FrameAnalysis.inspection_id == inspection_id)
        .order_by(FrameAnalysis.frame_index)
        .all()
    )


def delete_all(db: Session) -> None:
    db.query(FrameAnalysis).delete()
