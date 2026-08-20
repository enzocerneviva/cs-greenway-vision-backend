"""
Compara as previsões do modelo (predictions.csv, gerado por classify.py)
com o gabarito rotulado manualmente (labels.csv, gerado por label_images.py)
sobre as fotos de campo em data/images-real-road/.

Rodar, depois de gerar os dois CSVs:

    python data/images-real-road/compare.py
"""

import csv
from pathlib import Path

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

BASE_DIR = Path(__file__).parent
PREDICTIONS_CSV = BASE_DIR / "predictions.csv"
LABELS_CSV = BASE_DIR / "labels.csv"


def load_csv(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        return {row[list(row.keys())[0]]: row for row in csv.DictReader(f)}


def main() -> None:
    if not PREDICTIONS_CSV.exists():
        raise FileNotFoundError("predictions.csv não encontrado — rode classify.py primeiro.")
    if not LABELS_CSV.exists():
        raise FileNotFoundError("labels.csv não encontrado — rode label_images.py primeiro.")

    predictions = load_csv(PREDICTIONS_CSV)
    labels = load_csv(LABELS_CSV)

    common = sorted(set(predictions) & set(labels))
    missing_labels = sorted(set(predictions) - set(labels))
    if missing_labels:
        print(f"Aviso: {len(missing_labels)} imagem(ns) sem rótulo ainda: {missing_labels}\n")

    y_true = [labels[name]["label"] for name in common]
    y_pred = [predictions[name]["predicted_label"] for name in common]

    print(f"Imagens comparadas: {len(common)}\n")
    print(f"Acurácia: {accuracy_score(y_true, y_pred):.2%}\n")
    print("Relatório de classificação:")
    print(classification_report(y_true, y_pred, zero_division=0))

    labels_sorted = sorted(set(y_true) | set(y_pred))
    print(f"Matriz de confusão (linhas=real, colunas=previsto) — ordem: {labels_sorted}")
    print(confusion_matrix(y_true, y_pred, labels=labels_sorted))

    print("\nCasos onde o modelo errou:")
    for name in common:
        real = labels[name]["label"]
        previsto = predictions[name]["predicted_label"]
        if real != previsto:
            print(f"  {name}: real={real}, previsto={previsto}")


if __name__ == "__main__":
    main()
