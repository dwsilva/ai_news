"""Infraestrutura dos testes.

Os testes de metrica rodam contra um Postgres de verdade, num banco separado criado na hora.
Poderia ter usado sqlite ou mock, mas metade do que quero testar (FILTER, date_trunc, o cast
dos parametros nulos) e comportamento do proprio Postgres - mockar nao provaria nada.
"""

import os
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from srag.metricas.modelos import Filtro

BANCO_DE_TESTE = "srag_teste"


def _url_administrativa() -> str:
    return os.environ.get(
        "SRAG_DATABASE_URL", "postgresql+psycopg://srag:srag@localhost:55432/srag"
    )


def _url_do_teste(url_base: str) -> str:
    return url_base.rsplit("/", 1)[0] + f"/{BANCO_DE_TESTE}"


@pytest.fixture(scope="session")
def banco():
    """Cria o banco de teste, aplica o schema e devolve a engine de escrita."""
    url_base = _url_administrativa()
    administrativa = create_engine(url_base, isolation_level="AUTOCOMMIT")
    with administrativa.connect() as conexao:
        conexao.execute(text(f"DROP DATABASE IF EXISTS {BANCO_DE_TESTE} WITH (FORCE)"))
        conexao.execute(text(f"CREATE DATABASE {BANCO_DE_TESTE}"))
    administrativa.dispose()

    url_teste = _url_do_teste(url_base)
    os.environ["SRAG_DATABASE_URL"] = url_teste
    # O papel somente leitura e do cluster, entao vale para o banco novo tambem.
    leitura = url_teste.replace("srag:srag@", "srag_leitura:leitura@")
    os.environ["SRAG_DATABASE_URL_LEITURA"] = leitura
    _reiniciar_caches()

    from srag.db import aplicar_schema, engine_escrita

    aplicar_schema()
    yield engine_escrita()

    _reiniciar_caches()


def _reiniciar_caches() -> None:
    from srag.config import get_config
    from srag.db.engine import engine_escrita, engine_leitura

    get_config.cache_clear()
    engine_escrita.cache_clear()
    engine_leitura.cache_clear()


@pytest.fixture
def limpar(banco):
    with banco.begin() as conexao:
        conexao.execute(text("TRUNCATE srag.internacao"))
    return banco


@pytest.fixture
def inserir(limpar):
    """Insere internacoes sinteticas. So os campos citados no teste precisam ser passados."""

    def _inserir(*registros: dict) -> None:
        linhas = []
        for indice, registro in enumerate(registros):
            linha = {
                "chave_notificacao": f"teste-{indice}",
                "ano_base": 2026,
                "dt_sintomas": date(2026, 6, 15),
                "uf_notificacao": "SC",
                "evolucao": "Ignorado",
                "uti": "Ignorado",
                "vacina_covid": "Ignorado",
                "faixa_etaria": "40 a 49 anos",
                "classificacao_final": "SRAG não especificado",
                "dias_uti": None,
            }
            linha.update(registro)
            linhas.append(linha)

        colunas = list(linhas[0])
        comando = text(
            f"INSERT INTO srag.internacao ({', '.join(colunas)}) "
            f"VALUES ({', '.join(':' + coluna for coluna in colunas)})"
        )
        with limpar.begin() as conexao:
            conexao.execute(comando, linhas)

    return _inserir


@pytest.fixture
def filtro_padrao():
    return Filtro(janela_dias=30, data_referencia=date(2026, 6, 30))


@pytest.fixture
def dia():
    """Atalho para montar datas relativas a data de referencia usada nos testes."""

    def _dia(deslocamento: int) -> date:
        return date(2026, 6, 30) - timedelta(days=deslocamento)

    return _dia
