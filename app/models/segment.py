from sqlalchemy import Column, Integer, Float, String, ForeignKey
from app.database.session import Base


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, index=True)
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=False)
    km_start = Column(Float, nullable=False)
    km_end = Column(Float, nullable=False)
    direction = Column(String, nullable=False)  # sentido da pista, ex.: "NORTE"/"SUL"

    # Ponta a ponta do trecho, usado pra desenhar uma linha reta no mapa —
    # não é o traçado real da via, é uma aproximação v1. Nulo em trechos
    # cadastrados antes dessa feature (não aparecem no mapa até ganhar coordenadas).
    lat_start = Column(Float, nullable=True)
    lng_start = Column(Float, nullable=True)
    lat_end = Column(Float, nullable=True)
    lng_end = Column(Float, nullable=True)
