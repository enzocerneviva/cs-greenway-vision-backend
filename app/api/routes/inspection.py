from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.inspection import InspectionResponse, VideoUploadResponse
from app.repositories import inspection_repository
from app.services.inspection_service import save_inspection_video

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


@router.post("/upload", response_model=VideoUploadResponse)
def upload_inspection_video(file: UploadFile = File(...)):
    stored_path = save_inspection_video(file)
    return VideoUploadResponse(original_filename=file.filename, stored_path=stored_path)
