"""Engines do SQLAlchemy.

Sao duas de proposito: a de escrita e usada pela ingestao e pelo registro de auditoria,
e a de leitura e a unica que as ferramentas do agente enxergam.
"""

from functools import lru_cache
from importlib import resources

from sqlalchemy import Engine, create_engine, text

from srag.config import get_config


def _criar(url: str, somente_leitura: bool) -> Engine:
    cfg = get_config()
    opcoes = f"-c statement_timeout={cfg.statement_timeout_ms}"
    if somente_leitura:
        opcoes += " -c default_transaction_read_only=on"
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": opcoes},
    )


@lru_cache
def engine_escrita() -> Engine:
    return _criar(get_config().database_url, somente_leitura=False)


@lru_cache
def engine_leitura() -> Engine:
    return _criar(get_config().url_leitura, somente_leitura=True)


def aplicar_schema() -> None:
    """Roda o schema.sql. E idempotente, entao pode ser chamado no boot da API."""
    ddl = resources.files("srag.db").joinpath("schema.sql").read_text(encoding="utf-8")
    with engine_escrita().begin() as conexao:
        conexao.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # O DDL tem blocos DO $$ ... $$, que o SQLAlchemy nao sabe separar por ';'.
        # Executar o arquivo inteiro de uma vez resolve, o driver aceita multiplos comandos.
        conexao.exec_driver_sql(ddl)
