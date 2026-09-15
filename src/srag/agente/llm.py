"""Acesso ao modelo de linguagem.

Tudo que fala com o Gemini passa por aqui, por dois motivos: para que o teto de chamadas e de
tokens seja aplicado num lugar so, e para que nenhuma chamada escape da auditoria.
"""

import logging
from typing import TypeVar

from pydantic import BaseModel

from srag.auditoria import Auditor
from srag.config import get_config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OrcamentoEstourado(RuntimeError):
    """Teto de chamadas ou de tokens da execucao foi atingido."""


class ChaveAusente(RuntimeError):
    pass


class ClienteLLM:
    def __init__(self, auditor: Auditor, modelo: str | None = None) -> None:
        cfg = get_config()
        if not cfg.google_api_key:
            raise ChaveAusente(
                "defina GOOGLE_API_KEY no .env para gerar a parte textual do relatorio"
            )

        from langchain_google_genai import ChatGoogleGenerativeAI

        self.modelo = modelo or cfg.modelo_llm
        self.auditor = auditor
        self.chamadas = 0
        self.tokens = 0
        self._max_chamadas = cfg.max_chamadas_llm
        self._max_tokens = cfg.max_tokens_execucao
        self._cliente = ChatGoogleGenerativeAI(
            model=self.modelo,
            google_api_key=cfg.google_api_key,
            temperature=cfg.temperatura_llm,
        )

    def responder(self, sistema: str, usuario: str, formato: type[T], acao: str) -> T:
        """Faz uma chamada com saida estruturada e registra o custo na trilha."""
        self._conferir_orcamento()

        with self.auditor.etapa("llm", acao, modelo=self.modelo) as registro:
            registro.modelo = self.modelo
            resposta = self._cliente.with_structured_output(formato, include_raw=True).invoke(
                [("system", sistema), ("human", usuario)]
            )
            estruturada = resposta["parsed"]
            entrada, saida = _uso(resposta.get("raw"))

            self.chamadas += 1
            self.tokens += entrada + saida
            registro.tokens_entrada = entrada
            registro.tokens_saida = saida
            registro.resultado = {
                "chamadas_acumuladas": self.chamadas,
                "tokens_acumulados": self.tokens,
            }

        if estruturada is None:
            raise ValueError("o modelo nao devolveu uma resposta no formato esperado")
        return estruturada

    def _conferir_orcamento(self) -> None:
        if self.chamadas >= self._max_chamadas:
            self.auditor.guardrail(
                "orcamento_llm", False, f"teto de {self._max_chamadas} chamadas atingido"
            )
            raise OrcamentoEstourado(f"limite de {self._max_chamadas} chamadas por execucao")
        if self.tokens >= self._max_tokens:
            self.auditor.guardrail(
                "orcamento_llm", False, f"teto de {self._max_tokens} tokens atingido"
            )
            raise OrcamentoEstourado(f"limite de {self._max_tokens} tokens por execucao")


def _uso(bruta) -> tuple[int, int]:
    uso = getattr(bruta, "usage_metadata", None) or {}
    return int(uso.get("input_tokens", 0)), int(uso.get("output_tokens", 0))
