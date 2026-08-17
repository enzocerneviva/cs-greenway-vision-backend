from typing import List

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from app.schemas.inspection import InspectionResponse, VideoUploadResponse
from app.models import Inspection
from app.database.session import Base, engine, SessionLocal, get_db
from app.services.inspection_service import save_inspection_video
from sqlalchemy.orm import Session

app = FastAPI(
    title="GreenWay Vision API",
    description="Backend da plataforma GreenWay Vision",
    version="0.1.0"
)

Base.metadata.create_all(bind=engine)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/inspections", response_model=List[InspectionResponse])
def list_inspections(db: Session = Depends(get_db)):
    return db.query(Inspection).all()


@app.get("/inspections/{inspection_id}", response_model=InspectionResponse)
def get_inspection(inspection_id: int, db: Session = Depends(get_db)):
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@app.post("/inspections/upload", response_model=VideoUploadResponse)
def upload_inspection_video(file: UploadFile = File(...)):
    stored_path = save_inspection_video(file)
    return VideoUploadResponse(original_filename=file.filename, stored_path=stored_path)
