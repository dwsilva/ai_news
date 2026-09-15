"""Extracao do texto das materias."""

import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)

TEMPO_LIMITE = 25
MINIMO_DE_CARACTERES = 400
MAXIMO_DE_CARACTERES = 20_000
CABECALHOS = {"User-Agent": "srag-report/0.1 (PoC academica; contato via repositorio)"}

# Agregadores nao entregam a materia, so uma pagina de redirecionamento.
DOMINIOS_SEM_TEXTO = ("news.google.com", "bing.com")


def extrair(url: str) -> str | None:
    if not url or any(dominio in url for dominio in DOMINIOS_SEM_TEXTO):
        return None
    try:
        resposta = httpx.get(
            url, timeout=TEMPO_LIMITE, follow_redirects=True, headers=CABECALHOS
        )
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        logger.info("nao consegui abrir %s: %s", url, erro)
        return None

    texto = trafilatura.extract(
        resposta.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not texto or len(texto) < MINIMO_DE_CARACTERES:
        # Abaixo disso normalmente e chamada de home ou pagina de assinatura.
        logger.info("texto curto demais em %s", url)
        return None
    return texto[:MAXIMO_DE_CARACTERES]
