"""Fluxo do upload: aceitar (202) -> processar em segundo plano -> DONE/FAILED."""
import pytest
from sqlalchemy import event, func

from app.models import FrameAnalysis, Inspection, Video
from app.repositories import frame_analysis_repository, inspection_repository
from app.services import inspection_service
from app.vision.analysis_result import AnalysisError
from tests.conftest import make_result, post_upload


def get_inspection(client, inspection_id):
    response = client.get(f"/inspections/{inspection_id}")
    assert response.status_code == 200
    return response.json()


# --- caminho feliz ----------------------------------------------------------

def test_upload_responds_202_processing_then_ends_done(client, segment, fake_engine):
    response = post_upload(client, segment.id, direction="CAPITAL")

    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSING"  # o que o cliente recebe na hora

    done = get_inspection(client, response.json()["id"])  # depois que a tarefa rodou
    assert done["status"] == "DONE"
    assert done["priority"] == "HIGH"  # pior caso entre os frames
    assert done["model_version"] == "fake-v0"
    assert done["direction"] == "CAPITAL"
    assert done["failure_reason"] is None
    assert done["analyzed_at"].endswith("Z")
    assert len(done["frame_analyses"]) == 4


def test_frame_confidence_is_stored_and_returned(client, segment, fake_engine):
    response = post_upload(client, segment.id)

    frames = get_inspection(client, response.json()["id"])["frame_analyses"]
    # o 1º frame não passou pelo modelo (pré-filtro): sem confiança
    assert [f["confidence"] for f in frames] == [None, 0.6, 0.7, 0.8]


def test_engine_receives_display_frame_settings(client, segment, fake_engine):
    post_upload(client, segment.id)

    call = fake_engine.calls[0]
    assert call.media_type == "image"
    assert call.frame_max_width == 640
    assert call.frame_jpeg_quality == 80


# --- posição estimada (interpolação) ---------------------------------------

def test_km_is_interpolated_inside_the_informed_range(client, segment, fake_engine):
    response = post_upload(client, segment.id, km_start="10", km_end="12")

    frames = get_inspection(client, response.json()["id"])["frame_analyses"]
    assert [f["estimated_km"] for f in frames] == [10.0, 10.5, 11.0, 11.5]
    # intervalo semiaberto [10, 12): o último frame nunca cai exatamente em 12
    assert all(f["estimated_km"] < 12.0 for f in frames)


def test_km_uses_the_whole_segment_when_no_range_is_informed(client, segment, fake_engine):
    response = post_upload(client, segment.id)

    frames = get_inspection(client, response.json()["id"])["frame_analyses"]
    assert frames[0]["estimated_km"] == segment.km_start
    assert frames[-1]["estimated_km"] < segment.km_end


def test_photo_with_equal_km_start_and_end_sits_on_that_point(client, segment, fake_engine):
    fake_engine.result = make_result(("MEDIUM",))

    response = post_upload(client, segment.id, km_start="11.2", km_end="11.2")

    frames = get_inspection(client, response.json()["id"])["frame_analyses"]
    assert [f["estimated_km"] for f in frames] == [11.2]


# --- falhas de análise -----------------------------------------------------

def test_unreadable_media_becomes_failed_with_reason(client, segment, fake_engine, storage):
    fake_engine.result = AnalysisError("Não foi possível abrir o vídeo")

    response = post_upload(client, segment.id, direction="INTERIOR")

    failed = get_inspection(client, response.json()["id"])
    assert failed["status"] == "FAILED"
    assert failed["failure_reason"] == "Não foi possível abrir o vídeo"
    assert failed["direction"] == "INTERIOR"
    assert failed["frame_analyses"] == []
    # as imagens parciais dos frames não ficam órfãs em disco
    assert not (storage / "frames").exists() or list((storage / "frames").iterdir()) == []


def test_code_bug_in_background_becomes_failed_without_leaking_details(client, segment, fake_engine):
    fake_engine.result = TypeError("detalhe-tecnico-interno")

    response = post_upload(client, segment.id)

    failed = get_inspection(client, response.json()["id"])
    assert failed["status"] == "FAILED"
    assert "detalhe-tecnico-interno" not in failed["failure_reason"]
    assert "log do servidor" in failed["failure_reason"]


# --- gravação atômica -------------------------------------------------------

def test_failure_while_saving_frames_leaves_no_partial_inspection(
    client, segment, fake_engine, storage, session_factory, monkeypatch
):
    def boom(db, frame_analyses):
        raise RuntimeError("falha no meio da gravação")

    monkeypatch.setattr(frame_analysis_repository, "create_many", boom)

    response = post_upload(client, segment.id)

    failed = get_inspection(client, response.json()["id"])
    assert failed["status"] == "FAILED"  # nunca "DONE com frames faltando"
    assert failed["priority"] is None  # o resultado parcial foi desfeito
    with session_factory() as db:
        assert db.query(FrameAnalysis).count() == 0
    assert list((storage / "frames").iterdir()) == []  # sem imagens órfãs


def test_processing_step_does_a_single_commit(client, segment, fake_engine, engine, db):
    inspection = inspection_service.accept_inspection(
        db, segment.id, _upload("foto.jpg", "image/jpeg")
    )

    commits = []
    event.listen(engine, "commit", lambda conn: commits.append(1))
    inspection_service.process_inspection(inspection.id)

    assert len(commits) == 1  # Inspection + 4 FrameAnalysis, numa transação só


def test_failure_while_accepting_removes_the_saved_file(client, segment, storage, monkeypatch, session_factory):
    def boom(db, inspection):
        raise RuntimeError("falha ao gravar a inspeção")

    monkeypatch.setattr(inspection_repository, "create", boom)

    with pytest.raises(RuntimeError):
        post_upload(client, segment.id)

    with session_factory() as db:
        assert db.query(Video).count() == 0  # o Video também foi desfeito
    assert list((storage / "images").iterdir()) == []  # e o arquivo não ficou órfão


# --- validações de entrada --------------------------------------------------

def test_unsupported_file_type_is_rejected_with_400(client, segment, fake_engine, session_factory):
    response = post_upload(client, segment.id, content_type="text/plain", filename="a.txt")

    assert response.status_code == 400
    with session_factory() as db:
        assert db.query(Inspection).count() == 0


def test_file_larger_than_the_limit_is_rejected_with_413_and_deleted(
    client, segment, fake_engine, storage, monkeypatch
):
    monkeypatch.setattr(inspection_service, "MAX_IMAGE_SIZE_BYTES", 10)

    response = post_upload(client, segment.id, content=b"x" * 100)

    assert response.status_code == 413
    assert list((storage / "images").iterdir()) == []


def test_unknown_segment_returns_404_and_saves_nothing(client, fake_engine, storage):
    response = post_upload(client, 9999)

    assert response.status_code == 404
    assert not (storage / "images").exists()


def test_invalid_direction_is_rejected_with_422(client, segment, fake_engine):
    response = post_upload(client, segment.id, direction="NORTE")

    assert response.status_code == 422


def test_dates_are_serialized_as_utc_with_z(client, segment, fake_engine):
    response = post_upload(client, segment.id)

    assert response.json()["created_at"].endswith("Z")


# --- reset administrativo ---------------------------------------------------

def test_reset_is_forbidden_when_the_flag_is_off(client, segment, fake_engine, monkeypatch):
    post_upload(client, segment.id)
    monkeypatch.setattr("app.api.routes.inspection.ADMIN_RESET_ENABLED", False)

    response = client.delete("/inspections")

    assert response.status_code == 403
    assert len(client.get("/inspections").json()) == 1  # nada foi apagado


def test_reset_deletes_everything_when_the_flag_is_on(client, segment, fake_engine, storage):
    post_upload(client, segment.id)

    response = client.delete("/inspections")

    assert response.status_code == 204
    assert client.get("/inspections").json() == []
    assert list((storage / "images").iterdir()) == []


def test_analysis_of_an_inspection_deleted_meanwhile_is_discarded(client, segment, fake_engine):
    # reset aconteceu entre o 202 e o início da análise: não deve explodir
    inspection_service.process_inspection(12345)

    assert fake_engine.calls == []


def _upload(filename, content_type):
    import io

    from starlette.datastructures import Headers, UploadFile

    return UploadFile(io.BytesIO(b"x"), filename=filename, headers=Headers({"content-type": content_type}))
