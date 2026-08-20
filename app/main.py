from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database.session import Base, engine
from app import models  # garante que todas as tabelas sejam registradas antes do create_all
from app.api.routes import road, segment, inspection

app = FastAPI(
    title="GreenWay Vision API",
    description="Backend da plataforma GreenWay Vision",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

# Serve os arquivos de storage/ (vídeos, imagens, frames extraídos) direto
# por URL — usado hoje pelo frontend pra mostrar as imagens dos frames
# analisados. Caminho ancorado na raiz do projeto, não no cwd do processo.
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

app.include_router(road.router)
app.include_router(segment.router)
app.include_router(inspection.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
