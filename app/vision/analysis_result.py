from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FrameResult:
    """Resultado da classificação de um único frame analisado."""

    frame_index: int
    timestamp_seconds: float
    green_percent: float
    priority: str


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
