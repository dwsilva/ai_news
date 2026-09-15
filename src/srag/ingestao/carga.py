"""Leitura do CSV do SIVEP em blocos e carga no Postgres."""

import io
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from srag.db import engine_escrita
from srag.ingestao.download import baixar, hash_do_arquivo, resolver_url
from srag.ingestao.dominios import COLUNAS_ORIGEM
from srag.ingestao.transform import (
    COLUNAS_DESTINO,
    descartar_sem_data_de_sintomas,
    normalizar,
)

logger = logging.getLogger(__name__)

TAMANHO_BLOCO = 50_000
COLUNAS_INTEIRAS = ["semana_epi", "dias_uti", "doses_covid"]


@dataclass(frozen=True)
class ResumoCarga:
    ano_base: int
    arquivo_origem: str
    hash_arquivo: str
    linhas_lidas: int
    linhas_gravadas: int
    linhas_descartadas: int

    def como_dicionario(self) -> dict:
        return asdict(self)


def carregar_ano(ano: int, url: str | None = None, limite: int | None = None) -> ResumoCarga:
    inicio = datetime.now(UTC)
    endereco = url or resolver_url(ano)
    caminho = baixar(endereco)
    logger.info("processando %s", caminho.name)

    lidas = gravadas = descartadas = 0
    with engine_escrita().begin() as conexao:
        _criar_area_de_estagio(conexao)
        for bloco in _blocos(caminho, limite):
            lidas += len(bloco)
            normalizado = normalizar(bloco, ano)
            normalizado, sem_data = descartar_sem_data_de_sintomas(normalizado)
            descartadas += sem_data
            _copiar_para_estagio(conexao, normalizado)
            logger.info("  %d linhas lidas", lidas)

        gravadas = _consolidar(conexao)
        resumo = ResumoCarga(
            ano_base=ano,
            arquivo_origem=endereco,
            hash_arquivo=hash_do_arquivo(caminho),
            linhas_lidas=lidas,
            linhas_gravadas=gravadas,
            linhas_descartadas=descartadas,
        )
        _registrar_carga(conexao, resumo, inicio)

    logger.info(
        "carga de %s concluida: %d lidas, %d gravadas, %d descartadas",
        ano,
        lidas,
        gravadas,
        descartadas,
    )
    return resumo


def _blocos(caminho: Path, limite: int | None):
    """Le o CSV em pedacos. O arquivo tem ~1 GB, entao ler inteiro em memoria nao e opcao."""
    colunas = set(COLUNAS_ORIGEM)
    leitor = pd.read_csv(
        caminho,
        sep=";",
        encoding="latin-1",
        dtype=str,
        usecols=lambda coluna: coluna in colunas,
        chunksize=TAMANHO_BLOCO,
        low_memory=False,
    )
    total = 0
    for bloco in leitor:
        if limite is not None and total + len(bloco) > limite:
            bloco = bloco.head(limite - total)
        if bloco.empty:
            return
        total += len(bloco)
        yield bloco
        if limite is not None and total >= limite:
            return


def _criar_area_de_estagio(conexao) -> None:
    colunas = ", ".join(f"{nome} text" for nome in COLUNAS_DESTINO)
    conexao.execute(text(f"CREATE TEMP TABLE estagio_internacao ({colunas}) ON COMMIT DROP"))


def _copiar_para_estagio(conexao, dados: pd.DataFrame) -> None:
    if dados.empty:
        return
    preparado = dados.copy()
    for coluna in COLUNAS_INTEIRAS:
        preparado[coluna] = pd.to_numeric(preparado[coluna], errors="coerce").astype("Int64")

    buffer = io.StringIO()
    preparado.to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)

    cursor = conexao.connection.cursor()
    comando = (
        f"COPY estagio_internacao ({', '.join(COLUNAS_DESTINO)}) "
        "FROM STDIN WITH (FORMAT csv, NULL '')"
    )
    with cursor.copy(comando) as copia:
        copia.write(buffer.read())


def _consolidar(conexao) -> int:
    """Move o estagio para a tabela final ignorando notificacoes ja carregadas."""
    colunas = ", ".join(COLUNAS_DESTINO)
    conversao = ", ".join(_expressao_de_cast(nome) for nome in COLUNAS_DESTINO)
    resultado = conexao.execute(
        text(
            f"INSERT INTO srag.internacao ({colunas}) "
            f"SELECT DISTINCT ON (chave_notificacao) {conversao} "
            "FROM estagio_internacao "
            "ON CONFLICT (chave_notificacao) DO NOTHING"
        )
    )
    return resultado.rowcount


def _expressao_de_cast(coluna: str) -> str:
    if coluna.startswith("dt_"):
        return f"NULLIF({coluna}, '')::date"
    if coluna in COLUNAS_INTEIRAS:
        return f"NULLIF({coluna}, '')::numeric::smallint"
    if coluna == "ano_base":
        return f"{coluna}::smallint"
    return coluna


def _registrar_carga(conexao, resumo: ResumoCarga, inicio: datetime) -> None:
    conexao.execute(
        text(
            "INSERT INTO srag.carga (ano_base, arquivo_origem, hash_arquivo, linhas_lidas, "
            "linhas_gravadas, linhas_descartadas, iniciada_em) "
            "VALUES (:ano_base, :arquivo_origem, :hash_arquivo, :linhas_lidas, "
            ":linhas_gravadas, :linhas_descartadas, :inicio)"
        ),
        {**resumo.como_dicionario(), "inicio": inicio},
    )
