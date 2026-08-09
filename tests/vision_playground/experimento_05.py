import cv2

# Carregar um frame já extraído (escolha um que tenha vegetação visível)
frame = cv2.imread("teste.png")

# Converter de BGR para HSV
frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

# Exibir os dois, lado a lado pra comparar
cv2.imshow("Original (BGR)", frame)
cv2.imshow("Convertido (HSV)", frame_hsv)

cv2.waitKey(0)
cv2.destroyAllWindows()