"""Testes da normalizacao do CSV do SIVEP.

Os casos aqui sao os problemas que a base real tem de verdade: data impossivel, codigo fora
do dicionario, campo vazio, saida da UTI antes da entrada.
"""

import pandas as pd
import pytest

from srag.ingestao.anonimizacao import (
    IdentificadorResidual,
    chave_pseudonimizada,
    faixa_etaria,
    garantir_ausencia_de_identificadores,
)
from srag.ingestao.transform import descartar_sem_data_de_sintomas, normalizar


def linha(**campos) -> pd.DataFrame:
    base = {
        "NU_NOTIFIC": "123456",
        "DT_NOTIFIC": "10/06/2024",
        "SEM_PRI": "24",
        "DT_SIN_PRI": "05/06/2024",
        "SG_UF_NOT": "SC",
        "CO_MUN_NOT": "420540",
        "SG_UF": "SC",
        "CS_SEXO": "F",
        "NU_IDADE_N": "67",
        "TP_IDADE": "3",
        "CLASSI_FIN": "5",
        "CRITERIO": "1",
        "HOSPITAL": "1",
        "DT_INTERNA": "06/06/2024",
        "UTI": "1",
        "DT_ENTUTI": "06/06/2024",
        "DT_SAIDUTI": "16/06/2024",
        "SUPORT_VEN": "1",
        "EVOLUCAO": "1",
        "DT_EVOLUCA": "20/06/2024",
        "DT_ENCERRA": "25/06/2024",
        "VACINA": "1",
        "VACINA_COV": "1",
        "DOSE_1_COV": "01/03/2021",
        "DOSE_2_COV": "01/06/2021",
        "DOSE_REF": "",
        "PCR_RESUL": "1",
    }
    base.update(campos)
    return pd.DataFrame([base])


def test_traduz_os_codigos_do_dicionario():
    resultado = normalizar(linha(), ano_base=2024).iloc[0]

    assert resultado["sexo"] == "Feminino"
    assert resultado["evolucao"] == "Cura"
    assert resultado["uti"] == "Sim"
    assert resultado["classificacao_final"] == "SRAG por covid-19"
    assert resultado["faixa_etaria"] == "60 a 69 anos"


def test_campo_vazio_ou_codigo_desconhecido_vira_ignorado_e_nunca_nao():
    resultado = normalizar(linha(UTI="", VACINA_COV="7", EVOLUCAO=""), ano_base=2024).iloc[0]

    assert resultado["uti"] == "Ignorado"
    assert resultado["vacina_covid"] == "Ignorado"
    assert resultado["evolucao"] == "Ignorado"


def test_le_tanto_data_brasileira_quanto_iso():
    brasileira = normalizar(linha(), ano_base=2024).iloc[0]["dt_sintomas"]
    iso = normalizar(
        linha(DT_SIN_PRI="2024-06-05T00:00:00.000Z"), ano_base=2024
    ).iloc[0]["dt_sintomas"]

    assert str(brasileira) == "2024-06-05"
    assert str(iso) == "2024-06-05"


@pytest.mark.parametrize("valor", ["31/02/2024", "05/06/1899", "05/06/2199", "", "xx/xx/xxxx"])
def test_data_impossivel_vira_nulo(valor):
    resultado = normalizar(linha(DT_SIN_PRI=valor), ano_base=2024).iloc[0]

    assert pd.isna(resultado["dt_sintomas"])


def test_descarta_notificacao_sem_data_de_sintomas():
    dados = normalizar(
        pd.concat([linha(), linha(NU_NOTIFIC="999", DT_SIN_PRI="")], ignore_index=True),
        ano_base=2024,
    )

    validas, descartadas = descartar_sem_data_de_sintomas(dados)

    assert len(validas) == 1
    assert descartadas == 1


def test_idade_em_meses_cai_na_faixa_de_menor_de_um_ano():
    resultado = normalizar(linha(NU_IDADE_N="8", TP_IDADE="2"), ano_base=2024).iloc[0]

    assert resultado["faixa_etaria"] == "< 1 ano"


def test_saida_da_uti_antes_da_entrada_nao_vira_permanencia_negativa():
    resultado = normalizar(
        linha(DT_ENTUTI="16/06/2024", DT_SAIDUTI="06/06/2024"), ano_base=2024
    ).iloc[0]

    assert pd.isna(resultado["dias_uti"])


def test_conta_as_doses_de_covid_efetivamente_registradas():
    resultado = normalizar(linha(), ano_base=2024).iloc[0]

    assert resultado["doses_covid"] == 2


def test_uf_fora_da_lista_vira_nulo():
    resultado = normalizar(linha(SG_UF_NOT="ZZ"), ano_base=2024).iloc[0]

    assert pd.isna(resultado["uf_notificacao"])


def test_a_chave_e_estavel_e_nao_carrega_o_numero_da_notificacao():
    primeira = chave_pseudonimizada(2024, "123456", "420540", "10/06/2024", "05/06/2024")
    segunda = chave_pseudonimizada(2024, "123456", "420540", "10/06/2024", "05/06/2024")
    outra = chave_pseudonimizada(2024, "999999", "420540", "10/06/2024", "05/06/2024")

    assert primeira == segunda
    assert primeira != outra
    assert "123456" not in primeira


def test_nenhuma_coluna_identificadora_chega_na_carga():
    resultado = normalizar(linha(), ano_base=2024)

    assert "NU_NOTIFIC" not in resultado.columns
    assert "CO_MUN_NOT" not in resultado.columns
    garantir_ausencia_de_identificadores(resultado)


def test_identificador_que_escapa_derruba_a_carga():
    dados = normalizar(linha(), ano_base=2024)
    dados["DT_NASC"] = "01/01/1957"

    with pytest.raises(IdentificadorResidual):
        garantir_ausencia_de_identificadores(dados)


@pytest.mark.parametrize(
    ("idade", "esperado"),
    [(0, "< 1 ano"), (3, "1 a 4 anos"), (67, "60 a 69 anos"), (95, "80 anos ou mais")],
)
def test_faixas_etarias(idade, esperado):
    assert faixa_etaria(idade) == esperado


def test_idade_ausente_ou_absurda_fica_como_ignorado():
    assert faixa_etaria(None) == "Ignorado"
    assert faixa_etaria(-1) == "Ignorado"
