"""Configuracao da aplicacao. Tudo que muda entre ambientes passa por aqui."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SRAG_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://srag:srag@localhost:55432/srag"
    # Conexao usada pelas ferramentas do agente. Aponta para um papel que so tem SELECT.
    database_url_leitura: str = ""
    statement_timeout_ms: int = 15_000

    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    modelo_llm: str = "gemini-3.8-flash"
    modelo_embedding: str = "models/gemini-embedding-001"
    # O modelo devolve 3072 dimensoes por padrao. Peco 768 porque a familia suporta
    # truncagem (Matryoshka) e o indice cabe melhor; a coluna vector() segue esse numero.
    dimensoes_embedding: int = 768
    temperatura_llm: float = 0.2

    max_chamadas_llm: int = 12
    max_tokens_execucao: int = 120_000

    noticias_max_artigos: int = 15
    noticias_janela_dias: int = 30

    # Agregacoes com menos registros que isso sao suprimidas para nao permitir reidentificacao.
    k_anonimato: int = 5

    # Os ultimos dias da serie sempre estao incompletos por atraso de digitacao da ficha.
    # Ancorar a janela alguns dias atras evita ler esse atraso como queda de casos.
    atraso_notificacao_dias: int = 5

    dir_dados: Path = RAIZ / "data"
    dir_relatorios: Path = RAIZ / "reports"
    dir_logs: Path = RAIZ / "logs"

    @property
    def url_leitura(self) -> str:
        return self.database_url_leitura or self.database_url

    def preparar_diretorios(self) -> None:
        for caminho in (self.dir_dados, self.dir_relatorios, self.dir_logs):
            caminho.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_config() -> Config:
    return Config()
