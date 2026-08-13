"""
Experimento de aquisicao de dados do Mapillary.

Objetivo (v1 - so este trecho, nao o dataset completo):
1. Consultar a Graph API v4 do Mapillary por um bbox pequeno na SP-330.
2. Salvar os metadados retornados em CSV.
3. Visualizar a distribuicao de imagens por sequencia (grafico de barras).
4. Baixar uma amostra pequena das imagens para inspecao manual.
"""

import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
import matplotlib.pyplot as plt

load_dotenv()

ACCESS_TOKEN = os.getenv("MAPILLARY_ACCESS_TOKEN")
GRAPH_API_URL = "https://graph.mapillary.com/images"

# Trecho da SP-330 fornecido pelo usuario: Km 80 -> Km 84 (aproximado)
BBOX = {
    "min_lon": -47.2033,
    "min_lat": -22.8397,
    "max_lon": -47.1714,
    "max_lat": -22.8051,
}

# Sequencias escolhidas manualmente no site/app do Mapillary (percorrem a via
# de fato, ao contrario da busca por bbox, que traz ruas aleatorias dentro da
# area). Se essa lista estiver vazia, o script cai de volta para o bbox.
SEQUENCE_IDS: list[str] = [
    "4oormcsrucb7t55y3g4lim"
]

FIELDS = "id,sequence,captured_at,compass_angle,geometry,thumb_1024_url"

# Limites do experimento: nao queremos o dataset inteiro, so uma amostra para explorar.
MAX_METADATA_RECORDS = 500
SAMPLE_DOWNLOAD_COUNT = 20

# A Graph API rejeita (HTTP 500, "reduce the amount of data you're asking
# for") bboxes com imagens demais, o que depende da densidade de cobertura
# da regiao, nao so da area geografica. 0.01 grau (~1km) e seguro na maioria
# dos casos, mas tiles muito densos ainda podem falhar - por isso tambem
# tratamos esse erro tile a tile em vez de deixar o script inteiro quebrar.
TILE_SIZE_DEG = 0.01

BASE_DIR = Path(__file__).parent
METADATA_CSV = BASE_DIR / "metadata.csv"
DISTRIBUTION_PLOT = BASE_DIR / "sequence_distribution.png"
IMAGES_DIR = BASE_DIR / "images"


def generate_bbox_tiles(bbox: dict, tile_size_deg: float) -> list[dict]:
    """Divide um bbox grande em um grid de bboxes menores.

    Necessario porque a Graph API rejeita bboxes grandes com HTTP 500.
    """
    tiles = []
    lat = bbox["min_lat"]
    while lat < bbox["max_lat"]:
        lon = bbox["min_lon"]
        next_lat = min(lat + tile_size_deg, bbox["max_lat"])
        while lon < bbox["max_lon"]:
            next_lon = min(lon + tile_size_deg, bbox["max_lon"])
            tiles.append(
                {"min_lon": lon, "min_lat": lat, "max_lon": next_lon, "max_lat": next_lat}
            )
            lon = next_lon
        lat = next_lat

    return tiles


def fetch_images_in_bbox(bbox: dict, max_records: int) -> list[dict]:
    """Consulta a Graph API v4 e retorna metadados de imagens dentro de um bbox.

    A API pagina os resultados: cada resposta traz `paging.next`, a URL
    completa para a proxima pagina. Seguimos esse link ate atingir
    `max_records` ou a API nao ter mais paginas.
    """
    bbox_param = f"{bbox['min_lon']},{bbox['min_lat']},{bbox['max_lon']},{bbox['max_lat']}"

    params = {
        "access_token": ACCESS_TOKEN,
        "fields": FIELDS,
        "bbox": bbox_param,
        "limit": 100,
    }

    records: list[dict] = []
    url = GRAPH_API_URL

    while url and len(records) < max_records:
        response = requests.get(url, params=params if url == GRAPH_API_URL else None)
        response.raise_for_status()
        payload = response.json()

        records.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")

        time.sleep(0.2)  # evita bater rate limit da API

    return records[:max_records]


def fetch_images_by_sequences(sequence_ids: list[str], max_records: int) -> list[dict]:
    """Consulta a Graph API v4 filtrando por sequence_ids especificas.

    Evita o problema do bbox (imagens aleatorias de ruas fora da via de
    interesse): aqui trazemos so as imagens das sequencias escolhidas.
    """
    if not ACCESS_TOKEN:
        raise RuntimeError("MAPILLARY_ACCESS_TOKEN nao encontrado no .env")

    params = {
        "access_token": ACCESS_TOKEN,
        "fields": FIELDS,
        "sequence_ids": ",".join(sequence_ids),
        "limit": 100,
    }

    records: list[dict] = []
    url = GRAPH_API_URL

    while url and len(records) < max_records:
        response = requests.get(url, params=params if url == GRAPH_API_URL else None)
        response.raise_for_status()
        payload = response.json()

        records.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")

        print(f"  recebidas {len(records)} imagens ate agora...")
        time.sleep(0.2)  # evita bater rate limit da API

    return records[:max_records]


def fetch_images_metadata(bbox: dict, max_records: int) -> list[dict]:
    """Consulta a Graph API v4 sobre um grid de tiles cobrindo o bbox pedido,
    juntando e deduplicando (por id) os resultados de cada tile.
    """
    if not ACCESS_TOKEN:
        raise RuntimeError("MAPILLARY_ACCESS_TOKEN nao encontrado no .env")

    tiles = generate_bbox_tiles(bbox, TILE_SIZE_DEG)
    print(f"  bbox dividido em {len(tiles)} tile(s)")

    records_by_id: dict[str, dict] = {}
    for i, tile in enumerate(tiles, start=1):
        remaining = max_records - len(records_by_id)
        if remaining <= 0:
            break

        try:
            tile_records = fetch_images_in_bbox(tile, remaining)
        except requests.exceptions.HTTPError as error:
            print(f"  tile {i}/{len(tiles)}: falhou ({error}), pulando")
            continue

        for record in tile_records:
            records_by_id[record["id"]] = record

        print(f"  tile {i}/{len(tiles)}: +{len(tile_records)} imagens (total: {len(records_by_id)})")

    return list(records_by_id.values())


def save_metadata_csv(records: list[dict], path: Path) -> pd.DataFrame:
    """Achata os registros (geometry é um dict aninhado) e salva em CSV."""
    rows = []
    for record in records:
        coordinates = record.get("geometry", {}).get("coordinates", [None, None])
        rows.append(
            {
                "id": record.get("id"),
                "sequence": record.get("sequence"),
                "captured_at": record.get("captured_at"),
                "compass_angle": record.get("compass_angle"),
                "longitude": coordinates[0],
                "latitude": coordinates[1],
                "thumb_1024_url": record.get("thumb_1024_url"),
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


def plot_sequence_distribution(df: pd.DataFrame, output_path: Path) -> None:
    """Gera um grafico de barras: quantidade de imagens por sequencia."""
    counts = df["sequence"].value_counts()

    plt.figure(figsize=(10, 5))
    counts.plot(kind="bar")
    plt.title("Imagens por sequencia - trecho SP-330 (Km 80-84)")
    plt.xlabel("ID da sequencia")
    plt.ylabel("Quantidade de imagens")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    print(f"\n{len(counts)} sequencias distintas encontradas.")
    print(counts)


def download_sample(df: pd.DataFrame, sample_size: int, images_dir: Path) -> None:
    """Baixa uma amostra pequena das imagens (uma requisicao HTTP por imagem)."""
    images_dir.mkdir(exist_ok=True)

    sample = df.dropna(subset=["thumb_1024_url"]).sample(
        n=min(sample_size, len(df)), random_state=42
    )

    for _, row in sample.iterrows():
        image_path = images_dir / f"{row['id']}.jpg"
        response = requests.get(row["thumb_1024_url"])
        response.raise_for_status()
        image_path.write_bytes(response.content)
        print(f"  salvo: {image_path.name}")


def main():
    print("1. Consultando metadados na Graph API v4...")
    if SEQUENCE_IDS:
        print(f"  modo: sequence_ids ({len(SEQUENCE_IDS)} sequencia(s))")
        records = fetch_images_by_sequences(SEQUENCE_IDS, MAX_METADATA_RECORDS)
    else:
        print("  modo: bbox (SEQUENCE_IDS vazio)")
        records = fetch_images_metadata(BBOX, MAX_METADATA_RECORDS)
    print(f"Total de metadados obtidos: {len(records)}")

    print("\n2. Salvando metadados em CSV...")
    df = save_metadata_csv(records, METADATA_CSV)
    print(f"Salvo em: {METADATA_CSV}")

    print("\n3. Gerando grafico de distribuicao por sequencia...")
    plot_sequence_distribution(df, DISTRIBUTION_PLOT)
    print(f"Grafico salvo em: {DISTRIBUTION_PLOT}")

    print(f"\n4. Baixando amostra de {SAMPLE_DOWNLOAD_COUNT} imagens...")
    download_sample(df, SAMPLE_DOWNLOAD_COUNT, IMAGES_DIR)
    print(f"Imagens salvas em: {IMAGES_DIR}")


if __name__ == "__main__":
    main()
