"""Conversao do relatorio de Markdown para HTML e PDF.

O HTML embute os graficos em base64. Fica um arquivo unico, que abre direto no navegador,
pode ser devolvido inteiro pela API e serve de entrada para o gerador de PDF sem depender de
caminho relativo funcionar dentro do WeasyPrint.
"""

import base64
import logging
import re
from pathlib import Path

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)

PADRAO_IMAGEM = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

ESTILO = """
:root { color-scheme: light; }
body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #1f2933;
    line-height: 1.55;
    max-width: 880px;
    margin: 0 auto;
    padding: 32px 24px 64px;
    background: #fff;
}
h1 { font-size: 1.75rem; color: #1f4e79; border-bottom: 2px solid #1f4e79; padding-bottom: 8px; }
h2 { font-size: 1.25rem; color: #1f4e79; margin-top: 2.2rem; }
h3 { font-size: 1.05rem; margin-top: 1.6rem; }
blockquote {
    border-left: 4px solid #c2540a;
    background: #fdf5ef;
    margin: 1.4rem 0;
    padding: 12px 16px;
    font-size: 0.92rem;
}
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.9rem; }
th, td { border: 1px solid #d8dee4; padding: 6px 10px; text-align: left; }
th { background: #eef3f8; }
img { max-width: 100%; margin: 12px 0; }
code { background: #f1f3f5; padding: 1px 4px; border-radius: 3px; font-size: 0.86em; }
pre { background: #f6f8fa; padding: 12px; overflow-x: auto; font-size: 0.8rem; border-radius: 4px; }
pre code { background: none; padding: 0; }
em { color: #52606d; }
@page { size: A4; margin: 18mm 15mm; }
"""

_markdown = MarkdownIt("commonmark").enable(["table"])


def para_html(markdown: str, base: Path, titulo: str = "Relatório de SRAG") -> str:
    corpo = _markdown.render(_embutir_imagens(markdown, base))
    return (
        "<!doctype html>\n"
        '<html lang="pt-br">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{titulo}</title>\n<style>{ESTILO}</style>\n</head>\n"
        f"<body>\n{corpo}\n</body>\n</html>\n"
    )


def para_pdf(html: str, destino: Path) -> Path | None:
    """Gera o PDF. Devolve None se o WeasyPrint nao estiver disponivel no ambiente."""
    try:
        from weasyprint import HTML
    except OSError as erro:
        # No Windows o WeasyPrint depende de bibliotecas do GTK que normalmente nao estao
        # instaladas. Dentro do container isso nunca acontece.
        logger.warning("PDF nao gerado: %s", erro)
        return None

    destino.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(destino)
    return destino


def _embutir_imagens(markdown: str, base: Path) -> str:
    def trocar(achado: re.Match) -> str:
        alt, caminho = achado.group(1), achado.group(2)
        if caminho.startswith(("http://", "https://", "data:")):
            return achado.group(0)
        arquivo = base / caminho
        if not arquivo.exists():
            logger.warning("imagem nao encontrada: %s", arquivo)
            return achado.group(0)
        dados = base64.b64encode(arquivo.read_bytes()).decode()
        return f"![{alt}](data:image/png;base64,{dados})"

    return PADRAO_IMAGEM.sub(trocar, markdown)
