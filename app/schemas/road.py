from typing import Optional
from pydantic import BaseModel


class RoadCreate(BaseModel):
    name: str
    concessionaire: Optional[str] = None


class RoadResponse(BaseModel):
    id: int
    name: str
    concessionaire: Optional[str]
    # Traçado aproximado buscado automaticamente no OpenStreetMap — ver
    # app/services/geocoding_service.py. Nulo se não encontrado.
    geometry: Optional[list[list[float]]]

    class Config:
        from_attributes = True
