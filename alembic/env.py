from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401 — registra todas as tabelas em Base.metadata
from app.database.session import SQLALCHEMY_DATABASE_URL, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# É com esse "mapa" dos models que o Alembic compara o banco e descobre o que
# falta (alembic revision --autogenerate).
target_metadata = Base.metadata


def _database_url() -> str:
    # Por padrão usa o mesmo banco da aplicação. Pra apontar pra outro banco
    # (ex.: um arquivo de teste) sem mexer no código:
    #   alembic -x url=sqlite:///outro.db upgrade head
    return context.get_x_argument(as_dictionary=True).get("url", SQLALCHEMY_DATABASE_URL)


def run_migrations_online() -> None:
    engine = create_engine(_database_url())

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite não altera nem remove coluna diretamente; no modo "batch"
            # o Alembic recria a tabela por baixo quando for preciso.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
