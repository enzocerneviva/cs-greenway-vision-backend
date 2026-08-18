import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models import Inspection, Video
from app.repositories import inspection_repository, segment_repository, video_repository
from app.vision import engine as vision_engine

ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
}

MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

STORAGE_DIR = "storage/videos"


def save_inspection_video(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video type: {file.content_type}",
        )

    os.makedirs(STORAGE_DIR, exist_ok=True)

    extension = os.path.splitext(file.filename)[1]
    safe_filename = f"{uuid.uuid4()}{extension}"
    destination_path = os.path.join(STORAGE_DIR, safe_filename)

    total_bytes_written = 0
    with open(destination_path, "wb") as buffer:
        while chunk := file.file.read(1024 * 1024):
            total_bytes_written += len(chunk)
            if total_bytes_written > MAX_VIDEO_SIZE_BYTES:
                buffer.close()
                os.remove(destination_path)
                raise HTTPException(
                    status_code=413,
                    detail="Video exceeds the maximum allowed size (100MB)",
                )
            buffer.write(chunk)

    return destination_path


def create_inspection(db: Session, segment_id: int, file: UploadFile) -> Inspection:
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
