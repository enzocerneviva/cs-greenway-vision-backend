from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import ADMIN_RESET_ENABLED, BLOCK_SIZE_KM, LOW_CONFIDENCE_THRESHOLD, TIMEZONE

router = APIRouter(tags=["meta"])


class MetaResponse(BaseModel):
    timezone: str
    block_size_km: float
    admin_reset_enabled: bool
    low_confidence_threshold: float


@router.get("/meta", response_model=MetaResponse)
def get_meta():
    """Como o backend está configurado — o frontend usa pra, por exemplo,
    esconder o botão "Resetar análises" quando o reset está desativado."""
    return MetaResponse(
        timezone=TIMEZONE,
        block_size_km=BLOCK_SIZE_KM,
        admin_reset_enabled=ADMIN_RESET_ENABLED,
        low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
    )
