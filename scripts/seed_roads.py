"""
Popula rodovias reais da Motiva. Rodar com o venv ativado, a partir da raiz
do projeto: python scripts/seed_roads.py

Idempotente por nome de rodovia (não duplica se já existir).
"""
from app.database.session import SessionLocal
from app.models import Road, Segment

# (nome, concessionária, km_start, km_end)
ROADS = [
    ("SP-330 (Anhanguera)", "AutoBān", 11.0, 158.0),
    ("SP-348 (Bandeirantes)", "AutoBān", 13.0, 173.0),
]


def seed():
    db = SessionLocal()
    try:
        for name, concessionaire, km_start, km_end in ROADS:
            existing = db.query(Road).filter(Road.name == name).first()
            if existing:
                print(f"já existe, pulando: {name}")
                continue

            road = Road(name=name, concessionaire=concessionaire)
            db.add(road)
            db.commit()
            db.refresh(road)

            segment = Segment(road_id=road.id, km_start=km_start, km_end=km_end)
            db.add(segment)
            db.commit()

            print(f"criado: {name} (km {km_start}-{km_end})")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
