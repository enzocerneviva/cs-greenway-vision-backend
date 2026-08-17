from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalysisResult:
    """
    Resultado padronizado de uma análise de vídeo pelo Vision Engine.

    measurement_value/measurement_unit ficam None quando o modelo não produz
    uma medida física real (caso do classificador v1, que prevê a prioridade
    direto da imagem, sem calibração de câmera).
    """

    priority: str
    model_version: str
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
