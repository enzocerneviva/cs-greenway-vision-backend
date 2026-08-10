import cv2

# Abrir o vídeo
video = cv2.VideoCapture("video_teste.mp4")
print("Vídeo abriu?", video.isOpened())

while True:
    sucesso, frame = video.read()
    if not sucesso:
        break
    cv2.imshow("Video", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

video.release()
cv2.destroyAllWindows()