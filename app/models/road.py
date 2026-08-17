from sqlalchemy import Column, Integer, String
from app.database.session import Base


class Road(Base):
    __tablename__ = "roads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
