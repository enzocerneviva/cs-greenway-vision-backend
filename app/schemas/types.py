from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import PlainSerializer

# Valores fixos aceitos pela API. Usar Literal (em vez de str) faz o FastAPI
# validar a entrada e documentar os valores permitidos no /openapi.json —
# o openapi-typescript do frontend gera, a partir disso, uniões de strings
# em vez de um "string" genérico.
Priority = Literal["LOW", "MEDIUM", "HIGH"]
Direction = Literal["CAPITAL", "INTERIOR"]
InspectionStatus = Literal["PROCESSING", "DONE", "FAILED"]


def _to_utc_iso(value: datetime) -> str:
    # O SQLite não guarda fuso: o valor gravado é UTC, mas volta como
    # datetime "ingênuo" (sem tzinfo), que o navegador leria como horário
    # local. Aqui assumimos UTC e serializamos com "Z" no final.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str, when_used="json")]
