# Atalhos para os comandos do README. Sao conveniencia: tudo aqui pode ser rodado
# direto com docker compose, que e o caminho para quem nao tem make (PowerShell, cmd).
COMPOSE := docker compose
# ANOS aceita varios: make ingest ANOS="2024 2025 2026"
ANO  ?= 2026
ANOS ?= $(ANO)
UF   ?=

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
	$(COMPOSE) exec -T api python -m srag.cli ingestao $(foreach ano,$(ANOS),--ano $(ano))

relatorio:
	$(COMPOSE) exec -T api python -m srag.cli relatorio $(if $(UF),--uf $(UF),)

diagrama:
	$(COMPOSE) exec -T api python -m srag.cli diagrama

test:
	$(COMPOSE) exec -T api pytest -q

lint:
	$(COMPOSE) exec -T api ruff check src tests
