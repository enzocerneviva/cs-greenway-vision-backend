# Ponto de entrada do Vision Engine: orquestra frame_extractor, o pré-filtro
# de vegetação e o modelo de classificação treinado.
#
# Contrato: analyze(video_path) -> AnalysisResult (docs/architecture.md §8).
# Este módulo não deve depender de FastAPI, SQLAlchemy ou qualquer detalhe
# do backend — recebe um caminho de vídeo, devolve um resultado.

from functools import lru_cache
from pathlib import Path
from typing import Optional

import cv2
import joblib
from PIL import Image

from app.vision.analysis_result import AnalysisError, AnalysisResult, FrameResult
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



@lru_cache(maxsize=1)
def _get_classifier():
    # Carregado na primeira classificação (e só uma vez), não no import:
    # importar o engine fica barato — a API sobe rápido e os testes não
    # precisam do arquivo do modelo.
    return joblib.load(MODEL_PATH)


def _frame_to_pil(frame) -> Image.Image:
    # cv2 devolve o frame em BGR; o extrator de embeddings espera RGB.
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_frame)


def _predict_with_confidence(embedding) -> tuple[str, float]:
    """Classe escolhida e a fração de votos que ela recebeu (a "confiança")."""
    classifier = _get_classifier()
    probabilities = classifier.predict_proba([embedding])[0]
    # classes_ está em ordem alfabética (HIGH, LOW, MEDIUM) — o índice da maior
    # probabilidade é o índice da classe correspondente.
    best = int(probabilities.argmax())
    return str(classifier.classes_[best]), round(float(probabilities[best]), 4)


def _classify_frame(frame) -> tuple[str, float]:
    # Import aqui dentro de propósito: o torch/torchvision demoram a importar
    # e só são necessários quando um frame realmente vai ser classificado.
    from app.vision.feature_extractor_cnn import extract_embedding

    return _predict_with_confidence(extract_embedding(_frame_to_pil(frame)))


def _save_display_frame(frame, destination: Path, max_width: int, jpeg_quality: int) -> None:
    # Versão reduzida só pra exibição; o frame em resolução cheia já cumpriu
    # seu papel (ir pro modelo) e não é guardado.
    height, width = frame.shape[:2]
    if width > max_width:
        new_height = round(height * max_width / width)
        frame = cv2.resize(frame, (max_width, new_height), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])


def analyze(
    file_path: str,
    media_type: str = "video",
    frame_image_dir: Optional[Path] = None,
    frame_max_width: int = 640,
    frame_jpeg_quality: int = 80,
) -> AnalysisResult:
    """
    frame_image_dir, se passado, faz cada frame classificado ser salvo como
    JPEG nesse diretório ({frame_index}.jpg), reduzido a no máximo
    frame_max_width pixels de largura — usado pra dar suporte à
    visualização de frame analysis no frontend. Opcional porque o vision
    engine deve continuar utilizável (e testável) sem depender de onde o
    backend guarda arquivos.
    """
    if frame_image_dir is not None:
        frame_image_dir.mkdir(parents=True, exist_ok=True)

    if media_type == "image":
        frame = cv2.imread(file_path)
        if frame is None:
            raise AnalysisError("Não foi possível abrir a imagem (arquivo inválido ou corrompido)")
        # imagem não tem timestamp real — é um único ponto, não uma sequência no tempo
        frames = [(frame, 0.0)]
    else:
        try:
            frames = extrair_frames(file_path)
        except ValueError as exc:
            raise AnalysisError("Não foi possível abrir o vídeo (arquivo inválido ou corrompido)") from exc

    if not frames:
        raise AnalysisError("Nenhum frame foi extraído do vídeo")

    frame_results = []
    for index, (frame, timestamp_seconds) in enumerate(frames):
        try:
            green_percent = detectar_vegetacao(frame)

            # Frame sem verde suficiente não passa pelo classificador — LOW por
            # convenção (mesmo raciocínio de antes), mas ainda vira um ponto no
            # rastro, pra a visualização por frame ficar contínua.
            if green_percent >= PRE_FILTER_MIN_GREEN_PERCENT:
                priority, confidence = _classify_frame(frame)
            else:
                # O modelo não avaliou este frame: sem confiança a informar.
                priority, confidence = "LOW", None
        except (cv2.error, RuntimeError) as exc:
            raise AnalysisError(f"Falha ao processar o frame {index}") from exc

        image_path = None
        if frame_image_dir is not None:
            frame_file = frame_image_dir / f"{index}.jpg"
            _save_display_frame(frame, frame_file, frame_max_width, frame_jpeg_quality)
            image_path = frame_file.as_posix()

        frame_results.append(FrameResult(
            frame_index=index,
            timestamp_seconds=timestamp_seconds,
            green_percent=green_percent,
            priority=priority,
            confidence=confidence,
            image_path=image_path,
        ))

    worst_priority = max(frame_results, key=lambda fr: _PRIORITY_SEVERITY[fr.priority]).priority

    return AnalysisResult(
        priority=worst_priority,
        model_version=MODEL_VERSION,
        frame_results=frame_results,
    )
