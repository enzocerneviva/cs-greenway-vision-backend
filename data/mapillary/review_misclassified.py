"""
Gera uma grade de imagens (contact sheet) com todos os erros do modelo no
conjunto de teste, anotando rótulo real vs previsto em cada uma — pra
revisão visual manual (ex.: label errado no dataset? imagem ambígua de
verdade? padrão que o modelo não capturou?).

Depende de data/mapillary/model/test_predictions.csv, gerado por
train_classifier.py.

Roda como módulo, a partir da raiz do repositório:

    python -m data.mapillary.review_misclassified
"""

import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"
PREDICTIONS_CSV = BASE_DIR / "model" / "test_predictions.csv"
OUTPUT_PATH = BASE_DIR / "model" / "misclassified_review.png"


def load_misclassified() -> list[dict]:
    with open(PREDICTIONS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [row for row in rows if row["correct"] == "False"]


def main() -> None:
    errors = load_misclassified()
    print(f"Erros no conjunto de teste: {len(errors)}")

    if not errors:
        print("Nenhum erro encontrado — nada para revisar.")
        return

    cols = 5
    rows = math.ceil(len(errors) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3, rows * 3.5))
    axes = axes.flatten() if len(errors) > 1 else [axes]

    for ax, row in zip(axes, errors):
        image_path = IMAGES_DIR / f"{row['id']}.jpg"
        image = Image.open(image_path)
        ax.imshow(image)
        ax.set_title(f"real: {row['true_label']}\nprevisto: {row['predicted_label']}", fontsize=10)
        ax.set_xlabel(row["id"], fontsize=7)
        ax.set_xticks([])
        ax.set_yticks([])

    for ax in axes[len(errors):]:
        ax.axis("off")

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=120)
    print(f"Grade salva em {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
