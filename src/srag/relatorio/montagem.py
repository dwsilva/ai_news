"""Montagem do relatorio em Markdown.

Markdown e o formato canonico: e o que fica legivel no repositorio, o que vira HTML na tela e
o que vira PDF. O texto do modelo entra so nos lugares marcados; cabecalho, tabelas de
metricas, graficos, fontes e apendice de auditoria sao montados por este modulo.
"""

from datetime import datetime

from srag.agente.estado import Redacao
from srag.metricas.modelos import MetricaCalculada, Painel
from srag.noticias.modelos import Fonte

AVISO = (
    "> Relatório gerado automaticamente a partir dos microdados públicos do SIVEP-Gripe "
    "(Open DATASUS) e de notícias coletadas na data de emissão. Destina-se a apoiar a leitura "
    "do cenário epidemiológico coletivo e **não** substitui avaliação clínica, boletim oficial "
    "ou decisão assistencial individual."
)


def montar(
    run_id: str,
    painel: Painel,
    redacao: Redacao | None,
    fontes: list[Fonte],
    graficos: dict[str, str],
    dossie_consulta: str = "",
    artigos_recusados: int = 0,
    ressalva: str = "",
) -> str:
    partes = [
        _cabecalho(painel, run_id),
        AVISO,
        _panorama(redacao, ressalva),
        _indicadores(painel, redacao),
        _graficos(painel, graficos),
        _alertas(redacao),
        _fontes(fontes),
        _auditoria(run_id, painel, dossie_consulta, fontes, artigos_recusados),
    ]
    return "\n\n".join(parte for parte in partes if parte).strip() + "\n"


def _cabecalho(painel: Painel, run_id: str) -> str:
    recorte = painel.filtro.uf or "Brasil"
    janela = painel.metricas[0].janela if painel.metricas else None
    linhas = [
        "# Relatório de situação — Síndrome Respiratória Aguda Grave",
        "",
        f"- **Recorte:** {recorte}",
        f"- **Data de referência:** {painel.data_referencia:%d/%m/%Y}",
    ]
    if janela:
        linhas.append(f"- **Janela de análise:** {janela.descricao()} ({janela.dias} dias)")
    linhas += [
        f"- **Registros na base:** {_milhar(painel.total_registros)} internações notificadas",
        f"- **Emitido em:** {datetime.now():%d/%m/%Y às %H:%M}",
        f"- **Identificador da execução:** `{run_id}`",
    ]
    return "\n".join(linhas)


def _panorama(redacao: Redacao | None, ressalva: str) -> str:
    if ressalva:
        return f"## Panorama\n\n{ressalva}"
    if not redacao:
        return ""
    return f"## Panorama\n\n{redacao.panorama}"


def _indicadores(painel: Painel, redacao: Redacao | None) -> str:
    blocos = ["## Indicadores"]
    for metrica in painel.metricas:
        blocos.append(_bloco_da_metrica(metrica, redacao))
    return "\n\n".join(blocos)


def _bloco_da_metrica(metrica: MetricaCalculada, redacao: Redacao | None) -> str:
    linhas = [f"### {metrica.nome}: {metrica.formatado()}", ""]

    linhas += [
        "| Numerador | Denominador | Sem informação | Período |",
        "| --- | --- | --- | --- |",
        f"| {_milhar(metrica.numerador)} | {_milhar(metrica.denominador)} "
        f"| {_milhar(metrica.ignorados)} | {metrica.janela.descricao()} |",
    ]

    if metrica.quebras:
        linhas += ["", "| Recorte | Valor | Base |", "| --- | --- | --- |"]
        for quebra in metrica.quebras:
            linhas.append(
                f"| {quebra.rotulo} | {quebra.formatado()} | {_milhar(quebra.denominador)} |"
            )

    comentario = redacao.comentario(metrica.codigo) if redacao else ""
    if comentario:
        linhas += ["", comentario]

    if metrica.limitacao:
        linhas += ["", f"*Como ler:* {metrica.limitacao}"]

    return "\n".join(linhas)


def _graficos(painel: Painel, caminhos: dict[str, str]) -> str:
    if not caminhos:
        return ""
    blocos = ["## Evolução dos casos"]
    for serie in painel.series:
        arquivo = caminhos.get(serie.codigo)
        if not arquivo:
            continue
        nome = arquivo.replace("\\", "/").rsplit("/", 1)[-1]
        blocos.append(f"![{serie.titulo}]({nome})\n\n*{serie.titulo}.*")
    return "\n\n".join(blocos)


def _alertas(redacao: Redacao | None) -> str:
    if not redacao or not redacao.sinais_de_alerta:
        return ""
    itens = "\n".join(f"- {sinal}" for sinal in redacao.sinais_de_alerta)
    return f"## Sinais de alerta\n\n{itens}"


def _fontes(fontes: list[Fonte]) -> str:
    if not fontes:
        return "## Fontes consultadas\n\nNenhuma notícia foi recuperada para este recorte."
    itens = "\n".join(f"{fonte.citacao()}" for fonte in fontes)
    return f"## Fontes consultadas\n\n{itens}"


def _auditoria(
    run_id: str,
    painel: Painel,
    dossie_consulta: str,
    fontes: list[Fonte],
    artigos_recusados: int,
) -> str:
    linhas = [
        "## Apêndice: rastreabilidade",
        "",
        f"- Identificador da execução: `{run_id}`",
        f"- Recorte consultado: {painel.filtro.descricao()}",
        f"- Registros considerados: {_milhar(painel.total_registros)}",
        f"- Busca de notícias: {dossie_consulta or 'não realizada'}",
        f"- Artigos citados: {len(fontes)} | descartados na triagem de injeção: "
        f"{artigos_recusados}",
        "",
        "Consultas SQL que produziram cada indicador:",
        "",
    ]
    for metrica in painel.metricas:
        linhas += [
            f"**{metrica.nome}** — parâmetros: `{metrica.parametros}`",
            "",
            "```sql",
            metrica.consulta.strip(),
            "```",
            "",
        ]
    linhas.append(
        "A trilha completa da execução (cada etapa, cada chamada ao modelo e cada guardrail "
        f"acionado) está em `GET /api/execucoes/{run_id}/auditoria`."
    )
    return "\n".join(linhas)


def _milhar(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")
