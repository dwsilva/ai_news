"""Ferramentas do agente.

Cada funcao aqui e uma capacidade que o orquestrador aciona: consultar o banco, desenhar os
graficos, buscar noticias, indexar e recuperar contexto. Todas recebem o auditor e registram
parametros e resultado, entao a trilha de uma execucao mostra a sequencia inteira de acoes.

As ferramentas sao deterministicas de proposito. O modelo nao escolhe parametro de consulta
nem monta SQL; ele escolhe apenas as perguntas de recuperacao (veja o no planejar_buscas).
"""

import logging
from pathlib import Path

from srag import graficos
from srag.auditoria import Auditor
from srag.config import get_config
from srag.metricas.calculos import montar_painel
from srag.metricas.modelos import Filtro, Painel, SerieTemporal
from srag.noticias import indexacao
from srag.noticias.coleta import coletar
from srag.noticias.indexacao import Embeddings
from srag.noticias.modelos import Dossie, Fonte, Trecho

logger = logging.getLogger(__name__)


def consultar_metricas(auditor: Auditor, filtro: Filtro) -> Painel:
    with auditor.etapa("metricas", "consultar_banco", **filtro.model_dump(mode="json")) as reg:
        painel = montar_painel(filtro)
        reg.resultado = {
            "data_referencia": str(painel.data_referencia),
            "total_registros": painel.total_registros,
            "valores": {
                metrica.codigo: {
                    "valor": metrica.valor,
                    "numerador": metrica.numerador,
                    "denominador": metrica.denominador,
                    "consulta": metrica.consulta.strip(),
                    "parametros": metrica.parametros,
                }
                for metrica in painel.metricas
            },
        }
    return painel


def desenhar_graficos(auditor: Auditor, series: list[SerieTemporal], run_id: str) -> dict[str, str]:
    destino = Path(get_config().dir_relatorios) / run_id
    with auditor.etapa("graficos", "gerar_png", destino=str(destino)) as reg:
        caminhos = graficos.gerar(series, destino)
        reg.resultado = {codigo: str(caminho) for codigo, caminho in caminhos.items()}
    return {codigo: str(caminho) for codigo, caminho in caminhos.items()}


def buscar_noticias(auditor: Auditor, uf: str | None) -> Dossie:
    cfg = get_config()
    with auditor.etapa(
        "noticias",
        "buscar_rss",
        uf=uf,
        janela_dias=cfg.noticias_janela_dias,
        maximo=cfg.noticias_max_artigos,
    ) as reg:
        dossie = coletar(uf=uf)
        reg.resultado = {
            "consulta": dossie.consulta,
            "aceitos": len(dossie.artigos),
            "recusados": len(dossie.recusados),
            "com_texto_integral": sum(1 for a in dossie.artigos if a.texto_completo),
            "veiculos": sorted({a.veiculo for a in dossie.artigos if a.veiculo}),
        }

    aprovado = not dossie.recusados
    detalhe = (
        "nenhum artigo com padrao de injecao"
        if aprovado
        else f"{len(dossie.recusados)} artigos descartados na triagem"
    )
    auditor.guardrail(
        "triagem_de_injecao",
        aprovado,
        detalhe,
        recusados=[{"url": a.url, "motivo": a.motivo_recusa} for a in dossie.recusados],
    )
    return dossie


def indexar_noticias(
    auditor: Auditor, run_id: str, dossie: Dossie, embeddings: Embeddings | None = None
) -> int:
    with auditor.etapa("noticias", "indexar", artigos=len(dossie.artigos)) as reg:
        total = indexacao.indexar(run_id, dossie.artigos, embeddings=embeddings)
        reg.resultado = {"trechos": total}
    return total


def recuperar_contexto(
    auditor: Auditor,
    run_id: str,
    perguntas: dict[str, str],
    por_pergunta: int = 3,
    embeddings: Embeddings | None = None,
) -> tuple[dict[str, list[Trecho]], list[Fonte]]:
    """Recupera trechos por metrica e monta a lista numerada de fontes do relatorio."""
    recuperados: dict[str, list[Trecho]] = {}
    with auditor.etapa("noticias", "recuperar", perguntas=perguntas) as reg:
        for codigo, pergunta in perguntas.items():
            recuperados[codigo] = indexacao.recuperar(
                run_id, pergunta, quantidade=por_pergunta, embeddings=embeddings
            )
        reg.resultado = {
            codigo: [
                {"titulo": t.titulo, "veiculo": t.veiculo, "distancia": round(t.distancia, 4)}
                for t in trechos
            ]
            for codigo, trechos in recuperados.items()
        }

    return recuperados, _numerar_fontes(recuperados)


def _numerar_fontes(recuperados: dict[str, list[Trecho]]) -> list[Fonte]:
    """Cada materia recebe um numero unico, na ordem em que aparece."""
    indices: dict[str, int] = {}
    fontes: list[Fonte] = []
    for trechos in recuperados.values():
        for trecho in trechos:
            if trecho.url in indices:
                continue
            indices[trecho.url] = len(fontes) + 1
            fontes.append(
                Fonte(
                    indice=indices[trecho.url],
                    titulo=trecho.titulo,
                    url=trecho.url,
                    veiculo=trecho.veiculo,
                    publicado_em=trecho.publicado_em,
                )
            )
    return fontes
