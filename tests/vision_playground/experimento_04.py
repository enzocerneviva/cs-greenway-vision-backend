import cv2
import os

# Abrir o vídeo
video = cv2.VideoCapture("video_teste.mp4")

# Descobrir o FPS
fps = video.get(cv2.CAP_PROP_FPS)

# Criar a pasta para os frames (não precisa criar, já existe, mas não tem problema deixar aqui)
os.makedirs("frames_extraidos", exist_ok=True)

# Extrair 1 frame por segundo
intervalo = int(fps)
frame_atual = 0
numero_frame = 0

while True:
    sucesso, frame = video.read()

    if not sucesso:
        break

    # Salvar 1 frame a cada 1 segundo
    if frame_atual % intervalo == 0:
        nome_arquivo = f"frames_extraidos/frame_{numero_frame:04d}.jpg"
        cv2.imwrite(nome_arquivo, frame)
        print(f"Frame salvo: {nome_arquivo}")
        numero_frame += 1

    frame_atual += 1

# Liberar o vídeo
video.release()

print("Extração concluída!")