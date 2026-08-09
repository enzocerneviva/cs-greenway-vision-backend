import cv2

# Carregar a imagem
imagem = cv2.imread("teste.png")

# Exibir a imagem
cv2.imshow("Minha imagem", imagem)

# Esperar uma tecla ser pressionada
cv2.waitKey(0)

# Fechar todas as janelas
cv2.destroyAllWindows()

print(type(imagem))
print(imagem.shape)