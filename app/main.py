import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy.exc import OperationalError

from app.core.config import CORS_ORIGINS, VIDEO_RETENTION_DAYS
from app.database.session import SessionLocal
from app.api.routes import analytics, inspection, meta, road, schedule, segment
from app.services import inspection_service

logger = logging.getLogger(__name__)


def _startup_maintenance() -> None:
    """Roda uma vez, na subida da API."""
    db = SessionLocal()
    try:
        orphaned = inspection_service.fail_orphaned_processing(db)
        if orphaned:
            logger.warning("%d inspeção(ões) em PROCESSING marcada(s) como FAILED (reinício).", orphaned)
        if VIDEO_RETENTION_DAYS is not None:
            removed = inspection_service.purge_expired_media(db, VIDEO_RETENTION_DAYS)
            logger.info("Retenção: %d arquivo(s) original(is) apagado(s).", removed)
    except OperationalError:
        # Banco sem tabelas (migrações não aplicadas): avisa claramente em vez
        # de derrubar a API com um erro de SQL.
        logger.error("Banco sem o esquema esperado. Rode: alembic upgrade head")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup_maintenance()
    yield


app = FastAPI(
    title="GreenWay Vision API",
    description="Backend da plataforma GreenWay Vision",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# As tabelas NÃO são mais criadas aqui: quem cria/atualiza o esquema do banco
# é o Alembic (alembic upgrade head) — ver docs/plans/plano-v2.md, item 1.

# Serve os arquivos de storage/ (vídeos, imagens, frames extraídos) direto
# por URL — usado hoje pelo frontend pra mostrar as imagens dos frames
# analisados. Caminho ancorado na raiz do projeto, não no cwd do processo.
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

app.include_router(road.router)
app.include_router(segment.router)
app.include_router(inspection.router)
app.include_router(schedule.router)
app.include_router(analytics.router)
app.include_router(meta.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
