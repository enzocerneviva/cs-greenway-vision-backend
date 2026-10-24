"""
Fixtures compartilhadas. A ideia central: cada teste roda com um banco SQLite
em memória próprio, pastas de storage temporárias e um Vision Engine falso —
então nenhum teste toca o greenway.db, o storage/ real nem carrega o modelo.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 — registra as tabelas em Base.metadata
from app.database.session import Base, get_db
from app.main import app
from app.models import Road, Segment
from app.services import inspection_service
from app.vision.analysis_result import AnalysisResult, FrameResult


@pytest.fixture
def engine():
    # StaticPool: uma única conexão compartilhada, necessária pra um SQLite em
    # memória ser visto por todas as Sessions (inclusive a da tarefa em
    # segundo plano, que roda em outra thread).
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Redireciona todo o storage do service para uma pasta temporária."""
    root = tmp_path.resolve()
    monkeypatch.setattr(inspection_service, "STORAGE_ROOT", root)
    monkeypatch.setattr(inspection_service, "VIDEO_STORAGE_DIR", root / "videos")
    monkeypatch.setattr(inspection_service, "IMAGE_STORAGE_DIR", root / "images")
    monkeypatch.setattr(inspection_service, "FRAME_STORAGE_DIR", root / "frames")
    return root


@pytest.fixture
def segment(db):
    road = Road(name="SP-000 (Teste)")
    db.add(road)
    db.commit()
    seg = Segment(road_id=road.id, km_start=10.0, km_end=12.0)
    db.add(seg)
    db.commit()
    return seg


def make_result(priorities=("LOW", "HIGH", "LOW", "LOW")) -> AnalysisResult:
    frames = [
        FrameResult(
            frame_index=i,
            timestamp_seconds=float(i),
            green_percent=10.0 * i,
            priority=p,
            confidence=None if i == 0 else round(0.5 + 0.1 * i, 2),
        )
        for i, p in enumerate(priorities)
    ]
    worst = max(priorities, key=["LOW", "MEDIUM", "HIGH"].index)
    return AnalysisResult(priority=worst, model_version="fake-v0", frame_results=frames)


@pytest.fixture
def fake_engine(monkeypatch):
    """
    Substitui vision_engine.analyze. O teste escolhe o que ele devolve:
    state.result = um AnalysisResult (sucesso) ou uma exceção (falha).
    Se pedirem frame_image_dir, grava um arquivo lá — pra provar a limpeza.
    """
    state = SimpleNamespace(result=make_result(), calls=[])

    def analyze(file_path, media_type, frame_image_dir=None, **kwargs):
        state.calls.append(SimpleNamespace(file_path=file_path, media_type=media_type, **kwargs))
        if frame_image_dir is not None:
            frame_image_dir.mkdir(parents=True, exist_ok=True)
            (frame_image_dir / "0.jpg").write_bytes(b"jpg")
        if isinstance(state.result, Exception):
            raise state.result
        return state.result

    monkeypatch.setattr(inspection_service.vision_engine, "analyze", analyze)
    return state


@pytest.fixture
def client(session_factory, storage, monkeypatch):
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # A tarefa em segundo plano abre a própria Session via SessionLocal.
    monkeypatch.setattr(inspection_service, "SessionLocal", session_factory)
    yield TestClient(app)
    app.dependency_overrides.clear()


def post_upload(client, segment_id, content_type="image/jpeg", filename="foto.jpg", content=b"x", **fields):
    """Envia um upload de inspeção (multipart), como o frontend faz."""
    return client.post(
        "/inspections",
        data={"segment_id": segment_id, **fields},
        files={"file": (filename, content, content_type)},
    )
