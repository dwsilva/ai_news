"""Normalizacao do CSV bruto do SIVEP-Gripe para o formato gravado no banco."""

from datetime import date

import pandas as pd

from srag.ingestao import dominios as dom
from srag.ingestao.anonimizacao import (
    chave_pseudonimizada,
    faixa_etaria,
    garantir_ausencia_de_identificadores,
)

# A ficha comecou a ser preenchida no formato atual em 2009; qualquer data fora desse
# intervalo e erro de digitacao e nao deve virar serie temporal.
DATA_MINIMA = date(2009, 1, 1)

COLUNAS_DESTINO = [
    "chave_notificacao",
    "ano_base",
    "dt_notificacao",
    "dt_sintomas",
    "semana_epi",
    "uf_notificacao",
    "uf_residencia",
    "sexo",
    "faixa_etaria",
    "classificacao_final",
    "criterio_encerramento",
    "hospitalizado",
    "dt_internacao",
    "uti",
    "dt_entrada_uti",
    "dt_saida_uti",
    "dias_uti",
    "suporte_ventilatorio",
    "evolucao",
    "dt_evolucao",
    "dt_encerramento",
    "vacina_gripe",
    "vacina_covid",
    "doses_covid",
    "pcr_resultado",
]


def _datas(serie: pd.Series) -> pd.Series:
    texto = serie.astype("string").str.strip()
    if _parece_iso(texto):
        # Os arquivos mais recentes vem em ISO 8601 com fuso: "2026-01-11T00:00:00.000Z".
        convertida = pd.to_datetime(texto, format="ISO8601", errors="coerce", utc=True)
        convertida = convertida.dt.tz_localize(None)
    else:
        convertida = pd.to_datetime(texto, format="%d/%m/%Y", errors="coerce")

    limite = pd.Timestamp(date.today())
    fora_do_intervalo = (convertida < pd.Timestamp(DATA_MINIMA)) | (convertida > limite)
    return convertida.mask(fora_do_intervalo).dt.date


def _parece_iso(texto: pd.Series) -> bool:
    amostra = texto.dropna().head(50)
    if amostra.empty:
        return False
    return bool(amostra.str.match(r"\d{4}-\d{2}-\d{2}").mean() > 0.5)


def _codigos(serie: pd.Series, mapa: dict[str, str], padrao: str = dom.IGNORADO) -> pd.Series:
    normalizada = serie.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return normalizada.map(mapa).fillna(padrao)


def _idade_em_anos(valor: pd.Series, unidade: pd.Series) -> pd.Series:
    numero = pd.to_numeric(valor, errors="coerce")
    unidade_normalizada = unidade.astype("string").str.strip()
    # TP_IDADE 1 e 2 sao dias e meses: para as faixas etarias usadas nos boletins,
    # qualquer um dos dois cai em "menor de 1 ano".
    em_anos = numero.where(unidade_normalizada == "3", 0)
    return em_anos.mask(numero.isna()).mask(em_anos > 130)


def _uf(serie: pd.Series) -> pd.Series:
    normalizada = serie.astype("string").str.strip().str.upper()
    return normalizada.where(normalizada.isin(dom.UFS))


def normalizar(bruto: pd.DataFrame, ano_base: int) -> pd.DataFrame:
    """Converte um chunk do CSV original no formato de srag.internacao."""
    origem = bruto.reindex(columns=dom.COLUNAS_ORIGEM)
    saida = pd.DataFrame(index=origem.index)

    saida["chave_notificacao"] = [
        chave_pseudonimizada(ano_base, notificacao, municipio, notificado, sintomas)
        for notificacao, municipio, notificado, sintomas in zip(
            origem["NU_NOTIFIC"],
            origem["CO_MUN_NOT"],
            origem["DT_NOTIFIC"],
            origem["DT_SIN_PRI"],
            strict=True,
        )
    ]
    saida["ano_base"] = ano_base

    saida["dt_notificacao"] = _datas(origem["DT_NOTIFIC"])
    saida["dt_sintomas"] = _datas(origem["DT_SIN_PRI"])
    saida["semana_epi"] = pd.to_numeric(origem["SEM_PRI"], errors="coerce")

    saida["uf_notificacao"] = _uf(origem["SG_UF_NOT"])
    saida["uf_residencia"] = _uf(origem["SG_UF"])

    saida["sexo"] = _codigos(origem["CS_SEXO"], dom.SEXO)
    idade = _idade_em_anos(origem["NU_IDADE_N"], origem["TP_IDADE"])
    saida["faixa_etaria"] = idade.map(faixa_etaria)

    saida["classificacao_final"] = _codigos(
        origem["CLASSI_FIN"], dom.CLASSIFICACAO_FINAL, padrao="Nao classificado"
    )
    saida["criterio_encerramento"] = _codigos(origem["CRITERIO"], dom.CRITERIO_ENCERRAMENTO)

    saida["hospitalizado"] = _codigos(origem["HOSPITAL"], dom.SIM_NAO)
    saida["dt_internacao"] = _datas(origem["DT_INTERNA"])

    saida["uti"] = _codigos(origem["UTI"], dom.SIM_NAO)
    saida["dt_entrada_uti"] = _datas(origem["DT_ENTUTI"])
    saida["dt_saida_uti"] = _datas(origem["DT_SAIDUTI"])
    saida["dias_uti"] = _dias_de_uti(saida["dt_entrada_uti"], saida["dt_saida_uti"])
    saida["suporte_ventilatorio"] = _codigos(origem["SUPORT_VEN"], dom.SUPORTE_VENTILATORIO)

    saida["evolucao"] = _codigos(origem["EVOLUCAO"], dom.EVOLUCAO)
    saida["dt_evolucao"] = _datas(origem["DT_EVOLUCA"])
    saida["dt_encerramento"] = _datas(origem["DT_ENCERRA"])

    saida["vacina_gripe"] = _codigos(origem["VACINA"], dom.SIM_NAO)
    saida["vacina_covid"] = _codigos(origem["VACINA_COV"], dom.SIM_NAO)
    saida["doses_covid"] = _doses_aplicadas(origem)
    saida["pcr_resultado"] = _codigos(origem["PCR_RESUL"], dom.PCR_RESULTADO)

    saida = saida[COLUNAS_DESTINO]
    garantir_ausencia_de_identificadores(saida)
    return saida


def _dias_de_uti(entrada: pd.Series, saida: pd.Series) -> pd.Series:
    inicio = pd.to_datetime(entrada, errors="coerce")
    fim = pd.to_datetime(saida, errors="coerce")
    dias = (fim - inicio).dt.days
    # Saida antes da entrada e erro de preenchimento; internacao de mais de um ano
    # em UTI tambem. Nos dois casos prefiro nao ter o dado a ter um dado errado.
    return dias.mask((dias < 0) | (dias > 365))


def _doses_aplicadas(origem: pd.DataFrame) -> pd.Series:
    colunas = ["DOSE_1_COV", "DOSE_2_COV", "DOSE_REF"]
    preenchidas = [
        _datas(origem[coluna]).notna().astype(int) for coluna in colunas if coluna in origem
    ]
    if not preenchidas:
        return pd.Series(0, index=origem.index)
    return sum(preenchidas)


def descartar_sem_data_de_sintomas(dados: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Notificacao sem data de primeiros sintomas nao entra em nenhuma serie temporal.

    Devolve o dataframe filtrado e quantas linhas foram descartadas, para a auditoria da carga.
    """
    validas = dados["dt_sintomas"].notna()
    return dados[validas], int((~validas).sum())
