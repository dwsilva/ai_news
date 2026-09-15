"""Fontes de noticias.

As duas sao feeds RSS publicos, sem chave de API: quem for avaliar o projeto consegue rodar
sem pedir credencial para ninguem. Elas se complementam - o Bing entrega o endereco real da
materia (da para extrair o texto inteiro), e o Google News tem uma cobertura de imprensa
regional brasileira bem melhor, so que atras de um link de redirecionamento.
"""

import logging
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import parse_qs, quote, urlparse

import feedparser
import httpx

from srag.noticias.modelos import Artigo, Consulta

logger = logging.getLogger(__name__)

TEMPO_LIMITE = 30
CABECALHOS = {"User-Agent": "srag-report/0.1 (PoC academica; contato via repositorio)"}


class FonteDeNoticias(Protocol):
    nome: str

    def buscar(self, consulta: Consulta, janela_dias: int, maximo: int) -> list[Artigo]: ...


class BingNews:
    """Busca de noticias do Bing em RSS.

    O link do feed passa por um redirecionador, mas o endereco original vem no parametro
    `url` da propria URL - nao ha nada para driblar, e so ler o parametro.
    """

    nome = "bing"

    def buscar(self, consulta: Consulta, janela_dias: int, maximo: int) -> list[Artigo]:
        # Sem operadores: com aspas e OR o feed do Bing volta vazio.
        termo = " ".join([*consulta.termos, consulta.local])
        endereco = (
            f"https://www.bing.com/news/search?q={quote(termo)}"
            "&format=RSS&setmkt=pt-BR&cc=BR"
        )
        entradas = _ler_feed(endereco, self.nome)

        artigos = []
        for entrada in entradas[:maximo]:
            url = _endereco_original(entrada.get("link", ""))
            if not url:
                continue
            artigos.append(
                Artigo(
                    titulo=_texto(entrada.get("title")),
                    url=url,
                    veiculo=urlparse(url).netloc.replace("www.", ""),
                    publicado_em=_data(entrada),
                    resumo=_texto(entrada.get("summary")),
                )
            )
        return _dentro_da_janela(artigos, janela_dias)


class GoogleNews:
    """Busca do Google News em RSS.

    O link aponta para o agregador e a materia original so e alcancavel por um endpoint
    interno nao documentado do Google. Nao vou usar esse endpoint: aqui o artigo entra com
    titulo, veiculo e data, e o relatorio cita exatamente isso.
    """

    nome = "google"

    def buscar(self, consulta: Consulta, janela_dias: int, maximo: int) -> list[Artigo]:
        alternativas = " OR ".join(f'"{termo}"' for termo in consulta.termos)
        termo = f"({alternativas}) {consulta.local} when:{janela_dias}d"
        endereco = (
            f"https://news.google.com/rss/search?q={quote(termo)}"
            "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )
        entradas = _ler_feed(endereco, self.nome)

        artigos = []
        for entrada in entradas[:maximo]:
            titulo = _texto(entrada.get("title"))
            veiculo = ""
            if isinstance(entrada.get("source"), dict):
                veiculo = entrada["source"].get("title", "")
            # O titulo do Google News termina com " - Veiculo"; sem isso a citacao fica feia.
            if not veiculo and " - " in titulo:
                titulo, _, veiculo = titulo.rpartition(" - ")

            artigos.append(
                Artigo(
                    titulo=titulo,
                    url=entrada.get("link", ""),
                    veiculo=veiculo,
                    publicado_em=_data(entrada),
                    resumo=_texto(entrada.get("summary")),
                )
            )
        return _dentro_da_janela(artigos, janela_dias)


def _ler_feed(endereco: str, fonte: str) -> list[dict]:
    try:
        resposta = httpx.get(
            endereco, timeout=TEMPO_LIMITE, follow_redirects=True, headers=CABECALHOS
        )
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        # Uma fonte fora do ar nao pode derrubar o relatorio inteiro.
        logger.warning("fonte %s indisponivel: %s", fonte, erro)
        return []

    feed = feedparser.parse(resposta.text)
    logger.info("fonte %s devolveu %d entradas", fonte, len(feed.entries))
    return list(feed.entries)


def _endereco_original(link: str) -> str:
    if "bing.com/news/apiclick" not in link:
        return link
    return parse_qs(urlparse(link).query).get("url", [""])[0]


def _texto(valor: object) -> str:
    return str(valor).strip() if valor else ""


def _data(entrada: dict) -> datetime | None:
    estrutura = entrada.get("published_parsed") or entrada.get("updated_parsed")
    if not estrutura:
        return None
    return datetime(*estrutura[:6], tzinfo=UTC)


def _dentro_da_janela(artigos: list[Artigo], janela_dias: int) -> list[Artigo]:
    """Descarta materia velha.

    O Bing ignora filtro de data no RSS e mistura materia de anos atras com a da semana;
    para um relatorio de situacao atual isso e ruido.
    """
    limite = datetime.now(UTC).timestamp() - janela_dias * 86_400
    recentes = []
    for artigo in artigos:
        if artigo.publicado_em and artigo.publicado_em.timestamp() < limite:
            continue
        recentes.append(artigo)
    return recentes
