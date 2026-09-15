"""Localizacao e download dos arquivos de SRAG publicados no Open DATASUS."""

import hashlib
import logging
import re
from pathlib import Path

import httpx

from srag.config import get_config

logger = logging.getLogger(__name__)

PAGINA_DATASET = "https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026"

# O nome do arquivo carrega a data da ultima atualizacao do "banco vivo", entao muda
# sem aviso. Estes valores servem so como rede de seguranca se a pagina sair do ar.
URLS_CONHECIDAS = {
    2021: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2021/INFLUD21-23-03-2026.csv",
    2022: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2022/INFLUD22-23-03-2026.csv",
    2023: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2023/INFLUD23-23-03-2026.csv",
    2024: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2024/INFLUD24-23-03-2026.csv",
    2025: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2025/INFLUD25-14-09-2026.csv",
    2026: "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2026/INFLUD26-14-09-2026.csv",
}


class ArquivoNaoEncontrado(RuntimeError):
    pass


def resolver_url(ano: int) -> str:
    """Descobre a URL vigente do CSV do ano na pagina do dataset.

    Prefiro raspar a pagina a fixar a URL no codigo porque o Ministerio republica o
    arquivo com um novo carimbo de data a cada atualizacao do banco vivo.
    """
    padrao = re.compile(
        rf"https://s3[^\"'\s<>]*?/SRAG/{ano}/INFLUD\d{{2}}-[\d-]+\.csv", re.IGNORECASE
    )
    try:
        resposta = httpx.get(PAGINA_DATASET, timeout=60, follow_redirects=True)
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        logger.warning("nao consegui ler a pagina do dataset (%s), usando a URL fixa", erro)
    else:
        encontradas = padrao.findall(resposta.text)
        if encontradas:
            return sorted(set(encontradas))[-1]
        logger.warning("a pagina do dataset nao lista um arquivo para %s", ano)

    if ano in URLS_CONHECIDAS:
        return URLS_CONHECIDAS[ano]
    raise ArquivoNaoEncontrado(f"nenhum arquivo de SRAG disponivel para {ano}")


def baixar(url: str, destino: Path | None = None) -> Path:
    """Baixa o CSV em streaming, reaproveitando o arquivo se ja estiver completo."""
    cfg = get_config()
    pasta = cfg.dir_dados / "bruto"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = destino or pasta / url.rsplit("/", 1)[-1]

    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resposta:
        resposta.raise_for_status()
        tamanho = int(resposta.headers.get("content-length", 0))
        if caminho.exists() and tamanho and caminho.stat().st_size == tamanho:
            logger.info("%s ja esta baixado (%.1f MB)", caminho.name, tamanho / 1e6)
            return caminho

        logger.info("baixando %s (%.1f MB)", caminho.name, tamanho / 1e6)
        baixados = 0
        proximo_aviso = 100_000_000
        with caminho.open("wb") as arquivo:
            for bloco in resposta.iter_bytes(chunk_size=1 << 20):
                arquivo.write(bloco)
                baixados += len(bloco)
                if baixados >= proximo_aviso:
                    logger.info("  %.0f MB", baixados / 1e6)
                    proximo_aviso += 100_000_000
    return caminho


def hash_do_arquivo(caminho: Path) -> str:
    """Identifica a versao exata do arquivo que gerou os numeros do relatorio."""
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()
