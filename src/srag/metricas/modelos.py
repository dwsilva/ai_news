"""Modelos das metricas.

Todo numero que aparece no relatorio sai de um MetricaCalculada. O objeto carrega junto o
numerador, o denominador e a consulta que o produziu, porque o guardrail de saida compara o
texto do modelo contra esses valores e a trilha de auditoria grava a consulta exata.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Janela(BaseModel):
    inicio: date
    fim: date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    def descricao(self) -> str:
        return f"{self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y}"


class Filtro(BaseModel):
    """Recorte da analise. E o unico ponto em que a solicitacao do usuario vira consulta."""

    uf: str | None = None
    janela_dias: int = 30
    data_referencia: date | None = None
    classificacao_final: str | None = None

    def descricao(self) -> str:
        return f"UF: {self.uf or 'Brasil'} | janela: {self.janela_dias} dias"


class Quebra(BaseModel):
    """Recorte de uma metrica (por faixa etaria, por UF).

    A unidade vem junto porque nem todo recorte e percentual: a permanencia em UTI e em dias,
    e um numero solto numa coluna chamada "Valor" nao diz qual dos dois e.
    """

    rotulo: str
    numerador: int
    denominador: int
    valor: float | None
    unidade: Literal["%", "dias"] = "%"

    def formatado(self) -> str:
        if self.valor is None:
            return "indisponível"
        numero = f"{self.valor:.1f}".replace(".", ",")
        return f"{numero}%" if self.unidade == "%" else f"{numero} {self.unidade}"


class MetricaCalculada(BaseModel):
    codigo: str
    nome: str
    valor: float | None
    unidade: Literal["%", "casos", "dias"]
    numerador: int
    denominador: int
    ignorados: int = 0
    janela: Janela
    limitacao: str = ""
    quebras: list[Quebra] = Field(default_factory=list)
    consulta: str = ""
    parametros: dict = Field(default_factory=dict)
    calculada_em: datetime = Field(default_factory=datetime.now)

    def formatado(self) -> str:
        if self.valor is None:
            return "indisponível"
        if self.unidade == "%":
            return f"{self.valor:.1f}%".replace(".", ",")
        return f"{self.valor:,.1f}".replace(",", ".")


class PontoSerie(BaseModel):
    rotulo: str
    data: date
    casos: int
    # O ultimo mes da serie quase sempre esta pela metade: o grafico precisa avisar isso.
    parcial: bool = False


class SerieTemporal(BaseModel):
    codigo: str
    titulo: str
    pontos: list[PontoSerie]

    @property
    def total(self) -> int:
        return sum(ponto.casos for ponto in self.pontos)


class Painel(BaseModel):
    """Tudo que foi calculado em uma execucao, antes de qualquer texto ser gerado."""

    filtro: Filtro
    data_referencia: date
    metricas: list[MetricaCalculada]
    series: list[SerieTemporal]
    total_registros: int

    def por_codigo(self, codigo: str) -> MetricaCalculada | None:
        return next((m for m in self.metricas if m.codigo == codigo), None)

    def serie(self, codigo: str) -> SerieTemporal | None:
        return next((s for s in self.series if s.codigo == codigo), None)
