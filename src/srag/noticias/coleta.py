"""Coleta das noticias que vao embasar os comentarios do relatorio."""

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from srag.config import get_config
from srag.guardrails import injecao
from srag.ingestao.dominios import NOMES_DE_UF
from srag.noticias.extracao import extrair
from srag.noticias.fontes import BingNews, FonteDeNoticias, GoogleNews
from srag.noticias.modelos import Artigo, Consulta, Dossie

logger = logging.getLogger(__name__)

TERMOS_BASE = ["SRAG", "sindrome respiratoria aguda grave", "InfoGripe"]


def montar_consulta(uf: str | None = None) -> Consulta:
    local = NOMES_DE_UF.get(uf, uf) if uf else "Brasil"
    return Consulta(termos=TERMOS_BASE, local=local)


def coletar(
    uf: str | None = None,
    janela_dias: int | None = None,
    maximo: int | None = None,
    fontes: list[FonteDeNoticias] | None = None,
) -> Dossie:
    cfg = get_config()
    janela = janela_dias or cfg.noticias_janela_dias
    limite = maximo or cfg.noticias_max_artigos
    fontes = fontes if fontes is not None else [BingNews(), GoogleNews()]

    consulta = montar_consulta(uf)
    brutos: list[Artigo] = []
    for fonte in fontes:
        brutos.extend(fonte.buscar(consulta, janela, limite))

    unicos = _remover_repetidos(brutos)[:limite]
    _completar_textos(unicos)

    aceitos, recusados = [], []
    for artigo in unicos:
        motivo = injecao.inspecionar(artigo.conteudo)
        if motivo:
            logger.warning("artigo recusado (%s): %s", motivo, artigo.url)
            artigo.aceito = False
            artigo.motivo_recusa = motivo
            recusados.append(artigo)
            continue
        aceitos.append(artigo)

    logger.info(
        "coleta concluida: %d artigos aceitos, %d recusados, %d com texto integral",
        len(aceitos),
        len(recusados),
        sum(1 for artigo in aceitos if artigo.texto_completo),
    )
    return Dossie(consulta=consulta.descricao(), artigos=aceitos, recusados=recusados)


def _remover_repetidos(artigos: list[Artigo]) -> list[Artigo]:
    """A mesma materia costuma aparecer nas duas fontes e em varios portais do mesmo grupo."""
    vistos: set[str] = set()
    unicos: list[Artigo] = []
    for artigo in artigos:
        chave = _normalizar(artigo.titulo)
        if not chave or chave in vistos or artigo.url in vistos:
            continue
        vistos.add(chave)
        vistos.add(artigo.url)
        unicos.append(artigo)
    return unicos


def _normalizar(titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", sem_acento.lower()).strip()


def _completar_textos(artigos: list[Artigo]) -> None:
    """Busca o texto integral de cada materia em paralelo.

    Sao dezenas de requisicoes a sites diferentes, quase todo o tempo e espera de rede.
    """
    with ThreadPoolExecutor(max_workers=8) as executor:
        textos = executor.map(lambda artigo: extrair(artigo.url), artigos)

    for artigo, texto in zip(artigos, textos, strict=True):
        if texto:
            artigo.texto = texto
            artigo.texto_completo = True
