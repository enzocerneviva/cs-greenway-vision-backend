from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

from app.core import clock
from app.database.session import Base


class ScheduleEvent(Base):
    """Uma inspeção ou roçada planejada para um trecho de rodovia, numa data."""

    __tablename__ = "schedule_events"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # INSPECTION / MOWING
    status = Column(String, nullable=False)  # PLANNED / IN_PROGRESS / DONE / CANCELED

    road_id = Column(Integer, ForeignKey("roads.id"), nullable=False)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=True)
    # CAPITAL / INTERIOR; nulo = os dois sentidos.
    direction = Column(String, nullable=True)
    # Intervalo semiaberto [km_start, km_end).
    km_start = Column(Float, nullable=False)
    km_end = Column(Float, nullable=False)

    scheduled_date = Column(Date, nullable=False, index=True)
    start_time = Column(String, nullable=True)  # "HH:MM"
    end_time = Column(String, nullable=True)  # "HH:MM"
    assignee = Column(String, nullable=True)  # texto livre por enquanto
    notes = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="MANUAL")  # MANUAL / SUGGESTION

    completed_at = Column(DateTime, nullable=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=True)
    # Como foi concluído: MANUAL (usuário) ou AUTO (uma inspeção enviada cobriu o trecho).
    # Só o AUTO pode ser reaberto.
    completion_source = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def is_overdue(self) -> bool:
        """Derivado (não é gravado): PLANNED com data anterior a hoje, no fuso de São Paulo."""
        return self.status == "PLANNED" and self.scheduled_date < clock.today()
