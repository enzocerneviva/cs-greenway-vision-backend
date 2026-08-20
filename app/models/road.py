import json

from sqlalchemy import Column, Integer, String, Text
from app.database.session import Base


class Road(Base):
    __tablename__ = "roads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    concessionaire = Column(String, nullable=True)  # ex.: "AutoBān", "ViaOeste"

    # Traçado real (aproximado) buscado automaticamente no OpenStreetMap ao
    # cadastrar a rodovia — ver app/services/geocoding_service.py. Guardado
    # como JSON ([[lat, lng], ...]) porque SQLite não tem tipo de array/geo
    # nativo. Nulo se a busca falhar ou a rodovia não tiver cobertura boa
    # o suficiente no OSM (cadastro nunca falha por causa disso).
    geometry_json = Column(Text, nullable=True)

    @property
    def geometry(self) -> list[list[float]] | None:
        if self.geometry_json is None:
            return None
        return json.loads(self.geometry_json)

    @geometry.setter
    def geometry(self, points: list[tuple[float, float]] | None) -> None:
        self.geometry_json = json.dumps(points) if points is not None else None
