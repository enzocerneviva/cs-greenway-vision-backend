"""
Baixa as imagens referenciadas em data/mapillary/metadata.csv para
data/mapillary/images/, sem consultar a API de sequencias do Mapillary
novamente.

"""

import csv
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"
METADATA_CSV = BASE_DIR / "metadata.csv"


def load_rows() -> list[dict]:
    if not METADATA_CSV.exists():
        raise FileNotFoundError(
            f"metadata.csv nao encontrado em {METADATA_CSV}. "
            "Copie/puxe o repositorio com este arquivo antes de rodar."
        )
    with open(METADATA_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def download_image(image_id: str, url: str) -> bool:
    """Baixa uma imagem. Retorna True se salvou, False se falhou."""
    dest = IMAGES_DIR / f"{image_id}.jpg"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        dest.write_bytes(response.content)
        return True
    except requests.exceptions.RequestException as exc:
        print(f"  falhou: {image_id} ({exc})")
        return False


def main() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)
    rows = load_rows()

    pending = [
        row for row in rows
        if not (IMAGES_DIR / f"{row['id']}.jpg").exists()
    ]

    print(f"Total de linhas em metadata.csv: {len(rows)}")
    print(f"Ja presentes em images/: {len(rows) - len(pending)}")
    print(f"Para baixar agora: {len(pending)}\n")

    if not pending:
        print("Nada para baixar, images/ ja esta completa.")
        return

    baixadas = 0
    for row in pending:
        url = row.get("thumb_1024_url")
        if not url:
            print(f"  sem thumb_1024_url: {row['id']} (pulada)")
            continue
        if download_image(row["id"], url):
            baixadas += 1
            print(f"  salvo: {row['id']}.jpg ({baixadas}/{len(pending)})")

    print(f"\nConcluido: {baixadas} imagem(ns) baixada(s) em {IMAGES_DIR}")


if __name__ == "__main__":
    main()