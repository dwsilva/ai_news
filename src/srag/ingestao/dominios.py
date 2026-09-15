"""Dicionario de dominios do SIVEP-Gripe.

Os codigos vem do dicionario de variaveis publicado junto com a base no Open DATASUS.
Tudo que nao esta mapeado vira "Ignorado" - nunca "Nao". Essa distincao importa: tratar
campo em branco como negativa infla artificialmente o denominador das taxas.
"""

IGNORADO = "Ignorado"

SIM_NAO = {"1": "Sim", "2": "Nao", "9": IGNORADO}

SEXO = {"M": "Masculino", "F": "Feminino", "I": IGNORADO}

EVOLUCAO = {
    "1": "Cura",
    "2": "Obito",
    "3": "Obito por outras causas",
    "9": IGNORADO,
}

SUPORTE_VENTILATORIO = {
    "1": "Sim, invasivo",
    "2": "Sim, nao invasivo",
    "3": "Nao",
    "9": IGNORADO,
}

CLASSIFICACAO_FINAL = {
    "1": "SRAG por influenza",
    "2": "SRAG por outro virus respiratorio",
    "3": "SRAG por outro agente etiologico",
    "4": "SRAG nao especificado",
    "5": "SRAG por covid-19",
}

CRITERIO_ENCERRAMENTO = {
    "1": "Laboratorial",
    "2": "Clinico epidemiologico",
    "3": "Clinico",
    "4": "Clinico imagem",
}

PCR_RESULTADO = {
    "1": "Detectavel",
    "2": "Nao detectavel",
    "3": "Inconclusivo",
    "4": "Nao realizado",
    "5": "Aguardando resultado",
    "9": IGNORADO,
}

# TP_IDADE informa a unidade de NU_IDADE_N.
UNIDADE_IDADE = {"1": "dia", "2": "mes", "3": "ano"}

# Faixas usadas nos boletins de SRAG do Ministerio da Saude.
FAIXAS_ETARIAS: list[tuple[int, int, str]] = [
    (0, 0, "< 1 ano"),
    (1, 4, "1 a 4 anos"),
    (5, 11, "5 a 11 anos"),
    (12, 17, "12 a 17 anos"),
    (18, 29, "18 a 29 anos"),
    (30, 39, "30 a 39 anos"),
    (40, 49, "40 a 49 anos"),
    (50, 59, "50 a 59 anos"),
    (60, 69, "60 a 69 anos"),
    (70, 79, "70 a 79 anos"),
    (80, 130, "80 anos ou mais"),
]

ORDEM_FAIXAS = [rotulo for _, _, rotulo in FAIXAS_ETARIAS] + [IGNORADO]

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

# Colunas lidas do CSV. Tudo que nao esta nesta lista e descartado ainda na leitura,
# antes de qualquer coisa tocar o banco - inclusive os campos de texto livre da ficha,
# que sao a principal fonte de dado sensivel nao estruturado da base.
COLUNAS_ORIGEM = [
    "NU_NOTIFIC",
    "DT_NOTIFIC",
    "SEM_PRI",
    "DT_SIN_PRI",
    "SG_UF_NOT",
    "CO_MUN_NOT",
    "SG_UF",
    "CS_SEXO",
    "NU_IDADE_N",
    "TP_IDADE",
    "CLASSI_FIN",
    "CRITERIO",
    "HOSPITAL",
    "DT_INTERNA",
    "UTI",
    "DT_ENTUTI",
    "DT_SAIDUTI",
    "SUPORT_VEN",
    "EVOLUCAO",
    "DT_EVOLUCA",
    "DT_ENCERRA",
    "VACINA",
    "VACINA_COV",
    "DOSE_1_COV",
    "DOSE_2_COV",
    "DOSE_REF",
    "PCR_RESUL",
]
