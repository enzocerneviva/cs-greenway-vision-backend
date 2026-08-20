"""
Rotulagem manual rápida das fotos de campo em data/images-real-road/
(fotos reais, fora do dataset de treino do Mapillary) — pra comparar contra
a previsão do modelo em predictions.csv (gerado por classify.py).

Abre cada imagem (visualizador padrão do sistema) e pede a classificação
no terminal. Salva incrementalmente em labels.csv — pode fechar e retomar
depois, só rotula o que ainda falta.

Rodar (você, no seu terminal — precisa da tela pra ver a imagem):

    python data/images-real-road/label_images.py
"""

import csv
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).parent
LABELS_CSV = BASE_DIR / "labels.csv"

VALID_LABELS = {
    "1": "LOW", "2": "MEDIUM", "3": "HIGH",
    "L": "LOW", "M": "MEDIUM", "H": "HIGH",
}


def load_labels() -> dict:
    if not LABELS_CSV.exists():
        return {}
    with open(LABELS_CSV, newline="", encoding="utf-8") as f:
        return {row["filename"]: row["label"] for row in csv.DictReader(f)}


def save_labels(labels: dict) -> None:
    with open(LABELS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "label"])
        for filename, label in sorted(labels.items()):
            writer.writerow([filename, label])


def ask_label(image_path: Path) -> str | None:
    print(f"\nAbrindo: {image_path.name}")
    Image.open(image_path).show()

    while True:
        resposta = input(
            "Classifique [1=LOW, 2=MEDIUM, 3=HIGH, P=pular, S=sair]: "
        ).strip().upper()

        if resposta in ("S", "SAIR"):
            return None
        if resposta in ("P", "PULAR"):
            return "SKIP"
        if resposta in VALID_LABELS:
            return VALID_LABELS[resposta]

        print("Entrada invalida. Use 1, 2, 3, P ou S.")


def main() -> None:
    image_paths = sorted(
        p for p in BASE_DIR.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )
    labels = load_labels()
    pending = [p for p in image_paths if p.name not in labels]

    print(f"Total de imagens: {len(image_paths)}")
    print(f"Já rotuladas: {len(labels)}")
    print(f"Pendentes: {len(pending)}\n")

    if not pending:
        print("Todas as imagens já foram rotuladas!")
        return

    rotuladas_nesta_sessao = 0
    for image_path in pending:
        label = ask_label(image_path)

        if label is None:
            print(f"\nSessão encerrada. {rotuladas_nesta_sessao} rotulada(s) agora.")
            return

        if label == "SKIP":
            print("Pulada (será perguntada de novo na próxima execução).")
            continue

        labels[image_path.name] = label
        save_labels(labels)
        rotuladas_nesta_sessao += 1
        print(f"Salvo: {image_path.name} -> {label}")

    print(f"\nTodas as pendentes foram rotuladas! ({rotuladas_nesta_sessao} nesta sessão)")


if __name__ == "__main__":
    main()
