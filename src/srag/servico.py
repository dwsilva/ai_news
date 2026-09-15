"""Servico de geracao de relatorio.

E o ponto de entrada unico: a CLI e a API chamam esta funcao, nada mais. Ela valida o pedido,
abre a execucao na auditoria, roda o grafo e persiste o resultado.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from srag.agente.grafo import Pipeline
from srag.agente.llm import ChaveAusente, ClienteLLM
from srag.auditoria import Auditor, novo_run_id
from srag.config import get_config
from srag.guardrails.entrada import PedidoInvalido, validar
from srag.metricas.modelos import Painel
from srag.noticias.indexacao import Embeddings
from srag.noticias.modelos import Fonte
from srag.relatorio import render

logger = logging.getLogger(__name__)


@dataclass
class Relatorio:
    run_id: str
    painel: Painel
    markdown: str
    html: str
    fontes: list[Fonte]
    guardrails: list[dict]
    pasta: Path
    pdf: Path | None


def gerar(
    uf: str | None = None,
    janela_dias: int = 30,
    data_referencia: date | None = None,
    classificacao_final: str | None = None,
    observacao: str | None = None,
    run_id: str | None = None,
) -> Relatorio:
    cfg = get_config()
    cfg.preparar_diretorios()

    run_id = run_id or novo_run_id()
    pedido = {
        "uf": uf,
        "janela_dias": janela_dias,
        "data_referencia": str(data_referencia) if data_referencia else None,
        "classificacao_final": classificacao_final,
        "tem_observacao": bool(observacao),
    }
    auditor = Auditor(run_id, pedido)
    auditor.abrir()

    try:
        filtro, observacao_aprovada = validar(
            uf=uf,
            janela_dias=janela_dias,
            data_referencia=data_referencia,
            classificacao_final=classificacao_final,
            observacao=observacao,
        )
    except PedidoInvalido as erro:
        auditor.guardrail("validacao_do_pedido", False, "; ".join(erro.problemas))
        auditor.concluir("recusado", erro=str(erro))
        raise

    auditor.guardrail("validacao_do_pedido", True, filtro.descricao())

    try:
        llm = _cliente_llm(auditor)
        embeddings = Embeddings() if llm else None
        resultado = Pipeline(auditor, llm=llm, embeddings=embeddings).executar(
            {"run_id": run_id, "filtro": filtro, "observacao": observacao_aprovada}
        )
    except Exception as erro:
        logger.exception("execucao %s falhou", run_id)
        auditor.concluir("erro", erro=f"{type(erro).__name__}: {erro}")
        raise

    relatorio = _persistir(auditor, run_id, resultado)
    logger.info("relatorio %s gerado em %s", run_id, relatorio.pasta)
    return relatorio


def _cliente_llm(auditor: Auditor) -> ClienteLLM | None:
    """Sem chave, o relatorio ainda sai - so que com os numeros e sem a analise textual."""
    try:
        return ClienteLLM(auditor)
    except ChaveAusente as erro:
        logger.warning("%s; gerando relatorio apenas com os indicadores", erro)
        auditor.guardrail("modelo_disponivel", False, str(erro))
        return None


def _persistir(auditor: Auditor, run_id: str, resultado: dict) -> Relatorio:
    pasta = get_config().dir_relatorios / run_id
    pasta.mkdir(parents=True, exist_ok=True)

    markdown = resultado["relatorio_md"]
    html = render.para_html(markdown, pasta)
    (pasta / "relatorio.md").write_text(markdown, encoding="utf-8")
    (pasta / "relatorio.html").write_text(html, encoding="utf-8")
    pdf = render.para_pdf(html, pasta / "relatorio.pdf")

    painel: Painel = resultado["painel"]
    fontes = resultado.get("fontes", [])
    auditor.concluir(
        "concluido",
        data_referencia=painel.data_referencia,
        relatorio_md=markdown,
        relatorio_html=html,
        caminho_pdf=str(pdf) if pdf else None,
        metricas=[metrica.model_dump(mode="json") for metrica in painel.metricas],
        fontes=[fonte.model_dump(mode="json") for fonte in fontes],
        guardrails=auditor.guardrails,
    )

    return Relatorio(
        run_id=run_id,
        painel=painel,
        markdown=markdown,
        html=html,
        fontes=fontes,
        guardrails=auditor.guardrails,
        pasta=pasta,
        pdf=pdf,
    )
