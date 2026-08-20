from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(road.router)
app.include_router(segment.router)
app.include_router(inspection.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
