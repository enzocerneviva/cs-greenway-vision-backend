"""Vision Engine testado isolado: sem FastAPI, sem banco e sem carregar o modelo."""
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.vision import engine, frame_extractor
from app.vision.analysis_result import AnalysisError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def green_frame(width=64, height=48):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 1] = 255  # BGR: canal verde cheio -> bem dentro da faixa HSV de vegetação
    return frame


def black_frame():
    return np.zeros((48, 64, 3), dtype=np.uint8)


@pytest.fixture
def classify_sequence(monkeypatch):
    """Faz o classificador devolver, em ordem, as prioridades pedidas."""
    def install(priorities):
        remaining = iter(priorities)
        monkeypatch.setattr(engine, "_classify_frame", lambda frame: next(remaining))
    return install


def stub_frames(monkeypatch, frames):
    monkeypatch.setattr(engine, "extrair_frames", lambda path: [(f, float(i)) for i, f in enumerate(frames)])


# --- agregação e pré-filtro -------------------------------------------------

def test_video_priority_is_the_worst_case_among_frames(monkeypatch, classify_sequence):
    stub_frames(monkeypatch, [green_frame(), green_frame(), green_frame()])
    classify_sequence(["LOW", "HIGH", "MEDIUM"])

    result = engine.analyze("qualquer.mp4", "video")

    assert result.priority == "HIGH"
    assert [fr.priority for fr in result.frame_results] == ["LOW", "HIGH", "MEDIUM"]


def test_frame_without_enough_green_is_low_and_skips_the_model(monkeypatch):
    stub_frames(monkeypatch, [black_frame()])

    def must_not_run(frame):
        raise AssertionError("o classificador não deveria ser chamado")

    monkeypatch.setattr(engine, "_classify_frame", must_not_run)

    result = engine.analyze("qualquer.mp4", "video")

    assert result.priority == "LOW"
    assert result.frame_results[0].green_percent < engine.PRE_FILTER_MIN_GREEN_PERCENT


def test_frame_results_keep_index_and_timestamp(monkeypatch, classify_sequence):
    stub_frames(monkeypatch, [green_frame(), green_frame()])
    classify_sequence(["LOW", "LOW"])

    frames = engine.analyze("qualquer.mp4", "video").frame_results

    assert [(fr.frame_index, fr.timestamp_seconds) for fr in frames] == [(0, 0.0), (1, 1.0)]


# --- erros de entrada viram AnalysisError -----------------------------------

def test_video_that_cannot_be_opened_raises_analysis_error(monkeypatch):
    def cannot_open(path):
        raise ValueError("não abriu")

    monkeypatch.setattr(engine, "extrair_frames", cannot_open)

    with pytest.raises(AnalysisError):
        engine.analyze("qualquer.mp4", "video")


def test_video_without_frames_raises_analysis_error(monkeypatch):
    stub_frames(monkeypatch, [])

    with pytest.raises(AnalysisError):
        engine.analyze("qualquer.mp4", "video")


def test_corrupted_image_raises_analysis_error(tmp_path):
    corrupted = tmp_path / "lixo.jpg"
    corrupted.write_bytes(b"isto nao e uma imagem")

    with pytest.raises(AnalysisError):
        engine.analyze(str(corrupted), "image")


def test_opencv_failure_on_a_frame_raises_analysis_error(monkeypatch):
    stub_frames(monkeypatch, [green_frame()])

    def broken(frame):
        raise cv2.error("falha interna do OpenCV")

    monkeypatch.setattr(engine, "detectar_vegetacao", broken)

    with pytest.raises(AnalysisError):
        engine.analyze("qualquer.mp4", "video")


# --- imagens de exibição ----------------------------------------------------

def test_display_frame_is_downscaled_to_the_max_width(monkeypatch, classify_sequence, tmp_path):
    stub_frames(monkeypatch, [green_frame(width=1280, height=720)])
    classify_sequence(["LOW"])

    result = engine.analyze("x.mp4", "video", frame_image_dir=tmp_path, frame_max_width=640)

    saved = cv2.imread(result.frame_results[0].image_path)
    assert saved.shape[1] == 640
    assert saved.shape[0] == 360  # proporção mantida


def test_small_display_frame_is_not_upscaled(monkeypatch, classify_sequence, tmp_path):
    stub_frames(monkeypatch, [green_frame(width=320, height=240)])
    classify_sequence(["LOW"])

    result = engine.analyze("x.mp4", "video", frame_image_dir=tmp_path, frame_max_width=640)

    assert cv2.imread(result.frame_results[0].image_path).shape[1] == 320


def test_no_images_are_written_without_frame_image_dir(monkeypatch, classify_sequence):
    stub_frames(monkeypatch, [green_frame()])
    classify_sequence(["LOW"])

    assert engine.analyze("x.mp4", "video").frame_results[0].image_path is None


# --- carregamento preguiçoso ------------------------------------------------

def test_importing_the_engine_does_not_load_torch_nor_the_model():
    code = (
        "import sys; import app.vision.engine as e; "
        "print('torch' in sys.modules, e._get_classifier.cache_info().currsize)"
    )
    output = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert output == "False 0"


# --- extrator de frames -----------------------------------------------------

class FakeCapture:
    def __init__(self, fps, total_frames=3):
        self._fps = fps
        self._remaining = total_frames
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return self._fps

    def read(self):
        if self._remaining == 0:
            return False, None
        self._remaining -= 1
        return True, black_frame()

    def release(self):
        self.released = True


@pytest.mark.parametrize("fps", [0, -1.0])
def test_extractor_rejects_invalid_fps_instead_of_dividing_by_zero(monkeypatch, fps):
    capture = FakeCapture(fps)
    monkeypatch.setattr(frame_extractor.cv2, "VideoCapture", lambda path: capture)

    with pytest.raises(ValueError):
        frame_extractor.extrair_frames("x.mp4")

    assert capture.released


def test_extractor_handles_videos_below_one_fps(monkeypatch):
    monkeypatch.setattr(frame_extractor.cv2, "VideoCapture", lambda path: FakeCapture(fps=0.5, total_frames=3))

    frames = frame_extractor.extrair_frames("x.mp4", intervalo_segundos=1)

    assert len(frames) == 3  # intervalo mínimo de 1 frame, sem divisão por zero


def test_extractor_takes_one_frame_per_interval(monkeypatch):
    monkeypatch.setattr(frame_extractor.cv2, "VideoCapture", lambda path: FakeCapture(fps=2, total_frames=6))

    frames = frame_extractor.extrair_frames("x.mp4", intervalo_segundos=1)

    assert [timestamp for _, timestamp in frames] == [0.0, 1.0, 2.0]
