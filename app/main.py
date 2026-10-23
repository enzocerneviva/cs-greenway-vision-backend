from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import CORS_ORIGINS
from app.api.routes import road, segment, inspection, meta

app = FastAPI(
    title="GreenWay Vision API",
    description="Backend da plataforma GreenWay Vision",
    version="0.1.0"
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
app.include_router(meta.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
