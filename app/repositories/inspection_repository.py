from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Inspection


def create(db: Session, inspection: Inspection) -> Inspection:
    db.add(inspection)
    db.flush()  # envia o INSERT (gera o id) sem confirmar a transação
    return inspection


def get_by_id(db: Session, inspection_id: int) -> Optional[Inspection]:
    return db.get(Inspection, inspection_id)


def list_all(db: Session) -> List[Inspection]:
    return db.query(Inspection).all()


def list_by_status(db: Session, status: str) -> List[Inspection]:
    return db.query(Inspection).filter(Inspection.status == status).all()


def delete_all(db: Session) -> None:
    db.query(Inspection).delete()
