"""Verificacao do texto produzido pelo modelo, antes de virar relatorio.

Sao quatro checagens, nesta ordem de importancia:

1. numero inventado - todo percentual e toda contagem grande citada no texto precisa existir
   entre os valores que as consultas devolveram;
2. citacao orfa - toda marcacao [n] precisa apontar para uma materia que foi mesmo recuperada;
3. dado pessoal - o texto nao pode conter CPF, CNS, telefone ou e-mail;
4. recomendacao clinica - o relatorio descreve cenario epidemiologico, nao conduz tratamento.

Se alguma falhar, o agente reescreve com o motivo na mao. Depois de duas tentativas a secao
sai marcada como indisponivel: e melhor entregar um relatorio com um buraco declarado do que
um numero que ninguem consegue rastrear.
"""

import re
from dataclasses import dataclass, field

from srag.metricas.modelos import Painel
from srag.noticias.modelos import Fonte

# Tolerancia na comparacao dos percentuais, em pontos percentuais. Cobre arredondamento de
# uma casa decimal sem deixar passar um numero diferente.
TOLERANCIA = 0.1

# Contagens abaixo disso quase sempre sao numeros da propria prosa ("as quatro metricas",
# "os ultimos 30 dias"), entao conferir todas geraria falso positivo sem ganho real.
MENOR_CONTAGEM_VERIFICADA = 1_000

PADRAO_PERCENTUAL = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:%|p\.p\.|pontos percentuais)")
PADRAO_CONTAGEM = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d{4,}\b")
# O modelo agrupa citacoes ("[1, 2]"), entao o padrao aceita a lista inteira e depois
# separa os indices. Sem isso, citacao agrupada passaria sem conferencia nenhuma.
PADRAO_CITACAO = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
PADRAO_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")

PADROES_DE_DADO_PESSOAL = [
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "CPF"),
    (re.compile(r"\b\d{11}\b(?!\d)"), "sequencia de 11 digitos compativel com CPF"),
    (re.compile(r"\b\d{15}\b"), "numero de cartao do SUS"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "endereco de e-mail"),
    (re.compile(r"\(\d{2}\)\s?9?\d{4}-\d{4}"), "telefone"),
]

PADROES_DE_CONDUTA_CLINICA = [
    re.compile(r"\b(prescrev|receit)\w*", re.IGNORECASE),
    re.compile(r"\bdeve(m)? (tomar|usar|administrar|ingerir)\b", re.IGNORECASE),
    re.compile(r"\b(dose|dosagem) de \d", re.IGNORECASE),
    re.compile(r"\b(mg|ml)\b\s*(de|por)\b", re.IGNORECASE),
    re.compile(r"\brecomend\w+ (o|a|que o|que a) (uso|paciente|tratamento)\b", re.IGNORECASE),
]


@dataclass
class Veredito:
    aprovado: bool
    problemas: list[str] = field(default_factory=list)
    numeros_verificados: int = 0

    def resumo(self) -> str:
        if self.aprovado:
            return f"{self.numeros_verificados} numeros conferidos, nenhum problema"
        return "; ".join(self.problemas)


def verificar(texto: str, painel: Painel, fontes: list[Fonte]) -> Veredito:
    problemas: list[str] = []
    sem_datas = PADRAO_DATA.sub(" ", texto)

    permitidos = _valores_permitidos(painel)
    percentuais = [_como_numero(bruto) for bruto in PADRAO_PERCENTUAL.findall(sem_datas)]
    contagens = [_como_numero(bruto) for bruto in PADRAO_CONTAGEM.findall(sem_datas)]

    for percentual in percentuais:
        if not _confere(percentual, permitidos["percentuais"], TOLERANCIA):
            problemas.append(
                f"o percentual {percentual:.1f}% nao corresponde a nenhuma metrica calculada"
            )

    for contagem in contagens:
        if contagem < MENOR_CONTAGEM_VERIFICADA:
            continue
        if not _confere(contagem, permitidos["contagens"], 0):
            problemas.append(f"a contagem {contagem:.0f} nao aparece nos dados consultados")

    indices_validos = {fonte.indice for fonte in fontes}
    for citacao in sorted(_indices_citados(texto)):
        if citacao not in indices_validos:
            problemas.append(f"a citacao [{citacao}] nao corresponde a nenhuma fonte recuperada")

    for padrao, descricao in PADROES_DE_DADO_PESSOAL:
        if padrao.search(texto):
            problemas.append(f"o texto contem o que parece ser {descricao}")

    for padrao in PADROES_DE_CONDUTA_CLINICA:
        achado = padrao.search(texto)
        if achado:
            problemas.append(
                f"trecho com cara de conduta clinica individual: '{achado.group(0)}'"
            )

    return Veredito(
        aprovado=not problemas,
        problemas=problemas,
        numeros_verificados=len(percentuais) + len(contagens),
    )


def _valores_permitidos(painel: Painel) -> dict[str, set[float]]:
    percentuais: set[float] = set()
    contagens: set[float] = {float(painel.total_registros)}

    for metrica in painel.metricas:
        if metrica.valor is not None:
            percentuais.add(round(metrica.valor, 1))
            percentuais.add(round(abs(metrica.valor), 1))
        contagens.update({float(metrica.numerador), float(metrica.denominador)})
        if metrica.ignorados:
            contagens.add(float(metrica.ignorados))
        for quebra in metrica.quebras:
            if quebra.valor is not None:
                percentuais.add(round(quebra.valor, 1))
            contagens.update({float(quebra.numerador), float(quebra.denominador)})

    for serie in painel.series:
        contagens.add(float(serie.total))
        contagens.update(float(ponto.casos) for ponto in serie.pontos)

    return {"percentuais": percentuais, "contagens": contagens}


def _indices_citados(texto: str) -> set[int]:
    indices: set[int] = set()
    for grupo in PADRAO_CITACAO.findall(texto):
        indices.update(int(marca) for marca in grupo.split(","))
    return indices


def _confere(valor: float, permitidos: set[float], tolerancia: float) -> bool:
    return any(abs(valor - permitido) <= tolerancia for permitido in permitidos)


def _como_numero(bruto: str) -> float:
    """Le numero escrito em portugues, onde o ponto pode ser milhar e a virgula e decimal."""
    if "," in bruto:
        return float(bruto.replace(".", "").replace(",", "."))
    # Ponto separando grupos de tres digitos e milhar ("16.087"); o resto e decimal ("27.9").
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", bruto):
        return float(bruto.replace(".", ""))
    return float(bruto)
