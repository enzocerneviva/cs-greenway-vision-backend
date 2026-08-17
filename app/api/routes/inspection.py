from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Inspection, Video
from app.schemas.inspection import InspectionResponse
from app.repositories import inspection_repository, segment_repository, video_repository
from app.services.inspection_service import save_inspection_video
from app.vision import engine as vision_engine

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
    segment = segment_repository.get_by_id(db, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    stored_path = save_inspection_video(file)

    video = video_repository.create(db, Video(
        segment_id=segment_id,
        file_path=stored_path,
        original_filename=file.filename,
    ))

    # O vídeo já está salvo e o Video persistido nesse ponto. Se a análise
    # falhar por qualquer motivo (vídeo corrompido, sem frames extraíveis,
    # erro do modelo), a inspeção é registrada como FAILED em vez de perder
    # a referência ao vídeo ou estourar um 500 pro cliente.
    try:
        result = vision_engine.analyze(stored_path)
        inspection = Inspection(
            video_id=video.id,
            measurement_value=result.measurement_value,
            measurement_unit=result.measurement_unit,
            priority=result.priority,
            model_version=result.model_version,
            status="DONE",
            analyzed_at=datetime.now(timezone.utc),
        )
    except Exception:
        inspection = Inspection(
            video_id=video.id,
            status="FAILED",
        )

    return inspection_repository.create(db, inspection)
