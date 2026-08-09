# Responsável por detectar vegetação em um frame usando HSV + máscara verde

import cv2
import numpy as np


# Valores de HSV calibrados manualmente com a imagem de teste (teste.png)
# usando trackbars. Caso a qualidade da detecção caia com fotos/vídeos
# diferentes (nova câmera, outro horário, vegetação diferente), esses
# valores podem precisar ser recalibrados.
H_MIN, H_MAX = 33, 95
S_MIN, S_MAX = 42, 255
V_MIN, V_MAX = 0, 255


def detectar_vegetacao(frame) -> float:
    """
    Recebe um frame (array numpy, no formato BGR) e retorna o percentual
    de vegetação detectado nesse frame (0 a 100).
    """
    frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    limite_inferior = np.array([H_MIN, S_MIN, V_MIN])
    limite_superior = np.array([H_MAX, S_MAX, V_MAX])

    mascara = cv2.inRange(frame_hsv, limite_inferior, limite_superior)

    pixels_vegetacao = cv2.countNonZero(mascara)
    altura, largura = mascara.shape
    total_pixels = altura * largura

    percentual_vegetacao = (pixels_vegetacao / total_pixels) * 100

    return percentual_vegetacao

