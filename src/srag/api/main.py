"""Aplicacao FastAPI: serve a API e a interface estatica."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from srag.api.rotas import diretorio_estatico, router
from srag.config import get_config
from srag.db import aplicar_schema, engine_escrita
from srag.log import configurar_logging

logger = logging.getLogger(__name__)

configurar_logging()


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    get_config().preparar_diretorios()
    try:
        aplicar_schema()
    except Exception:
        # A API sobe mesmo assim: /health mostra o problema e o operador corrige.
        logger.exception("nao consegui aplicar o schema no boot")
    yield


app = FastAPI(
    title="Relatorios de SRAG",
    version="0.1.0",
    description=(
        "Geracao automatizada de relatorios sobre Sindrome Respiratoria Aguda Grave a partir "
        "dos microdados do SIVEP-Gripe e de noticias coletadas em tempo real."
    ),
    lifespan=ciclo_de_vida,
)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    cfg = get_config()
    situacao = {"status": "ok", "banco": "ok", "modelo": "configurado", "internacoes": 0}

    try:
        with engine_escrita().connect() as conexao:
            situacao["internacoes"] = conexao.execute(
                text("SELECT count(*) FROM srag.internacao")
            ).scalar_one()
    except Exception as erro:
        situacao["status"] = "degradado"
        situacao["banco"] = f"indisponivel: {type(erro).__name__}"

    if not cfg.google_api_key:
        situacao["status"] = "degradado"
        situacao["modelo"] = "sem GOOGLE_API_KEY: relatorio sai so com os indicadores"

    if situacao["internacoes"] == 0 and situacao["banco"] == "ok":
        situacao["status"] = "degradado"
        situacao["banco"] = "sem dados carregados: rode a ingestao"

    return situacao


@app.get("/", include_in_schema=False)
def pagina_inicial() -> FileResponse:
    return FileResponse(diretorio_estatico() / "index.html")


app.mount("/static", StaticFiles(directory=diretorio_estatico()), name="static")
