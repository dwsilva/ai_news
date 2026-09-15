"""Testes de contrato da API.

Nao disparam geracao de relatorio: isso e coberto em test_agente. Aqui interessa que as rotas
respondam o que a interface espera e que parametro invalido pare na borda.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from srag.api.main import app


@pytest.fixture
def cliente(banco):
    return TestClient(app)


def test_health_relata_a_situacao_do_servico(cliente):
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] in {"ok", "degradado"}
    assert "internacoes" in corpo


def test_opcoes_traz_as_27_ufs(cliente):
    corpo = cliente.get("/api/opcoes").json()

    assert len(corpo["ufs"]) == 27
    assert {"sigla": "SC", "nome": "Santa Catarina"} in corpo["ufs"]
    assert corpo["janela"]["padrao"] == 30


def test_metricas_devolve_o_painel_completo(cliente, inserir, dia):
    inserir(
        {"chave_notificacao": "a", "dt_sintomas": dia(1), "evolucao": "Óbito"},
        {"chave_notificacao": "b", "dt_sintomas": dia(2), "evolucao": "Cura"},
    )

    corpo = cliente.get("/api/metricas", params={"data_referencia": "2026-06-30"}).json()

    assert len(corpo["metricas"]) == 4
    assert len(corpo["series"]) == 2
    assert corpo["total_registros"] == 2


def test_metricas_sem_dados_responde_conflito(cliente, limpar):
    resposta = cliente.get("/api/metricas")

    assert resposta.status_code == 409


def test_janela_fora_do_intervalo_e_recusada_na_borda(cliente):
    assert cliente.get("/api/metricas", params={"janela_dias": 400}).status_code == 422
    assert cliente.post("/api/relatorios", json={"janela_dias": 1}).status_code == 422


def test_execucao_inexistente_responde_404(cliente):
    assert cliente.get("/api/relatorios/nao-existe").status_code == 404
    assert cliente.get("/api/execucoes/nao-existe/auditoria").status_code == 404
    assert cliente.get("/api/relatorios/nao-existe/pdf").status_code == 404


def test_consulta_de_execucao_traz_as_etapas(cliente, banco):
    from srag.auditoria import Auditor

    auditor = Auditor("execucao-api", {"uf": "SC"})
    auditor.abrir()
    with auditor.etapa("metricas", "consultar_banco"):
        pass
    auditor.concluir("concluido", data_referencia=date(2026, 6, 30))

    corpo = cliente.get("/api/relatorios/execucao-api").json()

    assert corpo["status"] == "concluido"
    assert corpo["etapas"][0]["acao"] == "consultar_banco"
    # O markdown nao volta nesta rota para nao duplicar o payload do HTML.
    assert "relatorio_md" not in corpo


def test_a_pagina_inicial_e_servida(cliente):
    resposta = cliente.get("/")

    assert resposta.status_code == 200
    assert "Vigilância de SRAG" in resposta.text
