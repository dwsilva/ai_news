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
    ano: list[int] = typer.Option(
        ..., "--ano", help="Ano-base do arquivo do SIVEP. Repita a opcao para carregar varios."
    ),
    url: str | None = typer.Option(None, "--url", help="Sobrescreve a URL do CSV."),
    limite: int | None = typer.Option(None, "--limite", help="Le apenas as N primeiras linhas."),
) -> None:
    """Baixa os CSV do Open DATASUS e carrega no banco.

    Os anos sao carregados em sequencia, um de cada vez, porque cada arquivo tem centenas de
    megabytes e nao faz sentido segurar mais de um na memoria.
    """
    from srag.ingestao.carga import carregar_ano

    anos = sorted(set(ano))
    if url and len(anos) > 1:
        raise typer.BadParameter("--url so faz sentido com um unico --ano")

    total = 0
    for indice, ano_base in enumerate(anos, start=1):
        typer.echo(f"[{indice}/{len(anos)}] {ano_base}")
        resumo = carregar_ano(ano_base, url=url, limite=limite)
        total += resumo.linhas_gravadas
        typer.echo(
            f"  {resumo.linhas_gravadas} linhas gravadas "
            f"({resumo.linhas_descartadas} descartadas por falta de data de sintomas)"
        )

    if len(anos) > 1:
        typer.echo(f"total: {total} linhas gravadas em {len(anos)} anos")


@app.command()
def relatorio(
    uf: str | None = typer.Option(None, "--uf", help="Sigla da UF; sem isso o recorte e o Brasil."),
    janela: int = typer.Option(30, "--janela", help="Tamanho da janela de analise, em dias."),
    observacao: str | None = typer.Option(None, "--observacao", help="Foco adicional da analise."),
) -> None:
    """Gera o relatorio completo e grava em reports/<run_id>/."""
    from srag.servico import gerar

    resultado = gerar(uf=uf, janela_dias=janela, observacao=observacao)
    typer.echo(f"execucao {resultado.run_id}")
    for metrica in resultado.painel.metricas:
        typer.echo(f"  {metrica.nome}: {metrica.formatado()}")
    typer.echo(f"arquivos em {resultado.pasta}")


@app.command()
def metricas(
    uf: str | None = typer.Option(None, "--uf"),
    janela: int = typer.Option(30, "--janela"),
) -> None:
    """Mostra so os indicadores, sem acionar o modelo de linguagem."""
    from srag.metricas.calculos import montar_painel
    from srag.metricas.modelos import Filtro

    painel = montar_painel(Filtro(uf=uf, janela_dias=janela))
    typer.echo(f"data de referencia: {painel.data_referencia:%d/%m/%Y}")
    for metrica in painel.metricas:
        typer.echo(
            f"  {metrica.nome}: {metrica.formatado()} "
            f"({metrica.numerador}/{metrica.denominador})"
        )


@app.command()
def diagrama(
    origem: str = typer.Option("docs/arquitetura.dot", "--origem"),
    destino: str = typer.Option("docs/arquitetura.pdf", "--destino"),
) -> None:
    """Renderiza o diagrama de arquitetura em PDF (precisa do graphviz instalado)."""
    import shutil
    import subprocess

    if not shutil.which("dot"):
        raise typer.BadParameter("graphviz nao encontrado; rode este comando dentro do container")

    subprocess.run(["dot", "-Tpdf", origem, "-o", destino], check=True)
    subprocess.run(["dot", "-Tpng", "-Gdpi=140", origem, "-o", destino.replace(".pdf", ".png")],
                   check=True)
    typer.echo(f"diagrama gerado em {destino}")


if __name__ == "__main__":
    app()
