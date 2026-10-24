from datetime import date
from typing import Set

from sqlalchemy.orm import Session

from app.models import SuggestionDismissal


def upsert(db: Session, key: str, until: date) -> SuggestionDismissal:
    dismissal = db.query(SuggestionDismissal).filter(SuggestionDismissal.key == key).first()
    if dismissal is None:
        dismissal = SuggestionDismissal(key=key, until=until)
        db.add(dismissal)
    else:
        dismissal.until = until
    db.flush()
    return dismissal


def active_keys(db: Session, today: date) -> Set[str]:
    """Chaves de sugestões ainda escondidas hoje (until é inclusivo)."""
    rows = db.query(SuggestionDismissal.key).filter(SuggestionDismissal.until >= today).all()
    return {key for (key,) in rows}
