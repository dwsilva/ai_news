# Os alvos assumem docker e python disponiveis. No Windows, rodar de dentro do WSL.
COMPOSE := docker compose
ANO ?= 2024
UF ?=

.PHONY: up down logs shell schema ingest relatorio test lint diagrama

up:
	$(COMPOSE) up -d --build
	$(COMPOSE) exec -T api python -m srag.cli schema

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

shell:
	$(COMPOSE) exec api bash

schema:
	$(COMPOSE) exec -T api python -m srag.cli schema

ingest:
	$(COMPOSE) exec -T api python -m srag.cli ingestao --ano $(ANO)

relatorio:
	$(COMPOSE) exec -T api python -m srag.cli relatorio $(if $(UF),--uf $(UF),)

diagrama:
	$(COMPOSE) exec -T api python -m srag.cli diagrama

test:
	$(COMPOSE) exec -T api pytest -q

lint:
	$(COMPOSE) exec -T api ruff check src tests
