from datetime import datetime

from pydantic import BaseModel, Field


class Consulta(BaseModel):
    """Termos da busca de noticias.

    Fica estruturado porque cada buscador quer uma sintaxe diferente: o Google News aceita
    operadores booleanos e aspas, o Bing devolve zero resultado para a mesma expressao.
    """

    termos: list[str]
    local: str = "Brasil"

    def descricao(self) -> str:
        return f"{' / '.join(self.termos)} ({self.local})"


class Artigo(BaseModel):
    titulo: str
    url: str
    veiculo: str = ""
    publicado_em: datetime | None = None
    resumo: str = ""
    texto: str = ""
    # Falso quando so consegui o titulo e o resumo do feed, sem abrir a materia.
    texto_completo: bool = False
    aceito: bool = True
    motivo_recusa: str = ""

    @property
    def conteudo(self) -> str:
        return self.texto if self.texto_completo else f"{self.titulo}. {self.resumo}".strip()

    def referencia(self) -> str:
        data = f"{self.publicado_em:%d/%m/%Y}" if self.publicado_em else "sem data"
        return f"{self.veiculo or 'fonte nao identificada'}, {data}"


class Trecho(BaseModel):
    """Pedaco de materia recuperado do indice vetorial, com a fonte junto."""

    noticia_id: int
    titulo: str
    url: str
    veiculo: str
    publicado_em: datetime | None
    texto: str
    distancia: float


class Fonte(BaseModel):
    """Entrada da lista de referencias do relatorio."""

    indice: int
    titulo: str
    url: str
    veiculo: str
    publicado_em: datetime | None = None

    def citacao(self) -> str:
        data = f"{self.publicado_em:%d/%m/%Y}" if self.publicado_em else "sem data"
        return f"[{self.indice}] {self.titulo} - {self.veiculo}, {data}. {self.url}"


class Dossie(BaseModel):
    """Resultado da coleta: o que entrou, o que foi recusado e por que."""

    consulta: str
    artigos: list[Artigo] = Field(default_factory=list)
    recusados: list[Artigo] = Field(default_factory=list)

    @property
    def total_coletado(self) -> int:
        return len(self.artigos) + len(self.recusados)
