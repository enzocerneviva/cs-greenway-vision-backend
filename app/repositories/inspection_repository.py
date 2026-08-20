from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Inspection


def create(db: Session, inspection: Inspection) -> Inspection:
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def get_by_id(db: Session, inspection_id: int) -> Optional[Inspection]:
    return db.get(Inspection, inspection_id)


def list_all(db: Session) -> List[Inspection]:
    return db.query(Inspection).all()


def delete_all(db: Session) -> None:
    db.query(Inspection).delete()
    db.commit()
