"""Validacao do pedido antes de qualquer processamento.

A interface pede parametros, nao uma pergunta livre. Isso e uma decisao de guardrail: um
formulario validado nao tem como pedir ao agente algo que ele nao deveria fazer. O unico
campo de texto livre e a observacao, e ela passa pela mesma triagem de injecao das noticias.
"""

from datetime import date

from srag.guardrails import injecao
from srag.ingestao.dominios import CLASSIFICACAO_FINAL, UFS
from srag.metricas.modelos import Filtro

JANELA_MINIMA = 7
JANELA_MAXIMA = 180
TAMANHO_MAXIMO_OBSERVACAO = 300

CLASSIFICACOES_VALIDAS = frozenset(CLASSIFICACAO_FINAL.values())

# A observacao serve para direcionar a analise, nao para mudar o assunto.
TERMOS_DO_ESCOPO = (
    "srag",
    "respirat",
    "influenza",
    "gripe",
    "covid",
    "uti",
    "vacin",
    "obito",
    "óbito",
    "mortalidade",
    "internac",
    "internaç",
    "surto",
    "caso",
)


class PedidoInvalido(ValueError):
    def __init__(self, problemas: list[str]) -> None:
        super().__init__("; ".join(problemas))
        self.problemas = problemas


def validar(
    uf: str | None = None,
    janela_dias: int = 30,
    data_referencia: date | None = None,
    classificacao_final: str | None = None,
    observacao: str | None = None,
) -> tuple[Filtro, str | None]:
    """Devolve o filtro validado e a observacao aprovada (ou None)."""
    problemas: list[str] = []

    if uf:
        uf = uf.strip().upper()
        if uf not in UFS:
            problemas.append(f"UF desconhecida: {uf}")

    if not JANELA_MINIMA <= janela_dias <= JANELA_MAXIMA:
        problemas.append(
            f"janela de {janela_dias} dias fora do intervalo permitido "
            f"({JANELA_MINIMA} a {JANELA_MAXIMA})"
        )

    if data_referencia and data_referencia > date.today():
        problemas.append("data de referencia no futuro")

    if classificacao_final and classificacao_final not in CLASSIFICACOES_VALIDAS:
        problemas.append(f"classificacao final desconhecida: {classificacao_final}")

    observacao_aprovada = None
    if observacao and observacao.strip():
        observacao_aprovada = _validar_observacao(observacao.strip(), problemas)

    if problemas:
        raise PedidoInvalido(problemas)

    filtro = Filtro(
        uf=uf,
        janela_dias=janela_dias,
        data_referencia=data_referencia,
        classificacao_final=classificacao_final,
    )
    return filtro, observacao_aprovada


def _validar_observacao(texto: str, problemas: list[str]) -> str | None:
    if len(texto) > TAMANHO_MAXIMO_OBSERVACAO:
        problemas.append(
            f"observacao com {len(texto)} caracteres; o limite e {TAMANHO_MAXIMO_OBSERVACAO}"
        )
        return None

    motivo = injecao.inspecionar(texto)
    if motivo:
        problemas.append(f"observacao recusada pela triagem de injecao ({motivo})")
        return None

    if not dentro_do_escopo(texto):
        problemas.append(
            "observacao fora do escopo: este relatorio so trata de SRAG e dos indicadores "
            "derivados da base do SIVEP-Gripe"
        )
        return None

    return texto


def dentro_do_escopo(texto: str) -> bool:
    minusculo = texto.lower()
    return any(termo in minusculo for termo in TERMOS_DO_ESCOPO)
