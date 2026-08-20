from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Video


def create(db: Session, video: Video) -> Video:
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def get_by_id(db: Session, video_id: int) -> Optional[Video]:
    return db.get(Video, video_id)


def list_all(db: Session) -> List[Video]:
    return db.query(Video).all()


def delete_all(db: Session) -> None:
    db.query(Video).delete()
    db.commit()
