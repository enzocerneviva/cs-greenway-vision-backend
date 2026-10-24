"""
Calibra CRITICAL_GREEN_PERCENT (app/core/config.py).

Esse valor é o % de verde a partir do qual a PREVISÃO de crescimento considera um
bloco "no nível crítico". O verde (detectar_vegetacao, filtro de cor HSV) não
define a prioridade — quem define é o modelo —, então escolhemos o limite
olhando os dados: a MEDIANA do verde das imagens rotuladas HIGH do dataset.

Só mede e imprime; não altera nada. Rodar a partir da raiz do repositório:

    python -m data.mapillary.calibrate_critical_green
"""
import csv
from pathlib import Path
from statistics import median

import cv2

from app.vision.vegetation_detector import detectar_vegetacao

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"


def main() -> None:
    greens: dict[str, list[float]] = {"LOW": [], "MEDIUM": [], "HIGH": []}
    with open(BASE_DIR / "metadata.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            path = IMAGES_DIR / f"{row['id']}.jpg"
            if row.get("label") in greens and path.exists():
                greens[row["label"]].append(detectar_vegetacao(cv2.imread(str(path))))

    print("Verde (%) por classe rotulada:")
    for label, values in greens.items():
        print(f"  {label:<6} n={len(values):>3}  mediana={median(values):5.1f}  "
              f"mínimo={min(values):5.1f}  máximo={max(values):5.1f}")

    print(f"\nCRITICAL_GREEN_PERCENT sugerido (mediana dos HIGH): {median(greens['HIGH']):.1f}")
    print("Atenção: as medianas das classes ficam próximas — o verde é um separador fraco; "
          "o limite serve só para estimar tendência, não para classificar.")


if __name__ == "__main__":
    main()
