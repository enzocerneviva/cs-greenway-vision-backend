from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Segment


def create(db: Session, segment: Segment) -> Segment:
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def get_by_id(db: Session, segment_id: int) -> Optional[Segment]:
    return db.get(Segment, segment_id)


def list_all(db: Session) -> List[Segment]:
    return db.query(Segment).all()


def update(db: Session, segment: Segment) -> Segment:
    db.commit()
    db.refresh(segment)
    return segment
