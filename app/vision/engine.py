# Ponto de entrada do Vision Engine: orquestra frame_extractor, o pré-filtro
# de vegetação e o modelo de classificação treinado.
#
# Contrato: analyze(video_path) -> AnalysisResult (docs/architecture.md §8).
# Este módulo não deve depender de FastAPI, SQLAlchemy ou qualquer detalhe
# do backend — recebe um caminho de vídeo, devolve um resultado.

from pathlib import Path
from typing import Optional

import cv2
import joblib
from PIL import Image

from app.vision.analysis_result import AnalysisResult, FrameResult
from app.vision.feature_extractor_cnn import extract_embedding
from app.vision.frame_extractor import extrair_frames
from app.vision.vegetation_detector import detectar_vegetacao

# Modelo treinado em data/mapillary/train_classifier.py sobre o dataset
# rotulado do Mapillary (v1 — baseline aproximado, ver docs/architecture.md §8).
MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "mapillary" / "model" / "classifier.joblib"
MODEL_VERSION = "mapillary-v1-randomforest"

# % mínimo de "verde" num frame pra considerá-lo relevante o suficiente
# pra valer a pena classificar.
PRE_FILTER_MIN_GREEN_PERCENT = 5.0

# Ordem de severidade, usada pra escolher o pior caso entre os frames
# relevantes de um vídeo — mais seguro superestimar a prioridade do trecho
# do que deixar passar um ponto realmente crítico visto em só alguns frames.
_PRIORITY_SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

_classifier = joblib.load(MODEL_PATH)


def _frame_to_pil(frame) -> Image.Image:
    # cv2 devolve o frame em BGR; o extrator de embeddings espera RGB.
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_frame)


def _classify_frame(frame) -> str:
    embedding = extract_embedding(_frame_to_pil(frame))
    return _classifier.predict([embedding])[0]


def analyze(
    file_path: str,
    media_type: str = "video",
    frame_image_dir: Optional[Path] = None,
) -> AnalysisResult:
    """
    frame_image_dir, se passado, faz cada frame classificado ser salvo como
    JPEG nesse diretório ({frame_index}.jpg) — usado pra dar suporte à
    visualização de frame analysis no frontend. Opcional porque o vision
    engine deve continuar utilizável (e testável) sem depender de onde o
    backend guarda arquivos.
    """
    if frame_image_dir is not None:
        frame_image_dir.mkdir(parents=True, exist_ok=True)

    if media_type == "image":
        frame = cv2.imread(file_path)
        if frame is None:
            raise ValueError(f"Não foi possível abrir a imagem: {file_path}")
        # imagem não tem timestamp real — é um único ponto, não uma sequência no tempo
        frames = [(frame, 0.0)]
    else:
        frames = extrair_frames(file_path)

    if not frames:
        raise ValueError(f"Nenhum frame foi extraído do vídeo: {file_path}")

    frame_results = []
    for index, (frame, timestamp_seconds) in enumerate(frames):
        green_percent = detectar_vegetacao(frame)

        # Frame sem verde suficiente não passa pelo classificador — LOW por
        # convenção (mesmo raciocínio de antes), mas ainda vira um ponto no
        # rastro, pra a visualização por frame ficar contínua.
        if green_percent >= PRE_FILTER_MIN_GREEN_PERCENT:
            priority = _classify_frame(frame)
        else:
            priority = "LOW"

        image_path = None
        if frame_image_dir is not None:
            frame_file = frame_image_dir / f"{index}.jpg"
            cv2.imwrite(str(frame_file), frame)
            image_path = frame_file.as_posix()

        frame_results.append(FrameResult(
            frame_index=index,
            timestamp_seconds=timestamp_seconds,
            green_percent=green_percent,
            priority=priority,
            image_path=image_path,
        ))

    worst_priority = max(frame_results, key=lambda fr: _PRIORITY_SEVERITY[fr.priority]).priority

    return AnalysisResult(
        priority=worst_priority,
        model_version=MODEL_VERSION,
        frame_results=frame_results,
    )
