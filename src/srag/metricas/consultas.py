"""Consultas SQL das metricas.

Sao todas parametrizadas e ficam aqui, escritas a mao. O modelo de linguagem nunca gera SQL:
ele recebe o resultado ja calculado. Isso tira injecao de SQL do mapa de risco e, mais
importante, torna cada numero do relatorio reproduzivel fora do agente.
"""

# Aplicado a todas as consultas. O CAST explicito e necessario porque o psycopg nao infere
# o tipo de um parametro que chega como NULL.
FILTRO_COMUM = """
    AND (CAST(:uf AS text) IS NULL OR uf_notificacao = CAST(:uf AS text))
    AND (CAST(:classificacao AS text) IS NULL
         OR classificacao_final = CAST(:classificacao AS text))
"""

ULTIMA_DATA = f"""
SELECT max(dt_sintomas) AS ultima_data, count(*) AS total
FROM srag.internacao
WHERE dt_sintomas IS NOT NULL
  {FILTRO_COMUM}
"""

VARIACAO_DE_CASOS = f"""
SELECT
    count(*) FILTER (WHERE dt_sintomas > :corte)  AS periodo_atual,
    count(*) FILTER (WHERE dt_sintomas <= :corte) AS periodo_anterior
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio_anterior AND :fim
  {FILTRO_COMUM}
"""

MORTALIDADE = f"""
SELECT
    count(*) FILTER (WHERE evolucao = 'Óbito') AS obitos_srag,
    count(*) FILTER (WHERE evolucao = 'Óbito por outras causas') AS obitos_outras_causas,
    count(*) FILTER (WHERE evolucao IN ('Cura', 'Óbito', 'Óbito por outras causas'))
        AS com_desfecho,
    count(*) FILTER (WHERE evolucao = 'Ignorado') AS sem_desfecho
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
"""

OCUPACAO_UTI = f"""
SELECT
    count(*) FILTER (WHERE uti = 'Sim') AS em_uti,
    count(*) FILTER (WHERE uti IN ('Sim', 'Não')) AS com_informacao,
    count(*) FILTER (WHERE uti = 'Ignorado') AS ignorados,
    avg(dias_uti) FILTER (WHERE uti = 'Sim' AND dias_uti IS NOT NULL) AS media_dias_uti
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
"""

VACINACAO = f"""
SELECT
    count(*) FILTER (WHERE vacina_covid = 'Sim') AS vacinados,
    count(*) FILTER (WHERE vacina_covid IN ('Sim', 'Não')) AS com_informacao,
    count(*) FILTER (WHERE vacina_covid = 'Ignorado') AS ignorados
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
"""

VACINACAO_POR_FAIXA = f"""
SELECT
    faixa_etaria AS rotulo,
    count(*) FILTER (WHERE vacina_covid = 'Sim') AS numerador,
    count(*) FILTER (WHERE vacina_covid IN ('Sim', 'Não')) AS denominador
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
GROUP BY faixa_etaria
ORDER BY faixa_etaria
"""

CASOS_POR_DIA = f"""
SELECT dt_sintomas AS data, count(*) AS casos
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
GROUP BY dt_sintomas
ORDER BY dt_sintomas
"""

CASOS_POR_MES = f"""
SELECT date_trunc('month', dt_sintomas)::date AS data, count(*) AS casos
FROM srag.internacao
WHERE dt_sintomas BETWEEN :inicio AND :fim
  {FILTRO_COMUM}
GROUP BY 1
ORDER BY 1
"""
