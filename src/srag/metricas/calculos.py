"""Calculo das metricas do relatorio.

Nenhuma funcao daqui conversa com o modelo de linguagem. Elas leem o banco pela conexao
somente leitura e devolvem objetos fechados, com numerador, denominador e consulta.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import text

from srag.config import get_config
from srag.db import engine_leitura
from srag.metricas import consultas
from srag.metricas.modelos import (
    Filtro,
    Janela,
    MetricaCalculada,
    Painel,
    PontoSerie,
    Quebra,
    SerieTemporal,
)

logger = logging.getLogger(__name__)

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


class BaseVazia(RuntimeError):
    """Nao ha dados carregados para o recorte pedido."""


def montar_painel(filtro: Filtro) -> Painel:
    referencia, total = _data_de_referencia(filtro)
    janela = Janela(inicio=referencia - timedelta(days=filtro.janela_dias - 1), fim=referencia)

    metricas = [
        taxa_de_aumento(filtro, janela),
        taxa_de_mortalidade(filtro, janela),
        taxa_de_ocupacao_de_uti(filtro, janela),
        taxa_de_vacinacao(filtro, janela),
    ]
    series = [serie_diaria(filtro, referencia), serie_mensal(filtro, referencia)]

    return Painel(
        filtro=filtro,
        data_referencia=referencia,
        metricas=metricas,
        series=series,
        total_registros=total,
    )


def _parametros(filtro: Filtro, **extras) -> dict:
    return {"uf": filtro.uf, "classificacao": filtro.classificacao_final, **extras}


def _uma_linha(sql: str, parametros: dict):
    with engine_leitura().connect() as conexao:
        return conexao.execute(text(sql), parametros).one()


def _linhas(sql: str, parametros: dict):
    with engine_leitura().connect() as conexao:
        return conexao.execute(text(sql), parametros).all()


def _data_de_referencia(filtro: Filtro) -> tuple[date, int]:
    """Define ate onde a analise vai.

    Se o usuario nao pedir uma data, uso a ultima data de inicio de sintomas presente na base
    descontando a janela de atraso de notificacao: os dias mais recentes ainda estao sendo
    digitados e apareceriam como uma queda de casos que nao aconteceu.
    """
    linha = _uma_linha(consultas.ULTIMA_DATA, _parametros(filtro))
    if linha.ultima_data is None:
        raise BaseVazia("nenhuma internação carregada para o recorte pedido")

    if filtro.data_referencia:
        return min(filtro.data_referencia, linha.ultima_data), linha.total
    return linha.ultima_data - timedelta(days=get_config().atraso_notificacao_dias), linha.total


def taxa_de_aumento(filtro: Filtro, janela: Janela) -> MetricaCalculada:
    dias = janela.dias
    parametros = _parametros(
        filtro,
        fim=janela.fim,
        corte=janela.fim - timedelta(days=dias),
        inicio_anterior=janela.fim - timedelta(days=2 * dias - 1),
    )
    linha = _uma_linha(consultas.VARIACAO_DE_CASOS, parametros)

    anterior = linha.periodo_anterior
    valor = None if anterior == 0 else (linha.periodo_atual / anterior - 1) * 100

    limitacao = (
        f"Compara os últimos {dias} dias com os {dias} dias imediatamente anteriores, por data "
        f"de início de sintomas. A janela termina {get_config().atraso_notificacao_dias} dias "
        "antes do último registro da base para não confundir atraso de notificação com queda "
        "de casos."
    )

    return MetricaCalculada(
        codigo="taxa_aumento_casos",
        nome="Taxa de aumento de casos",
        valor=valor,
        unidade="%",
        numerador=linha.periodo_atual,
        denominador=anterior,
        janela=janela,
        limitacao=limitacao,
        consulta=consultas.VARIACAO_DE_CASOS,
        parametros=_serializavel(parametros),
    )


def taxa_de_mortalidade(filtro: Filtro, janela: Janela) -> MetricaCalculada:
    parametros = _parametros(filtro, inicio=janela.inicio, fim=janela.fim)
    linha = _uma_linha(consultas.MORTALIDADE, parametros)

    denominador = linha.com_desfecho
    valor = None if denominador == 0 else linha.obitos_srag / denominador * 100

    limitacao = (
        "Óbitos por SRAG sobre os casos já encerrados no período. "
        f"{linha.sem_desfecho} casos da janela ainda estão sem desfecho registrado e ficam fora "
        "do denominador, o que tende a subestimar a taxa nos dias mais recentes."
    )

    return MetricaCalculada(
        codigo="taxa_mortalidade",
        nome="Taxa de mortalidade",
        valor=valor,
        unidade="%",
        numerador=linha.obitos_srag,
        denominador=denominador,
        ignorados=linha.sem_desfecho,
        janela=janela,
        limitacao=limitacao,
        quebras=[
            _quebra("Óbitos por SRAG", linha.obitos_srag, denominador),
            _quebra("Óbitos por outras causas", linha.obitos_outras_causas, denominador),
        ],
        consulta=consultas.MORTALIDADE,
        parametros=_serializavel(parametros),
    )


def taxa_de_ocupacao_de_uti(filtro: Filtro, janela: Janela) -> MetricaCalculada:
    parametros = _parametros(filtro, inicio=janela.inicio, fim=janela.fim)
    linha = _uma_linha(consultas.OCUPACAO_UTI, parametros)

    denominador = linha.com_informacao
    valor = None if denominador == 0 else linha.em_uti / denominador * 100

    quebras = []
    if linha.media_dias_uti is not None:
        quebras.append(
            Quebra(
                rotulo="Permanência média em UTI (dias)",
                numerador=linha.em_uti,
                denominador=linha.em_uti,
                valor=round(float(linha.media_dias_uti), 1),
            )
        )

    limitacao = (
        "O SIVEP-Gripe não informa leitos disponíveis, então isto não é ocupação de leitos: é a "
        "proporção de internações por SRAG que passaram pela UTI, entre as fichas com o campo "
        "preenchido. Serve como indicador de gravidade, não de capacidade instalada."
    )

    return MetricaCalculada(
        codigo="taxa_ocupacao_uti",
        nome="Taxa de ocupação de UTI",
        valor=valor,
        unidade="%",
        numerador=linha.em_uti,
        denominador=denominador,
        ignorados=linha.ignorados,
        janela=janela,
        limitacao=limitacao,
        quebras=quebras,
        consulta=consultas.OCUPACAO_UTI,
        parametros=_serializavel(parametros),
    )


def taxa_de_vacinacao(filtro: Filtro, janela: Janela) -> MetricaCalculada:
    parametros = _parametros(filtro, inicio=janela.inicio, fim=janela.fim)
    linha = _uma_linha(consultas.VACINACAO, parametros)
    por_faixa = _linhas(consultas.VACINACAO_POR_FAIXA, parametros)

    denominador = linha.com_informacao
    valor = None if denominador == 0 else linha.vacinados / denominador * 100

    limitacao = (
        "É a cobertura vacinal declarada entre os casos notificados de SRAG, não a cobertura da "
        "população geral: a base só enxerga quem adoeceu o suficiente para ser notificado. Serve "
        "para comparar o perfil vacinal dos casos graves, não para medir a campanha."
    )

    return MetricaCalculada(
        codigo="taxa_vacinacao",
        nome="Taxa de vacinação contra covid-19",
        valor=valor,
        unidade="%",
        numerador=linha.vacinados,
        denominador=denominador,
        ignorados=linha.ignorados,
        janela=janela,
        limitacao=limitacao,
        quebras=_suprimir_pequenas(
            [_quebra(faixa.rotulo, faixa.numerador, faixa.denominador) for faixa in por_faixa]
        ),
        consulta=consultas.VACINACAO,
        parametros=_serializavel(parametros),
    )


def serie_diaria(filtro: Filtro, referencia: date, dias: int = 30) -> SerieTemporal:
    inicio = referencia - timedelta(days=dias - 1)
    parametros = _parametros(filtro, inicio=inicio, fim=referencia)
    contagem = {linha.data: linha.casos for linha in _linhas(consultas.CASOS_POR_DIA, parametros)}

    pontos = []
    for deslocamento in range(dias):
        dia = inicio + timedelta(days=deslocamento)
        pontos.append(PontoSerie(rotulo=f"{dia:%d/%m}", data=dia, casos=contagem.get(dia, 0)))

    return SerieTemporal(
        codigo="casos_diarios",
        titulo=f"Casos diários de SRAG nos últimos {dias} dias",
        pontos=pontos,
    )


def serie_mensal(filtro: Filtro, referencia: date, meses: int = 12) -> SerieTemporal:
    inicio = _recuar_meses(referencia.replace(day=1), meses - 1)
    parametros = _parametros(filtro, inicio=inicio, fim=referencia)
    contagem = {linha.data: linha.casos for linha in _linhas(consultas.CASOS_POR_MES, parametros)}

    pontos = []
    mes = inicio
    for _ in range(meses):
        rotulo = f"{MESES[mes.month - 1]}/{mes:%y}"
        # A janela termina na data de referencia, entao o ultimo mes so esta completo
        # se a referencia cair na vespera do mes seguinte.
        parcial = mes == referencia.replace(day=1) and _avancar_mes(mes) > referencia + timedelta(
            days=1
        )
        pontos.append(
            PontoSerie(rotulo=rotulo, data=mes, casos=contagem.get(mes, 0), parcial=parcial)
        )
        mes = _avancar_mes(mes)

    return SerieTemporal(
        codigo="casos_mensais",
        titulo=f"Casos mensais de SRAG nos últimos {meses} meses",
        pontos=pontos,
    )


def _quebra(rotulo: str, numerador: int, denominador: int) -> Quebra:
    valor = None if denominador == 0 else round(numerador / denominador * 100, 1)
    return Quebra(rotulo=rotulo, numerador=numerador, denominador=denominador, valor=valor)


def _suprimir_pequenas(quebras: list[Quebra]) -> list[Quebra]:
    """Esconde recortes com poucos registros.

    Um percentual calculado sobre tres pessoas nao informa nada epidemiologicamente e ainda
    abre espaco para reidentificacao quando cruzado com UF e faixa etaria.
    """
    minimo = get_config().k_anonimato
    mantidas = []
    for quebra in quebras:
        if quebra.denominador < minimo:
            logger.debug("quebra '%s' suprimida (n=%d)", quebra.rotulo, quebra.denominador)
            continue
        mantidas.append(quebra)
    return mantidas


def _recuar_meses(referencia: date, meses: int) -> date:
    total = referencia.year * 12 + (referencia.month - 1) - meses
    return date(total // 12, total % 12 + 1, 1)


def _avancar_mes(referencia: date) -> date:
    return _recuar_meses(referencia, -1)


def _serializavel(parametros: dict) -> dict:
    return {
        chave: valor.isoformat() if isinstance(valor, date) else valor
        for chave, valor in parametros.items()
    }
