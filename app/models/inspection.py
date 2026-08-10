from sqlalchemy import Column, Integer, Float, String, DateTime
from datetime import datetime, timezone
from app.database.session import Base

# Tabela Inspeção (inspections)
class Inspection(Base):
    __tablename__ = "inspections"

    # Colunas
    id = Column(Integer, primary_key=True, index=True)
    measurement_value = Column(Float, nullable=False) # Medição da vegetação
    measurement_unit = Column(String, default="cm") # Unidade da medição (cm)
    priority = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
