"""Rotas HTTP.

A API nao calcula nada: ela valida o corpo da requisicao, dispara o servico e le do banco.
Toda a logica esta em srag.servico, que e o mesmo caminho usado pela CLI.
"""

import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from srag import auditoria
from srag.auditoria import novo_run_id
from srag.config import get_config
from srag.guardrails.entrada import JANELA_MAXIMA, JANELA_MINIMA, PedidoInvalido
from srag.ingestao.dominios import CLASSIFICACAO_FINAL, NOMES_DE_UF
from srag.metricas.calculos import BaseVazia, montar_painel
from srag.metricas.modelos import Filtro
from srag.servico import gerar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class PedidoDeRelatorio(BaseModel):
    uf: str | None = None
    janela_dias: int = Field(default=30, ge=JANELA_MINIMA, le=JANELA_MAXIMA)
    data_referencia: date | None = None
    classificacao_final: str | None = None
    observacao: str | None = None


class RelatorioAceito(BaseModel):
    run_id: str
    status: str


@router.get("/opcoes")
def opcoes() -> dict:
    """Valores aceitos pelo formulario. O front monta os selects a partir daqui."""
    return {
        "ufs": [{"sigla": sigla, "nome": nome} for sigla, nome in sorted(NOMES_DE_UF.items())],
        "classificacoes": sorted(CLASSIFICACAO_FINAL.values()),
        "janela": {"minima": JANELA_MINIMA, "maxima": JANELA_MAXIMA, "padrao": 30},
    }


@router.post("/relatorios", response_model=RelatorioAceito, status_code=202)
def solicitar_relatorio(pedido: PedidoDeRelatorio, tarefas: BackgroundTasks) -> RelatorioAceito:
    """Dispara a geracao e devolve na hora o identificador para acompanhar."""
    run_id = novo_run_id()
    tarefas.add_task(_executar, run_id, pedido)
    return RelatorioAceito(run_id=run_id, status="em_andamento")


@router.get("/relatorios")
def listar_relatorios(limite: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return auditoria.ultimas_execucoes(limite)


@router.get("/relatorios/{run_id}")
def consultar_relatorio(run_id: str) -> dict:
    registro = auditoria.execucao(run_id)
    if not registro:
        raise HTTPException(status_code=404, detail="execucao nao encontrada")

    registro["etapas"] = [
        {
            "etapa": passo["etapa"],
            "acao": passo["acao"],
            "status": passo["status"],
            "duracao_ms": passo["duracao_ms"],
        }
        for passo in auditoria.trilha(run_id)
    ]
    # O markdown ja esta no HTML; devolver os dois so aumenta o payload.
    registro.pop("relatorio_md", None)
    return registro


@router.get("/relatorios/{run_id}/pdf")
def baixar_pdf(run_id: str) -> FileResponse:
    registro = auditoria.execucao(run_id)
    if not registro:
        raise HTTPException(status_code=404, detail="execucao nao encontrada")

    caminho = registro.get("caminho_pdf")
    if not caminho or not Path(caminho).exists():
        raise HTTPException(status_code=404, detail="PDF nao disponivel para esta execucao")

    return FileResponse(caminho, media_type="application/pdf", filename=f"srag-{run_id}.pdf")


@router.get("/relatorios/{run_id}/markdown")
def baixar_markdown(run_id: str) -> dict:
    registro = auditoria.execucao(run_id)
    if not registro:
        raise HTTPException(status_code=404, detail="execucao nao encontrada")
    return {"run_id": run_id, "markdown": registro.get("relatorio_md") or ""}


@router.get("/execucoes/{run_id}/auditoria")
def consultar_auditoria(run_id: str) -> dict:
    registro = auditoria.execucao(run_id)
    if not registro:
        raise HTTPException(status_code=404, detail="execucao nao encontrada")

    return {
        "run_id": run_id,
        "status": registro["status"],
        "parametros": registro["parametros"],
        "guardrails": registro.get("guardrails") or [],
        "trilha": auditoria.trilha(run_id),
    }


@router.get("/metricas")
def consultar_metricas(
    uf: str | None = None,
    janela_dias: int = Query(default=30, ge=JANELA_MINIMA, le=JANELA_MAXIMA),
    data_referencia: date | None = None,
) -> dict:
    """Indicadores puros, sem passar pelo modelo.

    Serve para conferir qualquer numero do relatorio contra a fonte.
    """
    try:
        painel = montar_painel(
            Filtro(uf=uf, janela_dias=janela_dias, data_referencia=data_referencia)
        )
    except BaseVazia as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    return painel.model_dump(mode="json")


def _executar(run_id: str, pedido: PedidoDeRelatorio) -> None:
    try:
        gerar(
            uf=pedido.uf,
            janela_dias=pedido.janela_dias,
            data_referencia=pedido.data_referencia,
            classificacao_final=pedido.classificacao_final,
            observacao=pedido.observacao,
            run_id=run_id,
        )
    except PedidoInvalido as erro:
        logger.warning("pedido %s recusado: %s", run_id, erro)
    except Exception:
        # O servico ja gravou o erro na execucao; aqui so nao pode escapar para o worker.
        logger.exception("execucao %s falhou", run_id)


def diretorio_estatico() -> Path:
    return Path(__file__).parent / "static"


def caminho_dos_relatorios() -> Path:
    return get_config().dir_relatorios
