from typing import Optional
from pydantic import BaseModel


class RoadCreate(BaseModel):
    name: str
    concessionaire: Optional[str] = None


class RoadResponse(BaseModel):
    id: int
    name: str
    concessionaire: Optional[str]

    class Config:
        from_attributes = True
