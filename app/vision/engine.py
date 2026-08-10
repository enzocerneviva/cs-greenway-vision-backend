# Ponto de entrada do motor de visão: orquestra frame_extractor, vegetation_detector e classifier

from app.vision.frame_extractor import extrair_frames
from app.vision.vegetation_detector import detectar_vegetacao
from app.vision.classifier import classificar_percentual


def analyze_video(caminho_video: str) -> dict:
    """
    Função principal do motor de visão. Recebe o caminho de um vídeo
    e retorna um dicionário com o resultado da análise de vegetação.
    """
    frames = extrair_frames(caminho_video)

    if not frames:
        raise ValueError("Nenhum frame foi extraído do vídeo.")

    percentuais = [detectar_vegetacao(frame) for frame in frames]

    percentual_medio = sum(percentuais) / len(percentuais)
    classificacao = classificar_percentual(percentual_medio)

    return {
        "percentual_vegetacao": round(percentual_medio, 2),
        "classificacao": classificacao,
        "frames_analisados": len(frames),
    }

