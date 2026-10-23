from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import ADMIN_RESET_ENABLED
from app.database.session import get_db
from app.schemas.inspection import InspectionResponse
from app.schemas.types import Direction
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


@router.post("", response_model=InspectionResponse, status_code=202)
def create_inspection(
    background_tasks: BackgroundTasks,
    segment_id: int = Form(...),
    file: UploadFile = File(...),
    km_start: Optional[float] = Form(None),
    km_end: Optional[float] = Form(None),
    direction: Optional[Direction] = Form(None),
    db: Session = Depends(get_db),
):
    """
    km_start/km_end: intervalo exato (opcional) que o arquivo cobre —
    necessário porque nem todo vídeo cobre o trecho inteiro (um vídeo de
    poucos segundos pode representar só 500m de uma rodovia de 150km).
    Quando informado, os frames são interpolados dentro desse intervalo em
    vez de km_start/km_end do Segment inteiro. Foto usa km_start == km_end
    (um único ponto). Se nenhum dos dois vier, mantém o comportamento
    antigo: interpola sobre o trecho inteiro.

    direction: sentido da pista ("CAPITAL" ou "INTERIOR") — necessário pra
    saber de qual lado da rodovia é a inspeção, já que ida e volta podem
    ter condições de vegetação bem diferentes.

    Responde 202 na hora, com a inspeção em status PROCESSING: a análise roda
    em segundo plano. O cliente acompanha com GET /inspections/{id} até o
    status virar DONE ou FAILED (e, se FAILED, ler failure_reason).
    """
    inspection = inspection_service.accept_inspection(db, segment_id, file, direction=direction)
    background_tasks.add_task(
        inspection_service.process_inspection, inspection.id, km_start, km_end
    )
    return inspection


@router.delete("", status_code=204)
def reset_inspections(db: Session = Depends(get_db)):
    """
    Apaga todas as inspeções/frame_analyses/vídeos (e os arquivos em
    storage/) — não mexe em roads/segments. Uso previsto: voltar o
    ambiente de testes pro estado "tudo cinza, sem inspeção" sem precisar
    recadastrar as rodovias.

    Só funciona com ADMIN_RESET_ENABLED ligado (app/core/config.py); desligado,
    responde 403.
    """
    if not ADMIN_RESET_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="O reset de análises está desativado neste ambiente (ADMIN_RESET_ENABLED=false).",
        )
    inspection_service.reset_all_analyses(db)
