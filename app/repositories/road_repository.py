from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Road


def create(db: Session, road: Road) -> Road:
    db.add(road)
    db.commit()
    db.refresh(road)
    return road


def get_by_id(db: Session, road_id: int) -> Optional[Road]:
    return db.get(Road, road_id)


def list_all(db: Session) -> List[Road]:
    return db.query(Road).all()
