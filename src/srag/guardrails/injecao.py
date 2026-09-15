"""Triagem de injecao de prompt no conteudo das noticias.

As materias sao conteudo de terceiros que vai parar dentro do contexto do modelo. Trato o
risco em duas camadas: aqui, descartando o artigo que traz texto com cara de instrucao; e no
prompt, delimitando o conteudo e dizendo explicitamente que aquilo e dado, nao ordem.

Nenhuma das duas e infalivel. A defesa que de fato segura o estrago e arquitetural: o agente
nao tem ferramenta de escrita, o banco so aceita SELECT e os numeros do relatorio sao
conferidos contra as metricas calculadas.
"""

import re

PADROES = [
    (r"ignore (as )?(todas as )?instru[cç][oõ]es", "pedido para ignorar instrucoes"),
    (r"ignore (all |any )?(previous|prior|above) instructions", "pedido para ignorar instrucoes"),
    (r"disregard (the |all )?(previous|above|prior)", "pedido para desconsiderar contexto"),
    (r"esque[cç]a (tudo|as instru[cç][oõ]es|o que)", "pedido para esquecer o contexto"),
    (
        r"\b(voc[eê]|you) (agora )?(e|é|are now|is now)\s+(um|uma|a|an)\b"
        r".{0,40}\b(assistente|agente|assistant|model)\b",
        "tentativa de redefinir o papel do agente",
    ),
    (r"</?(system|assistant|user)>", "marcacao de papel de conversa"),
    (r"\[/?(INST|SYSTEM)\]", "marcacao de instrucao de modelo"),
    (r"(responda|reply|answer) (apenas|somente|only) (com|with)", "tentativa de forcar a saida"),
    (r"(revele|mostre|print|reveal|repeat) (o |your |the )?(system ?prompt|prompt do sistema)",
     "tentativa de extrair o prompt"),
    (r"(execute|rode|run|eval)\s*\(", "tentativa de execucao de codigo"),
    (r"\b(DROP|DELETE|UPDATE|INSERT)\s+(TABLE|FROM|INTO)\b", "comando SQL embutido"),
]

COMPILADOS = [(re.compile(padrao, re.IGNORECASE | re.DOTALL), motivo) for padrao, motivo in PADROES]


def inspecionar(texto: str) -> str | None:
    """Devolve o motivo da recusa, ou None se o texto parecer uma materia comum."""
    if not texto:
        return None
    for padrao, motivo in COMPILADOS:
        if padrao.search(texto):
            return motivo
    return None


def delimitar(rotulo: str, conteudo: str) -> str:
    """Embrulha conteudo externo num bloco identificado.

    Tambem remove as cercas de codigo do proprio texto, para que a materia nao consiga
    fechar o bloco mais cedo e escrever fora dele.
    """
    limpo = conteudo.replace("```", "'''").strip()
    return f"<<<{rotulo}\n{limpo}\n{rotulo}>>>"
