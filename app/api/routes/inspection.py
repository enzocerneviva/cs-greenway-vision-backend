from typing import List
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.inspection import InspectionResponse
from app.repositories import inspection_repository
from app.services import inspection_service

router = APIRouter(prefix="/inspections", tags=["inspections"])


@router.get("", response_model=List[InspectionResponse])
def list_inspections(db: Session = Depends(get_db)):
    return inspection_repository.list_all(db)


@router.get("/{inspection_id}", response_model=InspectionResponse)
def get_inspection(inspection_id: int, db: Session = Depends(get_db)):
    inspection = inspection_repository.get_by_id(db, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@router.post("", response_model=InspectionResponse)
def create_inspection(
    segment_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return inspection_service.create_inspection(db, segment_id, file)
