"""
Classifica todas as imagens desta pasta com o modelo treinado
(data/mapillary/model/classifier.joblib), pra teste visual/manual contra
fotos reais de rodovia (fora do dataset de treino).

Roda direto (o nome da pasta tem hífen, não dá pra importar como pacote
Python com -m):

    python data/images-real-road/classify.py
"""

import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).parent
OUTPUT_PATH = BASE_DIR / "classification_review.png"
PREDICTIONS_CSV = BASE_DIR / "predictions.csv"

sys.path.insert(0, str(BASE_DIR.parents[1]))  # raiz do repo, pra importar app.vision.*

from app.vision.engine import _classifier  # noqa: E402
from app.vision.feature_extractor_cnn import extract_embedding  # noqa: E402
from app.vision.vegetation_detector import detectar_vegetacao  # noqa: E402


def main() -> None:
    image_paths = sorted(
        p for p in BASE_DIR.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )
    print(f"Imagens encontradas: {len(image_paths)}\n")

    results = []
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        embedding = extract_embedding(image)
        predicted = _classifier.predict([embedding])[0]

        # % de verde (pré-filtro), só como referência complementar aqui —
        # não filtra nada neste teste, classificamos todas de propósito.
        bgr_array = np.array(image)[:, :, ::-1]
        green_percent = detectar_vegetacao(bgr_array)

        results.append((path.name, predicted, green_percent))
        print(f"{path.name:20s} -> {predicted:8s} (verde: {green_percent:5.1f}%)")

    cols = 5
    rows = math.ceil(len(results) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3, rows * 3.5))
    axes = axes.flatten() if len(results) > 1 else [axes]

    for ax, (name, predicted, green_percent) in zip(axes, results):
        image = Image.open(BASE_DIR / name)
        ax.imshow(image)
        ax.set_title(f"previsto: {predicted}\nverde: {green_percent:.1f}%", fontsize=10)
        ax.set_xlabel(name, fontsize=7)
        ax.set_xticks([])
        ax.set_yticks([])

    for ax in axes[len(results):]:
        ax.axis("off")

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=120)
    print(f"\nGrade salva em {OUTPUT_PATH}")

    with open(PREDICTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "predicted_label", "green_percent"])
        writer.writerows(results)
    print(f"Previsões salvas em {PREDICTIONS_CSV}")


if __name__ == "__main__":
    main()
