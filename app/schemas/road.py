from pydantic import BaseModel


class RoadCreate(BaseModel):
    name: str


class RoadResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
