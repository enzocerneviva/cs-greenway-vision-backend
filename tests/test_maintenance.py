"""Rotinas de manutenção da subida da API e rotas que confirmam a própria transação."""
from datetime import datetime, timedelta, timezone

from app.models import Inspection, Video
from app.services import geocoding_service, inspection_service


def _video(db, segment, path, uploaded_at):
    video = Video(
        segment_id=segment.id,
        file_path=str(path),
        original_filename=path.name,
        media_type="video",
        uploaded_at=uploaded_at,
    )
    db.add(video)
    db.commit()
    return video


# --- inspeções órfãs --------------------------------------------------------

def test_processing_inspections_are_failed_on_startup(db, segment, storage):
    video = _video(db, segment, storage / "a.mp4", datetime.now(timezone.utc))
    db.add(Inspection(video_id=video.id, status="PROCESSING"))
    db.commit()
    frames_dir = storage / "frames" / str(video.id)
    frames_dir.mkdir(parents=True)
    (frames_dir / "0.jpg").write_bytes(b"jpg")

    count = inspection_service.fail_orphaned_processing(db)

    inspection = db.query(Inspection).one()
    assert count == 1
    assert inspection.status == "FAILED"
    assert "reiniciado" in inspection.failure_reason
    assert not frames_dir.exists()


def test_finished_inspections_are_not_touched_on_startup(db, segment, storage):
    video = _video(db, segment, storage / "a.mp4", datetime.now(timezone.utc))
    db.add(Inspection(video_id=video.id, status="DONE", priority="LOW"))
    db.commit()

    assert inspection_service.fail_orphaned_processing(db) == 0
    assert db.query(Inspection).one().status == "DONE"


# --- retenção de arquivos originais ----------------------------------------

def test_purge_deletes_only_originals_older_than_the_retention(db, segment, storage):
    old_file = storage / "old.mp4"
    new_file = storage / "new.mp4"
    old_file.write_bytes(b"x")
    new_file.write_bytes(b"x")
    now = datetime.now(timezone.utc)
    old_video = _video(db, segment, old_file, now - timedelta(days=40))
    _video(db, segment, new_file, now - timedelta(days=2))

    removed = inspection_service.purge_expired_media(db, retention_days=30, now=now)

    assert removed == 1
    assert not old_file.exists()
    assert new_file.exists()
    assert db.get(Video, old_video.id) is not None  # a linha do banco fica


def test_purge_never_deletes_files_outside_storage(db, segment, storage, tmp_path_factory):
    outside = tmp_path_factory.mktemp("fora") / "importante.mp4"
    outside.write_bytes(b"x")
    now = datetime.now(timezone.utc)
    _video(db, segment, outside, now - timedelta(days=400))

    removed = inspection_service.purge_expired_media(db, retention_days=30, now=now)

    assert removed == 0
    assert outside.exists()


def test_purge_ignores_a_file_that_is_already_gone(db, segment, storage):
    now = datetime.now(timezone.utc)
    _video(db, segment, storage / "sumiu.mp4", now - timedelta(days=100))

    assert inspection_service.purge_expired_media(db, retention_days=30, now=now) == 0


# --- rotas que confirmam a própria transação --------------------------------
# (os repositories só fazem flush; sem o commit na rota, nada seria gravado)

def test_roads_and_segments_are_persisted(client, monkeypatch):
    monkeypatch.setattr(geocoding_service, "fetch_road_geometry", lambda name: None)

    road = client.post("/roads", json={"name": "SP-999 (Teste)"})
    assert road.status_code == 200
    segment = client.post("/segments", json={"road_id": road.json()["id"], "km_start": 1.0, "km_end": 5.0})
    assert segment.status_code == 200

    assert [r["name"] for r in client.get("/roads").json()] == ["SP-999 (Teste)"]
    assert len(client.get("/segments").json()) == 1


def test_segment_location_update_is_persisted(client, segment):
    response = client.patch(
        f"/segments/{segment.id}/location",
        json={"lat_start": -22.9, "lng_start": -47.0, "lat_end": -22.8, "lng_end": -46.9},
    )

    assert response.status_code == 200
    stored = client.get("/segments").json()[0]
    assert stored["lat_start"] == -22.9


def test_meta_exposes_the_configuration(client):
    meta = client.get("/meta").json()

    assert meta["timezone"] == "America/Sao_Paulo"
    assert meta["block_size_km"] == 0.5
    assert isinstance(meta["admin_reset_enabled"], bool)
