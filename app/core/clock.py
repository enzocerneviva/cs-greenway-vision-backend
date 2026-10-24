"""
Datas e horas da aplicação num lugar só.

- Instantes (created_at, completed_at...) são sempre UTC.
- "Hoje" e as datas de agenda (YYYY-MM-DD) seguem o fuso de São Paulo
  (app.core.config.TIMEZONE): às 22h de São Paulo já é "amanhã" em UTC, e a
  agenda não pode virar o dia três horas antes do usuário.

O SQLite não guarda fuso: datetimes lidos do banco voltam sem tzinfo, mas são
UTC. Por isso as funções abaixo tratam datetime sem tzinfo como UTC.

Quem precisa de "agora" ou "hoje" chama clock.today() / clock.utc_now() (pelo
módulo, não importando o nome) — assim os testes conseguem fixar a data.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE


def app_timezone() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return utc_now().astimezone(app_timezone()).date()


def to_local_date(value: datetime) -> date:
    """Dia (no fuso da aplicação) em que um instante aconteceu."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(app_timezone()).date()


def to_naive_utc(value: datetime) -> datetime:
    """Formato em que o SQLite guarda e devolve os instantes (UTC, sem tzinfo)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def end_of_day_utc(day: date) -> datetime:
    """Último instante do dia local, em UTC sem tzinfo (comparável com o que vem do banco)."""
    local_end = datetime.combine(day, time.max, tzinfo=app_timezone())
    return to_naive_utc(local_end)


def start_of_week(day: date) -> date:
    """Segunda-feira da semana de `day`."""
    return day - timedelta(days=day.weekday())
