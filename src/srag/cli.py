"""Interface de linha de comando.

E a mesma pilha que a API usa; muda so o ponto de entrada.
"""

import logging

import typer

from srag.log import configurar_logging

app = typer.Typer(add_completion=False, help="Relatórios de SRAG a partir do Open DATASUS.")
logger = logging.getLogger(__name__)


@app.callback()
def principal(verboso: bool = typer.Option(False, "--verboso", "-v")) -> None:
    configurar_logging(verboso)


@app.command()
def schema() -> None:
    """Cria (ou atualiza) o schema do banco."""
    from srag.db import aplicar_schema

    aplicar_schema()
    typer.echo("schema aplicado")


@app.command()
def ingestao(
    ano: int = typer.Option(..., "--ano", help="Ano-base do arquivo do SIVEP."),
    url: str | None = typer.Option(None, "--url", help="Sobrescreve a URL do CSV."),
    limite: int | None = typer.Option(None, "--limite", help="Lê apenas as N primeiras linhas."),
) -> None:
    """Baixa o CSV do Open DATASUS e carrega no banco."""
    from srag.ingestao.carga import carregar_ano

    resumo = carregar_ano(ano, url=url, limite=limite)
    typer.echo(
        f"{resumo.linhas_gravadas} linhas gravadas "
        f"({resumo.linhas_descartadas} descartadas por falta de data de sintomas)"
    )


if __name__ == "__main__":
    app()
