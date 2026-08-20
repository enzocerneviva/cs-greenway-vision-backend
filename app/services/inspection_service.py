import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models import FrameAnalysis, Inspection, Segment, Video
from app.repositories import (
    frame_analysis_repository,
    inspection_repository,
    segment_repository,
    video_repository,
)
from app.vision import engine as vision_engine
from app.vision.analysis_result import FrameResult

# Ancorado na raiz do projeto (não no cwd do processo) — mesmo motivo do
# path do banco em app/database/session.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
}

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
}

MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB — imagem é bem menor que vídeo

VIDEO_STORAGE_DIR = PROJECT_ROOT / "storage" / "videos"
IMAGE_STORAGE_DIR = PROJECT_ROOT / "storage" / "images"
FRAME_STORAGE_DIR = PROJECT_ROOT / "storage" / "frames"


def _resolve_media_type(content_type: str) -> str:
    if content_type in ALLOWED_VIDEO_CONTENT_TYPES:
        return "video"
    if content_type in ALLOWED_IMAGE_CONTENT_TYPES:
        return "image"
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {content_type}",
    )


def save_inspection_media(file: UploadFile) -> tuple[str, str]:
    """Salva um vídeo ou imagem de inspeção em disco. Retorna (stored_path, media_type)."""
    media_type = _resolve_media_type(file.content_type)

    if media_type == "video":
        storage_dir = VIDEO_STORAGE_DIR
        max_size = MAX_VIDEO_SIZE_BYTES
    else:
        storage_dir = IMAGE_STORAGE_DIR
        max_size = MAX_IMAGE_SIZE_BYTES

    os.makedirs(storage_dir, exist_ok=True)

    extension = os.path.splitext(file.filename)[1]
    safe_filename = f"{uuid.uuid4()}{extension}"
    destination_path = os.path.join(storage_dir, safe_filename)

    total_bytes_written = 0
    with open(destination_path, "wb") as buffer:
        while chunk := file.file.read(1024 * 1024):
            total_bytes_written += len(chunk)
            if total_bytes_written > max_size:
                buffer.close()
                os.remove(destination_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the maximum allowed size ({max_size // (1024 * 1024)}MB)",
                )
            buffer.write(chunk)

    return destination_path, media_type


def create_inspection(
    db: Session,
    segment_id: int,
    file: UploadFile,
    km_start: float | None = None,
    km_end: float | None = None,
    direction: str | None = None,
) -> Inspection:
    segment = segment_repository.get_by_id(db, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    stored_path, media_type = save_inspection_media(file)

    video = video_repository.create(db, Video(
        segment_id=segment_id,
        file_path=stored_path,
        original_filename=file.filename,
        media_type=media_type,
    ))

    frame_image_dir = FRAME_STORAGE_DIR / str(video.id)

    # O arquivo já está salvo e o Video persistido nesse ponto. Se a análise
    # falhar por qualquer motivo (vídeo/imagem corrompido, sem frames
    # extraíveis, erro do modelo), a inspeção é registrada como FAILED em
    # vez de perder a referência ao arquivo ou estourar um 500 pro cliente.
    try:
        result = vision_engine.analyze(stored_path, media_type, frame_image_dir=frame_image_dir)
    except Exception:
        inspection = Inspection(video_id=video.id, status="FAILED")
        return inspection_repository.create(db, inspection)

    inspection = Inspection(
        video_id=video.id,
        measurement_value=result.measurement_value,
        measurement_unit=result.measurement_unit,
        priority=result.priority,
        model_version=result.model_version,
        direction=direction,
        status="DONE",
        analyzed_at=datetime.now(timezone.utc),
    )
    inspection = inspection_repository.create(db, inspection)

    _persist_frame_analyses(
        db, inspection.id, segment, result.frame_results, km_start=km_start, km_end=km_end
    )

    return inspection


def _persist_frame_analyses(
    db: Session,
    inspection_id: int,
    segment: Segment,
    frame_results: list[FrameResult],
    km_start: float | None = None,
    km_end: float | None = None,
) -> None:
    """
    Salva o detalhe por frame. O intervalo de km sobre o qual os frames são
    interpolados vem de:
    - km_start/km_end, se informados — o vídeo/foto não necessariamente
      cobre o trecho inteiro (um vídeo de poucos segundos pode representar
      só 500m de uma rodovia de 150km). Foto usa km_start == km_end (um
      único ponto: o único frame cai exatamente ali).
    - senão, km_start/km_end do Segment inteiro (comportamento antigo,
      assume que o arquivo cobre o trecho todo).
    Dentro do intervalo escolhido, a posição de cada frame é interpolação
    linear por índice — aproximação v1, não é GPS real.
    """
    total = len(frame_results)
    range_start = km_start if km_start is not None else segment.km_start
    range_end = km_end if km_end is not None else segment.km_end
    km_range = range_end - range_start

    for frame_result in frame_results:
        # frame_index / total (não / (total - 1)) de propósito: o último
        # frame não pode cair exatamente em range_end, porque os blocos de
        # 500m são um intervalo semiaberto [kmStart, kmEnd) — um frame
        # exatamente em kmEnd "vazava" pro bloco seguinte.
        fraction = frame_result.frame_index / total
        estimated_km = range_start + fraction * km_range

        image_path = None
        if frame_result.image_path is not None:
            # Guardado relativo à raiz do projeto (não o path absoluto que o
            # vision engine usou pra escrever) — é o que vira URL servida
            # estaticamente pelo backend (ver app/main.py).
            image_path = Path(frame_result.image_path).relative_to(PROJECT_ROOT).as_posix()

        frame_analysis_repository.create(db, FrameAnalysis(
            inspection_id=inspection_id,
            frame_index=frame_result.frame_index,
            timestamp_seconds=frame_result.timestamp_seconds,
            estimated_km=estimated_km,
            green_percent=frame_result.green_percent,
            priority=frame_result.priority,
            image_path=image_path,
        ))
