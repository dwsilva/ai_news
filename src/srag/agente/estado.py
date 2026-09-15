"""Estado compartilhado entre os nos do grafo e os formatos de saida do modelo."""

from typing import Any, TypedDict

from pydantic import BaseModel, Field

from srag.metricas.modelos import Filtro, Painel
from srag.noticias.modelos import Dossie, Fonte, Trecho


class BuscaPorMetrica(BaseModel):
    codigo: str = Field(description="codigo da metrica, exatamente como informado")
    pergunta: str = Field(
        description="pergunta curta, em portugues, para buscar noticias sobre essa metrica"
    )


class PlanoDeBusca(BaseModel):
    """Saida do no que decide o que procurar nas noticias para cada metrica."""

    buscas: list[BuscaPorMetrica]


class AnaliseDaMetrica(BaseModel):
    codigo: str
    comentario: str


class Redacao(BaseModel):
    """Saida do no de redacao. E o unico texto que o modelo produz."""

    panorama: str
    analises: list[AnaliseDaMetrica]
    sinais_de_alerta: list[str]

    def comentario(self, codigo: str) -> str:
        analise = next((item for item in self.analises if item.codigo == codigo), None)
        return analise.comentario if analise else ""


class Estado(TypedDict, total=False):
    run_id: str
    filtro: Filtro
    observacao: str | None

    painel: Painel
    graficos: dict[str, str]
    dossie: Dossie
    perguntas: dict[str, str]
    trechos: dict[str, list[Trecho]]
    fontes: list[Fonte]

    redacao: Redacao
    problemas: list[str]
    tentativas: int
    ressalva: str

    relatorio_md: str
    guardrails: list[dict[str, Any]]
