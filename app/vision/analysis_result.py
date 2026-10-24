from dataclasses import dataclass, field
from typing import List, Optional


class AnalysisError(Exception):
    """
    A mídia enviada não pôde ser analisada (arquivo corrompido, sem frames,
    falha ao processar um frame). É o único erro que o Vision Engine promete
    levantar por problema na entrada — assim quem chama não precisa conhecer
    OpenCV nem PyTorch pra decidir o que tratar.
    """


@dataclass
class FrameResult:
    """Resultado da classificação de um único frame analisado."""

    frame_index: int
    timestamp_seconds: float
    green_percent: float
    priority: str
    # Fração das árvores do RandomForest que votaram na classe escolhida
    # (0 a 1) — um sinal RELATIVO de certeza, não uma probabilidade calibrada.
    # None quando o modelo não avaliou o frame (o pré-filtro de cor já o
    # classificou como LOW).
    confidence: Optional[float] = None
    # Caminho (relativo à raiz do projeto, estilo storage/frames/...) da
    # imagem do frame salva em disco — None se quem chamou analyze() não
    # pediu pra persistir os frames (ex.: testes do vision engine isolado).
    image_path: Optional[str] = None


@dataclass
class AnalysisResult:
    """
    Resultado padronizado de uma análise de vídeo/imagem pelo Vision Engine.

    measurement_value/measurement_unit ficam None quando o modelo não produz
    uma medida física real (caso do classificador v1, que prevê a prioridade
    direto da imagem, sem calibração de câmera).

    frame_results traz o detalhe por frame (usado pelo backend pra montar o
    rastro de FrameAnalysis) — priority é o agregado (pior caso entre os
    frames), não uma média.
    """

    priority: str
    model_version: str
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
    frame_results: List[FrameResult] = field(default_factory=list)
