# Responsável por abrir o vídeo e extrair frames em intervalos definidos


import cv2


def extrair_frames(caminho_video: str, intervalo_segundos: int = 1) -> list:
    """
    Recebe o caminho de um vídeo e retorna uma lista de tuplas
    (frame, timestamp_segundos) — o timestamp é a posição real desse frame
    dentro do arquivo de vídeo, extraindo 1 frame a cada 'intervalo_segundos'
    segundos.
    """
    video = cv2.VideoCapture(caminho_video)

    if not video.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {caminho_video}")

    fps = video.get(cv2.CAP_PROP_FPS)
    intervalo = int(fps * intervalo_segundos)

    frames_extraidos = []
    frame_atual = 0

    while True:
        sucesso, frame = video.read()

        if not sucesso:
            break

        if frame_atual % intervalo == 0:
            timestamp_segundos = frame_atual / fps
            frames_extraidos.append((frame, timestamp_segundos))

        frame_atual += 1

    video.release()

    return frames_extraidos
