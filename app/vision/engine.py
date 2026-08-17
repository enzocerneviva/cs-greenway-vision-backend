# Ponto de entrada do Vision Engine: orquestra frame_extractor, o pré-filtro
# de vegetação e o modelo de classificação.
#
# Contrato: analyze(video_path) -> AnalysisResult (docs/architecture.md §8).
# Este módulo não deve depender de FastAPI, SQLAlchemy ou qualquer detalhe
# do backend — recebe um caminho de vídeo, devolve um resultado.

from app.vision.frame_extractor import extrair_frames
from app.vision.vegetation_detector import detectar_vegetacao
from app.vision.analysis_result import AnalysisResult

# Modelo treinável ainda não existe (entra quando o dataset rotulado
# estiver disponível). Até lá, o resultado é simulado.
MODEL_VERSION = "mock-v0"

# % mínimo de "verde" num frame pra considerá-lo relevante o suficiente
# pra valer a pena classificar. Valor provisório — será calibrado quando
# houver dados reais rotulados.
PRE_FILTER_MIN_GREEN_PERCENT = 5.0


def _classify_frame_mock(frame) -> str:
    """
    Substitui temporariamente o modelo treinável. Retorna sempre a mesma
    classificação simulada, só para validar o pipeline ponta a ponta antes
    do modelo real (embeddings de CNN pré-treinada + classificador
    scikit-learn) estar pronto.
    """
    return "MEDIUM"


def analyze(video_path: str) -> AnalysisResult:
    frames = extrair_frames(video_path)

    if not frames:
        raise ValueError(f"Nenhum frame foi extraído do vídeo: {video_path}")

    relevant_frames = [
        frame for frame in frames
        if detectar_vegetacao(frame) >= PRE_FILTER_MIN_GREEN_PERCENT
    ]

    if not relevant_frames:
        return AnalysisResult(priority="LOW", model_version=MODEL_VERSION)

    priority = _classify_frame_mock(relevant_frames[0])

    return AnalysisResult(priority=priority, model_version=MODEL_VERSION)
