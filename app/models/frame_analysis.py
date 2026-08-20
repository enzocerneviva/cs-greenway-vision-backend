from sqlalchemy import Column, Integer, Float, String, ForeignKey
from app.database.session import Base


class FrameAnalysis(Base):
    """Resultado da classificação de um frame específico dentro de uma Inspection."""

    __tablename__ = "frame_analyses"

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)

    frame_index = Column(Integer, nullable=False)
    # Segundo exato dentro do arquivo de vídeo original — use isso pra
    # localizar o frame no vídeo fonte e conferir visualmente. 0.0 pra imagem.
    timestamp_seconds = Column(Float, nullable=False)
    # Posição estimada por interpolação linear entre km_start/km_end do
    # Segment — aproximação v1 (não é GPS real), ver docs/architecture.md.
    estimated_km = Column(Float, nullable=False)
    green_percent = Column(Float, nullable=False)
    priority = Column(String, nullable=False)
    # Caminho relativo à raiz do projeto (ex.: "storage/frames/12/0.jpg"),
    # servido estaticamente — ver app/main.py. Nulo se a imagem não foi
    # persistida (não deveria acontecer em uso normal, mas o campo é opcional
    # por segurança).
    image_path = Column(String, nullable=True)
