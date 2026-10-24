from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Integer, String

from app.database.session import Base


class SuggestionDismissal(Base):
    """
    Sugestões são calculadas na hora (não ficam gravadas). Só o "Dispensar"
    do usuário é guardado: a `key` identifica a sugestão e ela fica escondida
    até a data `until` (inclusive).
    """

    __tablename__ = "suggestion_dismissals"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    until = Column(Date, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
