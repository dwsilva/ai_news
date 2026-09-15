"""Trilha de auditoria das execucoes do agente.

A regra que segui: se uma decisao mudou o relatorio, ela tem que estar aqui. Isso inclui as
consultas que alimentaram cada metrica, as materias que entraram e as que foram recusadas, as
chamadas ao modelo com contagem de tokens e todo guardrail que disparou.

Grava em dois lugares de proposito. O Postgres e a fonte consultavel (a API le de la). O JSONL
em disco e a copia que sobrevive se o banco for recriado, e e o formato que qualquer coletor
de log consegue ingerir sem adaptacao.
"""

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from srag.config import get_config
from srag.db import engine_escrita

logger = logging.getLogger(__name__)

ARQUIVO_JSONL = "execucoes.jsonl"


@dataclass
class Registro:
    """Uma linha da trilha. O chamador preenche o que souber durante a etapa."""

    etapa: str
    acao: str
    parametros: dict[str, Any] = field(default_factory=dict)
    resultado: dict[str, Any] = field(default_factory=dict)
    modelo: str | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    mensagem: str | None = None


def novo_run_id() -> str:
    return uuid.uuid4().hex[:16]


class Auditor:
    def __init__(self, run_id: str, parametros: dict[str, Any] | None = None) -> None:
        self.run_id = run_id
        self.parametros = parametros or {}
        self.guardrails: list[dict[str, Any]] = []
        self._sequencia = 0
        cfg = get_config()
        cfg.preparar_diretorios()
        self._arquivo = cfg.dir_logs / ARQUIVO_JSONL

    def abrir(self) -> None:
        with engine_escrita().begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO srag.execucao (run_id, status, parametros) "
                    "VALUES (:run_id, 'em_andamento', CAST(:parametros AS jsonb)) "
                    "ON CONFLICT (run_id) DO NOTHING"
                ),
                {"run_id": self.run_id, "parametros": json.dumps(self.parametros, default=str)},
            )

    @contextmanager
    def etapa(self, etapa: str, acao: str, **parametros: Any) -> Iterator[Registro]:
        registro = Registro(etapa=etapa, acao=acao, parametros=parametros)
        inicio = time.perf_counter()
        try:
            yield registro
        except Exception as erro:
            duracao = int((time.perf_counter() - inicio) * 1000)
            registro.mensagem = f"{type(erro).__name__}: {erro}"
            self._gravar(registro, "erro", duracao)
            raise
        duracao = int((time.perf_counter() - inicio) * 1000)
        self._gravar(registro, "ok", duracao)

    def guardrail(self, nome: str, aprovado: bool, detalhe: str = "", **extras: Any) -> None:
        """Registra o veredito de um guardrail, tenha ele bloqueado alguma coisa ou nao.

        Anotar tambem o que passou e o que permite dizer depois que a verificacao rodou,
        e nao que ninguem olhou.
        """
        evento = {"guardrail": nome, "aprovado": aprovado, "detalhe": detalhe, **extras}
        self.guardrails.append(evento)
        registro = Registro(
            etapa="guardrail",
            acao=nome,
            resultado=evento,
            mensagem=detalhe or None,
        )
        self._gravar(registro, "ok" if aprovado else "bloqueado", 0)

    def concluir(self, status: str, erro: str | None = None, **campos: Any) -> None:
        atribuicoes = ["status = :status", "finalizada_em = now()", "erro = :erro"]
        valores: dict[str, Any] = {"run_id": self.run_id, "status": status, "erro": erro}

        for nome, valor in campos.items():
            if nome in {"metricas", "fontes", "guardrails"}:
                atribuicoes.append(f"{nome} = CAST(:{nome} AS jsonb)")
                valores[nome] = json.dumps(valor, default=str)
            else:
                atribuicoes.append(f"{nome} = :{nome}")
                valores[nome] = valor

        with engine_escrita().begin() as conexao:
            conexao.execute(
                text(f"UPDATE srag.execucao SET {', '.join(atribuicoes)} WHERE run_id = :run_id"),
                valores,
            )

    def _gravar(self, registro: Registro, status: str, duracao_ms: int) -> None:
        self._sequencia += 1
        linha = {
            "run_id": self.run_id,
            "sequencia": self._sequencia,
            "ocorrido_em": datetime.now(UTC).isoformat(),
            "etapa": registro.etapa,
            "acao": registro.acao,
            "status": status,
            "duracao_ms": duracao_ms,
            "parametros": registro.parametros,
            "resultado": registro.resultado,
            "modelo": registro.modelo,
            "tokens_entrada": registro.tokens_entrada,
            "tokens_saida": registro.tokens_saida,
            "mensagem": registro.mensagem,
        }
        self._no_banco(linha)
        self._no_arquivo(linha)

    def _no_banco(self, linha: dict[str, Any]) -> None:
        comando = text(
            "INSERT INTO srag.auditoria (run_id, sequencia, etapa, acao, status, duracao_ms, "
            "parametros, resultado, modelo, tokens_entrada, tokens_saida, mensagem) "
            "VALUES (:run_id, :sequencia, :etapa, :acao, :status, :duracao_ms, "
            "CAST(:parametros AS jsonb), CAST(:resultado AS jsonb), :modelo, :tokens_entrada, "
            ":tokens_saida, :mensagem)"
        )
        valores = dict(linha)
        valores.pop("ocorrido_em")
        valores["parametros"] = json.dumps(linha["parametros"], default=str)
        valores["resultado"] = json.dumps(linha["resultado"], default=str)
        try:
            with engine_escrita().begin() as conexao:
                conexao.execute(comando, valores)
        except Exception:
            # Falha de auditoria nao pode derrubar a execucao, mas tem que ficar visivel.
            logger.exception("nao consegui gravar a auditoria no banco")

    def _no_arquivo(self, linha: dict[str, Any]) -> None:
        try:
            with self._arquivo.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")
        except OSError:
            logger.exception("nao consegui gravar a auditoria em disco")


def trilha(run_id: str) -> list[dict[str, Any]]:
    """Le a trilha de uma execucao, em ordem."""
    consulta = text(
        "SELECT sequencia, ocorrido_em, etapa, acao, status, duracao_ms, parametros, "
        "resultado, modelo, tokens_entrada, tokens_saida, mensagem "
        "FROM srag.auditoria WHERE run_id = :run_id ORDER BY sequencia"
    )
    with engine_escrita().connect() as conexao:
        return [dict(linha._mapping) for linha in conexao.execute(consulta, {"run_id": run_id})]


def execucao(run_id: str) -> dict[str, Any] | None:
    consulta = text(
        "SELECT run_id, status, criada_em, finalizada_em, parametros, data_referencia, "
        "relatorio_md, relatorio_html, caminho_pdf, metricas, fontes, guardrails, erro "
        "FROM srag.execucao WHERE run_id = :run_id"
    )
    with engine_escrita().connect() as conexao:
        linha = conexao.execute(consulta, {"run_id": run_id}).first()
    return dict(linha._mapping) if linha else None


def ultimas_execucoes(limite: int = 20) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT run_id, status, criada_em, finalizada_em, parametros, data_referencia "
        "FROM srag.execucao ORDER BY criada_em DESC LIMIT :limite"
    )
    with engine_escrita().connect() as conexao:
        return [dict(linha._mapping) for linha in conexao.execute(consulta, {"limite": limite})]


def caminho_do_jsonl() -> Path:
    return get_config().dir_logs / ARQUIVO_JSONL
