import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import (
    FRAME_DISPLAY_MAX_WIDTH,
    FRAME_JPEG_QUALITY,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
)
from app.database.session import SessionLocal
from app.models import FrameAnalysis, Inspection, Segment, Video
from app.repositories import (
    frame_analysis_repository,
    inspection_repository,
    segment_repository,
    video_repository,
)
from app.vision import engine as vision_engine
from app.vision.analysis_result import AnalysisError, FrameResult

logger = logging.getLogger(__name__)

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

STORAGE_ROOT = PROJECT_ROOT / "storage"
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


def accept_inspection(
    db: Session,
    segment_id: int,
    file: UploadFile,
    direction: str | None = None,
) -> Inspection:
    """
    Passo 1 do upload (síncrono, rápido): valida o trecho, guarda o arquivo e
    cria o Video + a Inspection com status PROCESSING, numa única transação.
    A análise em si acontece depois, em process_inspection.
    """
    segment = segment_repository.get_by_id(db, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    stored_path, media_type = save_inspection_media(file)

    try:
        video = video_repository.create(db, Video(
            segment_id=segment_id,
            file_path=stored_path,
            original_filename=file.filename,
            media_type=media_type,
        ))
        inspection = inspection_repository.create(db, Inspection(
            video_id=video.id,
            status="PROCESSING",
            direction=direction,
        ))
        db.commit()
    except Exception:
        # Capturado só pra limpar: se a gravação falhou, desfaz a transação e
        # apaga o arquivo recém-salvo (senão ficaria órfão em storage/); depois
        # o erro original segue adiante.
        db.rollback()
        _remove_file(stored_path)
        raise

    db.refresh(inspection)
    return inspection


def process_inspection(
    inspection_id: int,
    km_start: float | None = None,
    km_end: float | None = None,
) -> None:
    """
    Passo 2 do upload (roda em segundo plano, depois da resposta 202): analisa
    a mídia e grava o resultado — a Inspection e todos os seus FrameAnalysis
    num único commit (tudo ou nada).

    Abre a PRÓPRIA Session: a da requisição é fechada quando a resposta sai.
    """
    db = SessionLocal()
    try:
        _run_analysis(db, inspection_id, km_start, km_end)
    except Exception:
        # Captura geral de propósito (e única): aqui não há cliente a quem
        # devolver um erro 500, e uma exceção solta deixaria a inspeção em
        # PROCESSING para sempre. O erro completo vai pro log; a inspeção vira
        # FAILED com um motivo genérico (o detalhe técnico não vai pro usuário).
        logger.exception("Erro inesperado ao processar a inspeção %s", inspection_id)
        db.rollback()
        _mark_failed_by_id(db, inspection_id, "Erro interno ao processar a mídia (ver log do servidor).")
    finally:
        db.close()


def _run_analysis(
    db: Session,
    inspection_id: int,
    km_start: float | None,
    km_end: float | None,
) -> None:
    inspection = inspection_repository.get_by_id(db, inspection_id)
    if inspection is None:
        # Apagada (reset de análises) enquanto estava na fila.
        logger.warning("Inspeção %s não existe mais; análise descartada.", inspection_id)
        return

    video = inspection.video
    segment = segment_repository.get_by_id(db, video.segment_id)
    frame_image_dir = FRAME_STORAGE_DIR / str(video.id)

    # AnalysisError = a mídia não pôde ser analisada (arquivo corrompido, sem
    # frames, falha num frame): vira FAILED com o motivo. Qualquer outro erro é
    # bug de código e sobe até process_inspection.
    try:
        result = vision_engine.analyze(
            video.file_path,
            video.media_type,
            frame_image_dir=frame_image_dir,
            frame_max_width=FRAME_DISPLAY_MAX_WIDTH,
            frame_jpeg_quality=FRAME_JPEG_QUALITY,
        )
    except AnalysisError as exc:
        logger.warning("Análise falhou (inspeção %s): %s", inspection_id, exc, exc_info=True)
        _discard_frame_images(frame_image_dir)
        inspection.status = "FAILED"
        inspection.failure_reason = str(exc)[:300]
        db.commit()
        return

    try:
        inspection.measurement_value = result.measurement_value
        inspection.measurement_unit = result.measurement_unit
        inspection.priority = result.priority
        inspection.model_version = result.model_version
        inspection.status = "DONE"
        inspection.analyzed_at = datetime.now(timezone.utc)
        frame_analysis_repository.create_many(
            db,
            _build_frame_analyses(
                inspection.id, segment, result.frame_results, km_start=km_start, km_end=km_end
            ),
        )
        db.commit()
    except Exception:
        # Limpa e deixa o erro seguir: as imagens dos frames foram escritas em
        # disco mas nenhuma linha chegou ao banco, então ficariam órfãs.
        db.rollback()
        _discard_frame_images(frame_image_dir)
        raise


def _mark_failed_by_id(db: Session, inspection_id: int, reason: str) -> None:
    try:
        inspection = inspection_repository.get_by_id(db, inspection_id)
        if inspection is None or inspection.status != "PROCESSING":
            return
        _discard_frame_images(FRAME_STORAGE_DIR / str(inspection.video_id))
        inspection.status = "FAILED"
        inspection.failure_reason = reason
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Não foi possível marcar a inspeção %s como FAILED", inspection_id)


def fail_orphaned_processing(db: Session) -> int:
    """
    Chamada na subida da API: inspeções ainda em PROCESSING são de uma análise
    que morreu junto com o servidor anterior (a tarefa em segundo plano vive no
    processo). Viram FAILED, pra não ficarem "processando" para sempre.
    Pressupõe um único processo servidor.
    """
    orphans = inspection_repository.list_by_status(db, "PROCESSING")
    for inspection in orphans:
        _discard_frame_images(FRAME_STORAGE_DIR / str(inspection.video_id))
        inspection.status = "FAILED"
        inspection.failure_reason = "Análise interrompida: o servidor foi reiniciado durante o processamento."
    db.commit()
    return len(orphans)


def purge_expired_media(db: Session, retention_days: int, now: datetime | None = None) -> int:
    """
    Apaga os arquivos ORIGINAIS (vídeo/foto) enviados há mais de retention_days.
    As linhas do banco, os resultados e as imagens reduzidas dos frames ficam.
    Retorna quantos arquivos foram apagados.
    """
    now = now or datetime.now(timezone.utc)
    # uploaded_at é gravado em UTC, mas o SQLite devolve sem fuso.
    cutoff = (now - timedelta(days=retention_days)).replace(tzinfo=None)

    removed = 0
    for video in video_repository.list_uploaded_before(db, cutoff):
        path = Path(video.file_path)
        # Só apaga dentro de storage/: o caminho vem do banco, e esta função
        # não deve virar um jeito de remover arquivo fora dele.
        if STORAGE_ROOT in path.resolve().parents and path.exists():
            path.unlink()
            removed += 1
    return removed


def _build_frame_analyses(
    inspection_id: int,
    segment: Segment,
    frame_results: list[FrameResult],
    km_start: float | None = None,
    km_end: float | None = None,
) -> list[FrameAnalysis]:
    """
    Monta (sem gravar) o detalhe por frame. O intervalo de km sobre o qual os
    frames são interpolados vem de:
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

    frame_analyses = []
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

        frame_analyses.append(FrameAnalysis(
            inspection_id=inspection_id,
            frame_index=frame_result.frame_index,
            timestamp_seconds=frame_result.timestamp_seconds,
            estimated_km=estimated_km,
            green_percent=frame_result.green_percent,
            priority=frame_result.priority,
            confidence=frame_result.confidence,
            image_path=image_path,
        ))
    return frame_analyses


def _remove_file(path: str | Path) -> None:
    Path(path).unlink(missing_ok=True)


def _discard_frame_images(frame_image_dir: Path) -> None:
    shutil.rmtree(frame_image_dir, ignore_errors=True)


def reset_all_analyses(db: Session) -> None:
    """
    Apaga todas as inspeções, frame_analyses e vídeos (e os arquivos de
    mídia correspondentes em storage/) — sem tocar em roads/segments. Feito
    pra testes: voltar o mapa/faixa de blocos pro estado "tudo cinza, sem
    inspeção" sem precisar recadastrar as rodovias.
    """
    frame_analysis_repository.delete_all(db)
    inspection_repository.delete_all(db)
    video_repository.delete_all(db)
    db.commit()

    for storage_dir in (VIDEO_STORAGE_DIR, IMAGE_STORAGE_DIR, FRAME_STORAGE_DIR):
        if not storage_dir.exists():
            continue
        for entry in storage_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
