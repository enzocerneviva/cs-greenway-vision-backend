# Extrai um vetor de características (embedding) de uma imagem usando uma
# CNN pré-treinada (MobileNetV2, ImageNet) como extrator fixo — a rede não
# é treinada/ajustada aqui, só usada em modo inferência pra gerar um vetor
# numérico que resume a imagem (cor, textura, forma) de forma muito mais
# rica do que features desenhadas à mão.
#
# Usado tanto pelo treino do classificador (data/mapillary/train_classifier.py)
# quanto, futuramente, pelo Vision Engine em tempo de inferência real.

import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms

_device = torch.device("cpu")

_model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
_model.classifier = torch.nn.Identity()  # remove a camada final de classificação do ImageNet -> vira extrator de features
_model.eval()
_model.to(_device)

_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def extract_embedding(image: Image.Image) -> np.ndarray:
    """Recebe uma imagem PIL em RGB e retorna seu vetor de características (1D)."""
    tensor = _transform(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        embedding = _model(tensor)
    return embedding.squeeze(0).cpu().numpy()
