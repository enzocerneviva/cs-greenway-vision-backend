"""
Script de rotulacao manual para o dataset de vegetacao (GreenWay Vision).


Criterio de classificacao (ver README do modulo para mais detalhes):
  LOW    - vegetacao rasteira, pouca presenca nas margens, via/acostamento
           claramente desobstruidos.
  MEDIUM - vegetacao mais alta/densa, aproximando-se da pista, mas ainda
           sem comprometer a visibilidade.
  HIGH   - vegetacao alta/densa, ocupando boa parte da margem, invadindo
           ou proxima de invadir o acostamento/pista.
"""

import csv
import random
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"
METADATA_CSV = BASE_DIR / "metadata.csv"

VALID_LABELS = {
    "1": "LOW",
    "2": "MEDIUM",
    "3": "HIGH",
    "L": "LOW",
    "M": "MEDIUM",
    "H": "HIGH",
}


def load_metadata() -> tuple[list[str], list[dict]]:
    """Le metadata.csv e devolve (nomes_das_colunas, linhas).

    Se a coluna "label" ainda nao existir, ela e criada (vazia) em todas
    as linhas.
    """
    if not METADATA_CSV.exists():
        raise FileNotFoundError(
            f"metadata.csv nao encontrado em {METADATA_CSV}. "
            "Rode extraction.py primeiro."
)
    with open(METADATA_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "label" not in fieldnames:
        fieldnames.append("label")
        for row in rows:
            row["label"] = ""

    return fieldnames, rows


def save_metadata(fieldnames: list[str], rows: list[dict]) -> None:
    """Regrava metadata.csv por completo (inclui a coluna label atualizada)."""
    with open(METADATA_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ask_label(image_path: Path) -> str | None:
    """
    Mostra a imagem e pede a classificacao.

    Retorna "LOW"/"MEDIUM"/"HIGH", "SKIP" (pular por agora) ou None (sair).
    """
    print(f"\nAbrindo: {image_path.name}")
    img = Image.open(image_path)
    img.show()

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
    if not IMAGES_DIR.exists():
        print(f"Pasta de imagens nao encontrada: {IMAGES_DIR}")
        return

    all_images = sorted(IMAGES_DIR.glob("*.jpg"))
    if not all_images:
        print(f"Nenhuma imagem encontrada em {IMAGES_DIR}")
        return

    fieldnames, rows = load_metadata()
    rows_by_id = {row["id"]: row for row in rows}

    pending = []
    sem_metadata = []
    for image_path in all_images:
        row = rows_by_id.get(image_path.stem)
        if row is None:
            sem_metadata.append(image_path.stem)
            continue
        if not row.get("label"):
            pending.append(image_path)

    ja_rotuladas = sum(1 for row in rows if row.get("label"))
    random.shuffle(pending)

    print(f"Total de imagens em disco: {len(all_images)}")
    print(f"Ja rotuladas: {ja_rotuladas}")
    print(f"Pendentes: {len(pending)}")
    if sem_metadata:
        print(
            f"Aviso: {len(sem_metadata)} imagem(ns) sem linha correspondente "
            f"em metadata.csv (id nao encontrado). Essas nao aparecerao "
            f"para rotulacao ate que o metadata.csv seja atualizado com "
            f"elas."
        )
    print()

    if not pending:
        print("Todas as imagens com metadata correspondente ja foram rotuladas!")
        return

    rotuladas_nesta_sessao = 0

    for image_path in pending:
        row = rows_by_id[image_path.stem]
        label = ask_label(image_path)

        if label is None:
            print(
                f"\nSessao encerrada. "
                f"{rotuladas_nesta_sessao} imagem(ns) rotulada(s) agora."
            )
            break

        if label == "SKIP":
            print("Pulada (sera perguntada de novo na proxima execucao).")
            continue

        row["label"] = label
        save_metadata(fieldnames, rows)
        rotuladas_nesta_sessao += 1
        print(f"Salvo: {image_path.stem} -> {label}")

    else:
        print(
            f"\nTodas as imagens pendentes foram rotuladas! "
            f"({rotuladas_nesta_sessao} nesta sessao)"
        )


if __name__ == "__main__":
    main()