"""Camada de minimizacao e generalizacao aplicada na entrada dos dados.

A base do Open DATASUS ja e publicada anonimizada, mas ela ainda traz quase-identificadores
suficientes para reidentificacao em recortes pequenos (data de nascimento, municipio de
residencia, campos de texto livre da ficha). O que este modulo faz e reduzir isso antes de
qualquer dado ser gravado, e nao depois.
"""

import hashlib

import pandas as pd

from srag.ingestao.dominios import FAIXAS_ETARIAS, IGNORADO

# Se alguma dessas colunas aparecer no dataframe que vai para o banco, e bug.
COLUNAS_PROIBIDAS = frozenset(
    {
        "NU_NOTIFIC",
        "DT_NASC",
        "CO_MUN_RES",
        "ID_MN_RESI",
        "ID_MUNICIP",
        "CO_MUN_NOT",
        "ID_UNIDADE",
        "CO_UNI_NOT",
        "NM_PACIENT",
        "NM_MAE_PAC",
        "NU_CPF",
        "NU_CNS",
        "NU_CEP",
        "NU_TELEFON",
        "MORB_DESC",
        "OUTRO_DES",
        "DS_IF_OUT",
        "OUT_AMOST",
    }
)


class IdentificadorResidual(RuntimeError):
    """Levantado quando um identificador direto escapa da selecao de colunas."""


def faixa_etaria(idade_anos: float | None) -> str:
    if idade_anos is None or pd.isna(idade_anos) or idade_anos < 0:
        return IGNORADO
    idade = int(idade_anos)
    for minimo, maximo, rotulo in FAIXAS_ETARIAS:
        if minimo <= idade <= maximo:
            return rotulo
    return IGNORADO


def chave_pseudonimizada(*partes: object) -> str:
    """Identificador estavel da notificacao, sem carregar o numero original.

    Serve so para deduplicar recargas do mesmo arquivo. Como o hash nao e reversivel,
    o numero da notificacao nunca chega a ser persistido.
    """
    bruto = "|".join("" if p is None or pd.isna(p) else str(p) for p in partes)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:32]


def garantir_ausencia_de_identificadores(dados: pd.DataFrame) -> None:
    residuais = COLUNAS_PROIBIDAS.intersection(dados.columns)
    if residuais:
        raise IdentificadorResidual(
            f"colunas identificadoras chegaram na carga: {sorted(residuais)}"
        )
