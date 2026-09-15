"""Geracao dos dois graficos exigidos no relatorio.

Ficam em PNG porque precisam ser embutidos tanto no HTML quanto no PDF, e o PDF e gerado
por um motor que nao executa javascript.
"""

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (tem que vir depois do backend)
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from srag.metricas.modelos import SerieTemporal  # noqa: E402

logger = logging.getLogger(__name__)

AZUL = "#1f4e79"
AZUL_CLARO = "#8fb8de"
LARANJA = "#c2540a"
CINZA = "#6b7280"
JANELA_MEDIA_MOVEL = 7


def gerar(series: list[SerieTemporal], destino: Path) -> dict[str, Path]:
    """Desenha todas as series e devolve o caminho de cada arquivo por codigo."""
    destino.mkdir(parents=True, exist_ok=True)
    desenhos = {"casos_diarios": _casos_diarios, "casos_mensais": _casos_mensais}

    caminhos: dict[str, Path] = {}
    for serie in series:
        desenhar = desenhos.get(serie.codigo)
        if desenhar is None:
            logger.warning("serie '%s' sem grafico correspondente", serie.codigo)
            continue
        arquivo = destino / f"{serie.codigo}.png"
        desenhar(serie, arquivo)
        caminhos[serie.codigo] = arquivo
    return caminhos


def _casos_diarios(serie: SerieTemporal, arquivo: Path) -> None:
    rotulos = [ponto.rotulo for ponto in serie.pontos]
    casos = [ponto.casos for ponto in serie.pontos]
    media = _media_movel(casos, JANELA_MEDIA_MOVEL)

    figura, eixo = plt.subplots(figsize=(10, 4.2))
    eixo.fill_between(rotulos, casos, color=AZUL_CLARO, alpha=0.45)
    eixo.plot(rotulos, casos, color=AZUL, linewidth=1.4, marker="o", markersize=3,
              label="Casos por dia")
    eixo.plot(rotulos, media, color=LARANJA, linewidth=2.2,
              label=f"Média móvel de {JANELA_MEDIA_MOVEL} dias")

    eixo.set_title(serie.titulo, fontsize=13, color=AZUL, pad=12)
    eixo.set_ylabel("Casos notificados")
    eixo.legend(frameon=False, fontsize=9)
    # Com 30 rotulos de data o eixo fica ilegivel; mostrar de tres em tres resolve.
    eixo.set_xticks(range(0, len(rotulos), 3))
    eixo.set_xticklabels(rotulos[::3], rotation=45, ha="right", fontsize=8)
    _acabamento(eixo)

    figura.tight_layout()
    figura.savefig(arquivo, dpi=160)
    plt.close(figura)


def _casos_mensais(serie: SerieTemporal, arquivo: Path) -> None:
    rotulos = [ponto.rotulo for ponto in serie.pontos]
    casos = [ponto.casos for ponto in serie.pontos]

    figura, eixo = plt.subplots(figsize=(10, 4.2))
    cores = [AZUL_CLARO if ponto.parcial else AZUL for ponto in serie.pontos]
    barras = eixo.bar(rotulos, casos, color=cores, width=0.62)

    if any(ponto.parcial for ponto in serie.pontos):
        legenda = Patch(facecolor=AZUL_CLARO, label="Mês ainda incompleto na base")
        eixo.legend(handles=[legenda], frameon=False, fontsize=9, loc="upper left")

    maximo = max(casos) if casos else 0
    for barra, valor in zip(barras, casos, strict=True):
        if valor == 0:
            continue
        eixo.annotate(
            f"{valor:,}".replace(",", "."),
            (barra.get_x() + barra.get_width() / 2, valor),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=CINZA,
        )

    eixo.set_title(serie.titulo, fontsize=13, color=AZUL, pad=12)
    eixo.set_ylabel("Casos notificados")
    eixo.set_ylim(0, maximo * 1.15 if maximo else 1)
    eixo.tick_params(axis="x", labelsize=9)
    _acabamento(eixo)

    figura.tight_layout()
    figura.savefig(arquivo, dpi=160)
    plt.close(figura)


def _acabamento(eixo) -> None:
    eixo.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
    eixo.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    eixo.set_axisbelow(True)
    for lado in ("top", "right"):
        eixo.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        eixo.spines[lado].set_color("#d1d5db")


def _media_movel(valores: list[int], janela: int) -> list[float | None]:
    media: list[float | None] = []
    for posicao in range(len(valores)):
        if posicao + 1 < janela:
            media.append(None)
            continue
        recorte = valores[posicao + 1 - janela : posicao + 1]
        media.append(sum(recorte) / janela)
    return media
