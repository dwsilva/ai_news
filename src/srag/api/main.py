from fastapi import FastAPI

from srag.log import configurar_logging

configurar_logging()

app = FastAPI(title="Relatorios de SRAG", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
