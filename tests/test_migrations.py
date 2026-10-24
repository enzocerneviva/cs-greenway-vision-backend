"""Migrações do Alembic aplicadas de verdade, em bancos temporários."""
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def alembic(db_path: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite:///{db_path.as_posix()}", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )


def columns(db_path: Path, table: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[1] for row in conn.execute(f"pragma table_info({table})")]


def test_upgrade_head_builds_the_full_schema_on_an_empty_database(tmp_path):
    db_path = tmp_path / "novo.db"

    alembic(db_path, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    assert {"roads", "segments", "videos", "inspections", "frame_analyses"} <= tables
    assert "confidence" in columns(db_path, "frame_analyses")
    assert "failure_reason" in columns(db_path, "inspections")


def test_confidence_migration_keeps_existing_rows(tmp_path):
    """O cenário real: um banco já em uso (versão 0001) recebe a coluna nova sem perder dados."""
    db_path = tmp_path / "antigo.db"
    alembic(db_path, "upgrade", "0001")
    assert "confidence" not in columns(db_path, "frame_analyses")
    with sqlite3.connect(db_path) as conn:
        conn.execute("insert into roads (id, name) values (1, 'R')")
        conn.execute("insert into segments (id, road_id, km_start, km_end) values (1, 1, 0, 5)")
        conn.execute("insert into videos (id, segment_id, file_path, original_filename, media_type) values (1, 1, 'f', 'f', 'image')")
        conn.execute("insert into inspections (id, video_id, status) values (1, 1, 'DONE')")
        conn.execute(
            "insert into frame_analyses (id, inspection_id, frame_index, timestamp_seconds, estimated_km, green_percent, priority) "
            "values (1, 1, 0, 0.0, 1.5, 12.0, 'LOW')"
        )

    alembic(db_path, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select priority, estimated_km, confidence from frame_analyses").fetchone()
    assert row == ("LOW", 1.5, None)  # dado antigo intacto; confiança nula


def test_downgrade_removes_the_confidence_column(tmp_path):
    db_path = tmp_path / "volta.db"
    alembic(db_path, "upgrade", "head")

    alembic(db_path, "downgrade", "0001")

    assert "confidence" not in columns(db_path, "frame_analyses")
