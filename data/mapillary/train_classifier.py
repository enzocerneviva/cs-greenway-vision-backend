"""
Treina o classificador de vegetação (v1 — baseline) sobre o dataset
rotulado do Mapillary.

Roda como módulo, a partir da raiz do repositório, pra que o import de
`app.vision.feature_extractor_cnn` funcione:

    python -m data.mapillary.train_classifier
"""

import csv
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from app.vision.feature_extractor_cnn import extract_embedding

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"
METADATA_CSV = BASE_DIR / "metadata.csv"
MODEL_DIR = BASE_DIR / "model"
MODEL_PATH = MODEL_DIR / "classifier.joblib"


def load_labeled_rows() -> list[dict]:
    with open(METADATA_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        row for row in rows
        if row.get("label") and (IMAGES_DIR / f"{row['id']}.jpg").exists()
    ]


def build_dataset(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = []
    labels = []
    ids = []
    for i, row in enumerate(rows):
        image_path = IMAGES_DIR / f"{row['id']}.jpg"
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            print(f"  pulando {row['id']}: {exc}")
            continue

        features.append(extract_embedding(image))
        labels.append(row["label"])
        ids.append(row["id"])

        if (i + 1) % 50 == 0:
            print(f"  processadas {i + 1}/{len(rows)}")

    return np.array(features), np.array(labels), np.array(ids)


def main() -> None:
    rows = load_labeled_rows()
    print(f"Imagens rotuladas e presentes em disco: {len(rows)}\n")

    print("Extraindo embeddings (CNN pré-treinada, CPU — pode demorar alguns minutos)...")
    X, y, ids = build_dataset(rows)
    print(f"\nDataset final: {X.shape[0]} amostras, {X.shape[1]} features cada\n")

    X_train, X_test, y_train, y_test, ids_train, ids_test = train_test_split(
        X, y, ids, test_size=0.2, random_state=42, stratify=y
    )

    classifier = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",  # compensa o desbalanceamento (muito mais HIGH que MEDIUM)
        random_state=42,
    )
    classifier.fit(X_train, y_train)

    y_pred = classifier.predict(X_test)

    print(f"Acurácia no conjunto de teste: {accuracy_score(y_test, y_pred):.2%}\n")
    print("Relatório de classificação (precision/recall por classe):")
    print(classification_report(y_test, y_pred))

    labels_sorted = sorted(set(y))
    print(f"Matriz de confusão (linhas=real, colunas=previsto) — ordem: {labels_sorted}")
    print(confusion_matrix(y_test, y_pred, labels=labels_sorted))

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(classifier, MODEL_PATH)
    print(f"\nModelo salvo em {MODEL_PATH}")

    # Registra a divisão treino/teste e as previsões individuais, pra permitir
    # auditar depois quais imagens caíram em cada lado e onde o modelo errou.
    with open(MODEL_DIR / "train_ids.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label"])
        writer.writerows(zip(ids_train, y_train))

    with open(MODEL_DIR / "test_predictions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "true_label", "predicted_label", "correct"])
        writer.writerows(
            (img_id, true, pred, true == pred)
            for img_id, true, pred in zip(ids_test, y_test, y_pred)
        )

    print(f"Divisão treino/teste salva em {MODEL_DIR / 'train_ids.csv'} e {MODEL_DIR / 'test_predictions.csv'}")


if __name__ == "__main__":
    main()
