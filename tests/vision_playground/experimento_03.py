import cv2

# Abrir o vídeo
video = cv2.VideoCapture("video_teste.mp4")

# Descobrir o FPS do vídeo
fps = video.get(cv2.CAP_PROP_FPS)

# Descobrir a quantidade total de frames
total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)

# Calcular a duração aproximada do vídeo
duracao = total_frames / fps

print("FPS:", fps)
print("Total de frames:", total_frames)
print("Duração do vídeo:", duracao, "segundos")

# Pegar 1 frame a cada 1 segundo
intervalo = int(fps)

frame_atual = 0

while True:
    sucesso, frame = video.read()

    if not sucesso:
        break

    # Salvar/exibir apenas 1 frame por segundo
    if frame_atual % intervalo == 0:
        segundo = frame_atual / fps

        print("Frame:", frame_atual, "- Segundo:", segundo)

        cv2.imshow("Frame extraido", frame)

        # Esperar 500 ms para visualizar
        if cv2.waitKey(500) & 0xFF == ord("q"):
            break

    frame_atual += 1

# Liberar o vídeo
video.release()

# Fechar as janelas
cv2.destroyAllWindows()