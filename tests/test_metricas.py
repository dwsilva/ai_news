from datetime import date

from srag.metricas.calculos import (
    montar_painel,
    serie_diaria,
    taxa_de_aumento,
    taxa_de_mortalidade,
    taxa_de_ocupacao_de_uti,
    taxa_de_vacinacao,
)
from srag.metricas.modelos import Filtro, Janela

JANELA = Janela(inicio=date(2026, 6, 1), fim=date(2026, 6, 30))


def test_taxa_de_aumento_compara_a_janela_anterior(inserir, filtro_padrao, dia):
    inserir(
        *[{"chave_notificacao": f"atual-{i}", "dt_sintomas": dia(i)} for i in range(10)],
        *[{"chave_notificacao": f"ant-{i}", "dt_sintomas": dia(35 + i)} for i in range(5)],
    )

    metrica = taxa_de_aumento(filtro_padrao, JANELA)

    assert metrica.numerador == 10
    assert metrica.denominador == 5
    assert metrica.valor == 100.0


def test_taxa_de_aumento_fica_indisponivel_sem_periodo_anterior(inserir, filtro_padrao, dia):
    inserir({"dt_sintomas": dia(1)})

    metrica = taxa_de_aumento(filtro_padrao, JANELA)

    assert metrica.valor is None
    assert metrica.formatado() == "indisponível"


def test_mortalidade_deixa_casos_sem_desfecho_fora_do_denominador(inserir, filtro_padrao, dia):
    inserir(
        {"chave_notificacao": "a", "dt_sintomas": dia(2), "evolucao": "Óbito"},
        {"chave_notificacao": "b", "dt_sintomas": dia(3), "evolucao": "Cura"},
        {"chave_notificacao": "c", "dt_sintomas": dia(4), "evolucao": "Cura"},
        {"chave_notificacao": "d", "dt_sintomas": dia(5), "evolucao": "Cura"},
        {"chave_notificacao": "e", "dt_sintomas": dia(6), "evolucao": "Ignorado"},
    )

    metrica = taxa_de_mortalidade(filtro_padrao, JANELA)

    assert metrica.numerador == 1
    assert metrica.denominador == 4
    assert metrica.ignorados == 1
    assert metrica.valor == 25.0


def test_mortalidade_separa_obito_por_outras_causas(inserir, filtro_padrao, dia):
    inserir(
        {"chave_notificacao": "a", "dt_sintomas": dia(2), "evolucao": "Óbito"},
        {"chave_notificacao": "b", "dt_sintomas": dia(3), "evolucao": "Óbito por outras causas"},
    )

    metrica = taxa_de_mortalidade(filtro_padrao, JANELA)

    assert metrica.numerador == 1
    assert metrica.denominador == 2
    quebras = {quebra.rotulo: quebra.numerador for quebra in metrica.quebras}
    assert quebras["Óbitos por outras causas"] == 1


def test_ocupacao_de_uti_usa_so_as_fichas_preenchidas(inserir, filtro_padrao, dia):
    inserir(
        {"chave_notificacao": "a", "dt_sintomas": dia(1), "uti": "Sim", "dias_uti": 10},
        {"chave_notificacao": "b", "dt_sintomas": dia(2), "uti": "Não"},
        {"chave_notificacao": "c", "dt_sintomas": dia(3), "uti": "Ignorado"},
        {"chave_notificacao": "d", "dt_sintomas": dia(4), "uti": "Ignorado"},
    )

    metrica = taxa_de_ocupacao_de_uti(filtro_padrao, JANELA)

    assert metrica.numerador == 1
    assert metrica.denominador == 2
    assert metrica.ignorados == 2
    assert metrica.valor == 50.0


def test_ocupacao_de_uti_reporta_permanencia_media(inserir, filtro_padrao, dia):
    inserir(
        {"chave_notificacao": "a", "dt_sintomas": dia(1), "uti": "Sim", "dias_uti": 4},
        {"chave_notificacao": "b", "dt_sintomas": dia(2), "uti": "Sim", "dias_uti": 8},
    )

    metrica = taxa_de_ocupacao_de_uti(filtro_padrao, JANELA)

    permanencia = next(q for q in metrica.quebras if "Permanência" in q.rotulo)
    assert permanencia.valor == 6.0


def test_vacinacao_suprime_faixa_etaria_com_poucos_registros(inserir, filtro_padrao, dia):
    numerosa = [
        {
            "chave_notificacao": f"idoso-{i}",
            "dt_sintomas": dia(i + 1),
            "faixa_etaria": "60 a 69 anos",
            "vacina_covid": "Sim" if i % 2 == 0 else "Não",
        }
        for i in range(10)
    ]
    # Tres registros: abaixo do k=5, a faixa nao pode aparecer no relatorio.
    rara = [
        {
            "chave_notificacao": f"crianca-{i}",
            "dt_sintomas": dia(i + 1),
            "faixa_etaria": "5 a 11 anos",
            "vacina_covid": "Sim",
        }
        for i in range(3)
    ]
    inserir(*numerosa, *rara)

    metrica = taxa_de_vacinacao(filtro_padrao, JANELA)

    rotulos = [quebra.rotulo for quebra in metrica.quebras]
    assert "60 a 69 anos" in rotulos
    assert "5 a 11 anos" not in rotulos


def test_serie_diaria_preenche_os_dias_sem_notificacao(inserir, filtro_padrao, dia):
    inserir({"dt_sintomas": dia(0)}, {"chave_notificacao": "b", "dt_sintomas": dia(0)})

    serie = serie_diaria(filtro_padrao, date(2026, 6, 30))

    assert len(serie.pontos) == 30
    assert serie.pontos[-1].casos == 2
    assert all(ponto.casos == 0 for ponto in serie.pontos[:-1])


def test_data_de_referencia_recua_pelo_atraso_de_notificacao(inserir):
    inserir({"dt_sintomas": date(2026, 6, 30)})

    painel = montar_painel(Filtro())

    # A configuracao padrao descarta os 5 dias mais recentes da base.
    assert painel.data_referencia == date(2026, 6, 25)


def test_filtro_por_uf_nao_mistura_estados(inserir, filtro_padrao, dia):
    inserir(
        {"chave_notificacao": "sc", "dt_sintomas": dia(1), "uf_notificacao": "SC"},
        {"chave_notificacao": "sp", "dt_sintomas": dia(1), "uf_notificacao": "SP"},
        {"chave_notificacao": "sp2", "dt_sintomas": dia(2), "uf_notificacao": "SP"},
    )

    serie = serie_diaria(filtro_padrao.model_copy(update={"uf": "SP"}), date(2026, 6, 30))

    assert serie.total == 2


def test_faixas_etarias_saem_em_ordem_de_idade(inserir, filtro_padrao, dia):
    faixas = ["< 1 ano", "5 a 11 anos", "60 a 69 anos", "12 a 17 anos"]
    inserir(
        *[
            {
                "chave_notificacao": f"{faixa}-{i}",
                "dt_sintomas": dia(i + 1),
                "faixa_etaria": faixa,
                "vacina_covid": "Sim",
            }
            for faixa in faixas
            for i in range(6)
        ]
    )

    metrica = taxa_de_vacinacao(filtro_padrao, JANELA)

    assert [quebra.rotulo for quebra in metrica.quebras] == [
        "< 1 ano",
        "5 a 11 anos",
        "12 a 17 anos",
        "60 a 69 anos",
    ]


def test_a_leitura_e_somente_leitura_e_a_carga_tem_folga_de_tempo(banco):
    from srag.config import get_config
    from srag.db import opcoes_de_conexao

    cfg = get_config()
    leitura = opcoes_de_conexao(somente_leitura=True)
    escrita = opcoes_de_conexao(somente_leitura=False)

    assert "default_transaction_read_only=on" in leitura
    assert f"statement_timeout={cfg.statement_timeout_ms}" in leitura
    # A carga precisa de um limite proprio: com o do agente, o ano de pico da covid nao entra.
    assert "default_transaction_read_only" not in escrita
    assert f"statement_timeout={cfg.statement_timeout_carga_ms}" in escrita
    assert cfg.statement_timeout_carga_ms > cfg.statement_timeout_ms
