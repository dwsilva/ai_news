"""Testes do grafo do agente.

Rodam com um modelo falso: o que interessa aqui e o fluxo (o que acontece quando a
verificacao reprova o texto), nao a qualidade da redacao do Gemini.
"""

import hashlib
from datetime import UTC, datetime

import pytest

from srag.agente.estado import AnaliseDaMetrica, PlanoDeBusca, Redacao
from srag.agente.grafo import Pipeline
from srag.auditoria import Auditor
from srag.metricas.modelos import Filtro
from srag.noticias.modelos import Artigo, Dossie

DIMENSOES = 768


class EmbeddingsFalsos:
    """Vetor deterministico derivado do texto. Nao precisa fazer sentido semantico."""

    def documentos(self, textos: list[str]) -> list[list[float]]:
        return [self.pergunta(texto) for texto in textos]

    def pergunta(self, texto: str) -> list[float]:
        semente = hashlib.sha256(texto.encode("utf-8")).digest()
        return [(semente[i % len(semente)] - 128) / 128 for i in range(DIMENSOES)]


class LLMFalso:
    def __init__(self, *redacoes: Redacao) -> None:
        self.redacoes = list(redacoes)
        self.pedidos: list[str] = []

    def responder(self, sistema, usuario, formato, acao):
        self.pedidos.append(usuario)
        if formato is PlanoDeBusca:
            return PlanoDeBusca(buscas=[])
        # Quando so uma redacao foi programada, ela se repete em todas as tentativas.
        return self.redacoes.pop(0) if len(self.redacoes) > 1 else self.redacoes[0]


def redacao(comentario: str) -> Redacao:
    return Redacao(
        panorama=comentario,
        analises=[
            AnaliseDaMetrica(codigo=codigo, comentario=comentario)
            for codigo in (
                "taxa_aumento_casos",
                "taxa_mortalidade",
                "taxa_ocupacao_uti",
                "taxa_vacinacao",
            )
        ],
        sinais_de_alerta=["Acompanhar a evolução semanal."],
    )


@pytest.fixture
def base_com_casos(inserir, dia):
    inserir(
        *[
            {
                "chave_notificacao": f"caso-{i}",
                "dt_sintomas": dia(i % 40),
                "evolucao": "Óbito" if i % 10 == 0 else "Cura",
                "uti": "Sim" if i % 4 == 0 else "Não",
                "vacina_covid": "Sim" if i % 3 == 0 else "Não",
            }
            for i in range(120)
        ]
    )


@pytest.fixture
def sem_rede(monkeypatch):
    """Substitui a coleta por um dossie fixo, para o teste nao depender de internet."""
    dossie = Dossie(
        consulta="SRAG (Brasil)",
        artigos=[
            Artigo(
                titulo="InfoGripe aponta queda nos casos de SRAG",
                url="https://exemplo.br/infogripe",
                veiculo="Exemplo",
                publicado_em=datetime(2026, 6, 28, tzinfo=UTC),
                texto=(
                    "O boletim InfoGripe da Fiocruz indica queda na incidência de síndrome "
                    "respiratória aguda grave na maior parte das unidades federativas, com "
                    "estabilidade da ocupação de leitos de UTI pediátrica."
                ),
                texto_completo=True,
            )
        ],
    )
    monkeypatch.setattr("srag.agente.ferramentas.coletar", lambda uf=None: dossie)
    return dossie


def executar(llm, run_id: str) -> dict:
    auditor = Auditor(run_id, {"origem": "teste"})
    auditor.abrir()
    pipeline = Pipeline(auditor, llm=llm, embeddings=EmbeddingsFalsos())
    resultado = pipeline.executar({"run_id": run_id, "filtro": Filtro(), "observacao": None})
    resultado["auditor"] = auditor
    return resultado


def test_fluxo_completo_publica_o_texto_do_modelo(base_com_casos, sem_rede):
    texto = "Os casos permanecem em queda no período analisado [1]."

    resultado = executar(LLMFalso(redacao(texto)), "teste-feliz")

    assert texto in resultado["relatorio_md"]
    assert resultado["tentativas"] == 1
    assert not resultado["problemas"]


def test_texto_com_numero_inventado_provoca_reescrita(base_com_casos, sem_rede):
    ruim = "A mortalidade chegou a 91,4% no período."
    bom = "Os casos permanecem em queda no período analisado [1]."

    llm = LLMFalso(redacao(ruim), redacao(bom))
    resultado = executar(llm, "teste-reescrita")

    assert resultado["tentativas"] == 2
    assert bom in resultado["relatorio_md"]
    # A segunda chamada precisa carregar o motivo da recusa.
    assert "verificação automática recusou" in llm.pedidos[-1]


def test_apos_duas_recusas_o_relatorio_sai_com_ressalva(base_com_casos, sem_rede):
    ruim = "A mortalidade chegou a 91,4% no período."

    resultado = executar(LLMFalso(redacao(ruim), redacao(ruim)), "teste-ressalva")

    assert resultado["tentativas"] == 2
    assert "não passou na verificação automática" in resultado["relatorio_md"]
    assert "91,4%" not in resultado["relatorio_md"]


def test_indicadores_continuam_no_relatorio_mesmo_com_o_texto_recusado(base_com_casos, sem_rede):
    resultado = executar(LLMFalso(redacao("Mortalidade de 91,4%.")), "teste-indicadores")

    assert "Taxa de mortalidade" in resultado["relatorio_md"]
    assert "Taxa de ocupação de UTI" in resultado["relatorio_md"]


def test_a_trilha_registra_as_etapas_e_os_guardrails(base_com_casos, sem_rede):
    from srag.auditoria import trilha

    resultado = executar(LLMFalso(redacao("Casos em queda [1].")), "teste-trilha")

    passos = trilha("teste-trilha")
    acoes = {passo["acao"] for passo in passos}
    assert {"consultar_banco", "gerar_png", "buscar_rss", "indexar", "recuperar"} <= acoes
    assert any(passo["etapa"] == "guardrail" for passo in passos)
    assert any(g["guardrail"] == "verificacao_de_saida" for g in resultado["guardrails"])


def test_o_conteudo_da_noticia_chega_delimitado_ao_prompt(base_com_casos, sem_rede):
    llm = LLMFalso(redacao("Casos em queda [1]."))

    executar(llm, "teste-delimitacao")

    pedido_de_redacao = llm.pedidos[-1]
    assert "<<<NOTICIA" in pedido_de_redacao
    assert "NOTICIA>>>" in pedido_de_redacao
