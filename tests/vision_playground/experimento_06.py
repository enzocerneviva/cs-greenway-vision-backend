import cv2
import numpy as np


def nada(x):
    pass


# Carregar a imagem
frame = cv2.imread("teste.png")
frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

# Criar janela com trackbars
cv2.namedWindow("Trackbars")
cv2.createTrackbar("H Min", "Trackbars", 33, 179, nada)
cv2.createTrackbar("H Max", "Trackbars", 95, 179, nada)
cv2.createTrackbar("S Min", "Trackbars", 42, 255, nada)
cv2.createTrackbar("S Max", "Trackbars", 255, 255, nada)
cv2.createTrackbar("V Min", "Trackbars", 0, 255, nada)
cv2.createTrackbar("V Max", "Trackbars", 255, 255, nada)

while True:
    h_min = cv2.getTrackbarPos("H Min", "Trackbars")
    h_max = cv2.getTrackbarPos("H Max", "Trackbars")
    s_min = cv2.getTrackbarPos("S Min", "Trackbars")
    s_max = cv2.getTrackbarPos("S Max", "Trackbars")
    v_min = cv2.getTrackbarPos("V Min", "Trackbars")
    v_max = cv2.getTrackbarPos("V Max", "Trackbars")

    limite_inferior = np.array([h_min, s_min, v_min])
    limite_superior = np.array([h_max, s_max, v_max])

    mascara = cv2.inRange(frame_hsv, limite_inferior, limite_superior)

    cv2.imshow("Original", frame)
    cv2.imshow("Mascara", mascara)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()

print(f"Valores finais -> H: [{h_min}, {h_max}]  S: [{s_min}, {s_max}]  V: [{v_min}, {v_max}]")

# Recriar a máscara final com os valores calibrados
limite_inferior = np.array([h_min, s_min, v_min])
limite_superior = np.array([h_max, s_max, v_max])
mascara_final = cv2.inRange(frame_hsv, limite_inferior, limite_superior)

# Contar pixels brancos (vegetação) e o total de pixels da imagem
pixels_vegetacao = cv2.countNonZero(mascara_final)
altura, largura = mascara_final.shape
total_pixels = altura * largura

# Calcular o percentual
percentual_vegetacao = (pixels_vegetacao / total_pixels) * 100

print(f"Pixels de vegetação: {pixels_vegetacao}")
print(f"Total de pixels: {total_pixels}")
print(f"Percentual de vegetação: {percentual_vegetacao:.2f}%")