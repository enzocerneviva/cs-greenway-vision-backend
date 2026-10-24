"""
Avaliação honesta do classificador de vegetação (Parte C do plano V2).

Não treina nem altera o modelo em uso: só mede. Responde:
  1. Qual a nota "de verdade" do modelo? (o split aleatório do treino pode
     estar inflado — fotos vizinhas da mesma sequência são quase idênticas)
  2. O pré-processamento atual (corte central 224x224) perde informação?
  3. O pré-filtro de cor (< 5 % de verde = LOW) descarta fotos relevantes?
  4. A confiança do modelo (predict_proba) distingue acerto de erro?
  5. Como o modelo atual se sai nas fotos reais de campo?

Rodar a partir da raiz do repositório:

    python -m data.mapillary.evaluate_classifier [--cache PASTA] [--report ARQUIVO.md]

--cache  guarda os embeddings já calculados (o passo lento), pra repetir o
         relatório sem recalcular.
--report grava a saída num arquivo (o do modelo em uso fica em
         data/mapillary/model/evaluation.md).
"""

import argparse
import contextlib
import csv
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import joblib
import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, cross_val_predict
from torchvision import transforms

from app.vision.feature_extractor_cnn import _get_model, extract_embedding
from app.vision.vegetation_detector import detectar_vegetacao

import torch

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"
METADATA_CSV = BASE_DIR / "metadata.csv"
MODEL_PATH = BASE_DIR / "model" / "classifier.joblib"
REAL_PHOTOS_DIR = BASE_DIR.parent / "images-real-road"

LABELS = ["LOW", "MEDIUM", "HIGH"]
BLOCK_SIZE = 20  # fotos consecutivas (por tempo) de uma sequência que formam um "bloco"
N_SPLITS = 5
SEED = 42

# Mesma normalização do extractor atual; só muda o redimensionamento.
_NORMALIZE = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
_SQUASH = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(), _NORMALIZE])


def extract_embedding_squash(image: Image.Image) -> np.ndarray:
    """Imagem INTEIRA esticada pra 224x224 (sem cortar as laterais)."""
    tensor = _SQUASH(image).unsqueeze(0)
    with torch.no_grad():
        return _get_model()(tensor).squeeze(0).numpy()


def load_rows() -> list[dict]:
    with open(METADATA_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("label")]
    rows = [r for r in rows if (IMAGES_DIR / f"{r['id']}.jpg").exists()]
    for r in rows:
        r["captured_at"] = int(r["captured_at"])
    return rows


def assign_time_blocks(rows: list[dict]) -> np.ndarray:
    """Grupo = (sequência, bloco de BLOCK_SIZE fotos consecutivas por horário)."""
    by_sequence = defaultdict(list)
    for index, row in enumerate(rows):
        by_sequence[row["sequence"]].append(index)
    groups = np.zeros(len(rows), dtype=int)
    next_group = 0
    for indexes in by_sequence.values():
        indexes.sort(key=lambda i: rows[i]["captured_at"])
        for position, i in enumerate(indexes):
            groups[i] = next_group + position // BLOCK_SIZE
        next_group += (len(indexes) - 1) // BLOCK_SIZE + 1
    return groups


def embeddings(rows: list[dict], variant: str, cache: Path | None) -> np.ndarray:
    cache_file = cache / f"embeddings_{variant}.npy" if cache else None
    if cache_file and cache_file.exists():
        return np.load(cache_file)
    extract = extract_embedding if variant == "crop" else extract_embedding_squash
    print(f"  calculando embeddings ({variant})...", flush=True)
    features = np.array([
        extract(Image.open(IMAGES_DIR / f"{r['id']}.jpg").convert("RGB")) for r in rows
    ])
    if cache_file:
        cache.mkdir(parents=True, exist_ok=True)
        np.save(cache_file, features)
    return features


def new_classifier() -> RandomForestClassifier:
    # Mesma configuração do train_classifier.py.
    return RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=SEED)


def summarize(name: str, y_true, y_pred) -> dict:
    recalls = {}
    matrix = confusion_matrix(y_true, y_pred, labels=LABELS)
    for i, label in enumerate(LABELS):
        total = matrix[i].sum()
        recalls[label] = (matrix[i][i] / total) if total else float("nan")
    result = {
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0),
        **{f"recall_{k}": v for k, v in recalls.items()},
    }
    print(f"\n[{name}]")
    print(f"  acurácia {result['accuracy']:.1%} | F1 macro {result['macro_f1']:.2f} | "
          f"recall LOW {recalls['LOW']:.0%} MEDIUM {recalls['MEDIUM']:.0%} HIGH {recalls['HIGH']:.0%}")
    print(f"  matriz de confusão (linhas=real, colunas=previsto; ordem {LABELS}):")
    for label, line in zip(LABELS, matrix):
        print(f"    {label:<6}{line}")
    return result


class Tee:
    """Escreve no terminal e num arquivo ao mesmo tempo."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    if args.report is None:
        run(args)
        return

    with open(args.report, "w", encoding="utf-8") as report:
        report.write("# Avaliação do classificador de vegetação\n\n")
        report.write("Gerado por `python -m data.mapillary.evaluate_classifier --report ...`. ")
        report.write("Mede o modelo sem treiná-lo nem alterá-lo. Como ler cada seção: ver o docstring do script.\n\n")
        report.write("```text\n")
        report.flush()
        with contextlib.redirect_stdout(Tee(sys.stdout, report)):
            run(args)
        report.write("```\n")


def run(args) -> None:
    rows = load_rows()
    y = np.array([r["label"] for r in rows])
    groups = assign_time_blocks(rows)
    sequences = np.array([r["sequence"] for r in rows])
    print(f"Imagens rotuladas: {len(rows)} | classes: { {l: int((y == l).sum()) for l in LABELS} }")
    print(f"Sequências: {len(set(sequences))} | blocos de {BLOCK_SIZE} fotos consecutivas: {len(set(groups))}")

    random_cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    block_cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)

    print("\n=== 1 e 2. Nota do modelo: split aleatório x por blocos de tempo; recorte x imagem inteira ===")
    outcomes = {}
    probabilities = {}
    for variant in ("crop", "squash"):
        X = embeddings(rows, variant, args.cache)
        for cv_name, cv, kwargs in (("aleatório", random_cv, {}), ("por blocos", block_cv, {"groups": groups})):
            proba = cross_val_predict(new_classifier(), X, y, cv=cv, method="predict_proba", **kwargs)
            pred = np.array(sorted(set(y)))[proba.argmax(axis=1)]
            key = (variant, cv_name)
            outcomes[key] = summarize(f"{variant} | CV {cv_name}", y, pred)
            probabilities[key] = (proba, pred)

    print("\n=== Só a sequência grande (mesma estrada: sem o atalho 'qual estrada é esta?') ===")
    biggest = max(set(sequences), key=lambda s: (sequences == s).sum())
    mask = sequences == biggest
    X_crop = embeddings(rows, "crop", args.cache)
    pred = cross_val_predict(new_classifier(), X_crop[mask], y[mask], cv=block_cv, groups=groups[mask])
    print(f"  sequência {biggest[:8]}…: {int(mask.sum())} fotos, classes { {l: int((y[mask] == l).sum()) for l in LABELS} }")
    summarize("dentro de uma estrada só | CV por blocos", y[mask], pred)

    print("\n=== 4. A confiança do modelo distingue acerto de erro? (recorte, CV por blocos) ===")
    proba, pred = probabilities[("crop", "por blocos")]
    confidence = proba.max(axis=1)
    correct = pred == y
    print(f"  confiança média quando ACERTA: {confidence[correct].mean():.2f} | quando ERRA: {confidence[~correct].mean():.2f}")
    for threshold in (0.5, 0.6, 0.7, 0.8):
        kept = confidence >= threshold
        print(f"  só confiança >= {threshold:.1f}: mantém {kept.mean():.0%} das fotos, acurácia {accuracy_score(y[kept], pred[kept]):.1%}")

    print("\n=== 3. Pré-filtro de cor (< 5 % de verde vira LOW sem passar pelo modelo) ===")
    greens = np.array([
        detectar_vegetacao(cv2.imread(str(IMAGES_DIR / f"{r['id']}.jpg"))) for r in rows
    ])
    for label in LABELS:
        g = greens[y == label]
        print(f"  {label:<6} verde mediano {np.median(g):5.1f}% | abaixo de 5 %: {(g < 5).sum()} de {len(g)} ({(g < 5).mean():.0%})")

    print("\n=== 5. Modelo atual nas fotos reais de campo (data/images-real-road) ===")
    real = sorted(REAL_PHOTOS_DIR.glob("*.JPG"))
    labels_csv = REAL_PHOTOS_DIR / "labels.csv"
    truth = {}
    if labels_csv.exists():
        with open(labels_csv, newline="", encoding="utf-8") as f:
            truth = {r["filename"]: r["label"] for r in csv.DictReader(f)}
    classifier = joblib.load(MODEL_PATH)
    for variant, extract in (("recorte (atual)", extract_embedding), ("imagem inteira", extract_embedding_squash)):
        predicted = [classifier.predict([extract(Image.open(p).convert("RGB"))])[0] for p in real]
        counts = {l: predicted.count(l) for l in LABELS}
        hits = sum(1 for p, f in zip(predicted, real) if truth.get(f.name) == p)
        print(f"  {variant}: {len(real)} fotos -> previsões {counts} | acertos vs. gabarito: {hits}/{len(real)}")
    print("  (atenção: o modelo atual foi treinado com recorte; 'imagem inteira' aqui é só um teste de sensibilidade)")


if __name__ == "__main__":
    main()
