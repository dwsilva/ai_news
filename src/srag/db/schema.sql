CREATE SCHEMA IF NOT EXISTS srag;

-- Uma linha por internacao notificada, ja com os campos sensiveis removidos na ingestao.
CREATE TABLE IF NOT EXISTS srag.internacao (
    id                      bigserial PRIMARY KEY,
    chave_notificacao       text NOT NULL UNIQUE,
    ano_base                smallint NOT NULL,
    dt_notificacao          date,
    dt_sintomas             date,
    semana_epi              smallint,
    uf_notificacao          char(2),
    uf_residencia           char(2),
    sexo                    text,
    faixa_etaria            text,
    classificacao_final     text,
    criterio_encerramento   text,
    hospitalizado           text,
    dt_internacao           date,
    uti                     text,
    dt_entrada_uti          date,
    dt_saida_uti            date,
    dias_uti                smallint,
    suporte_ventilatorio    text,
    evolucao                text,
    dt_evolucao             date,
    dt_encerramento         date,
    vacina_gripe            text,
    vacina_covid            text,
    doses_covid             smallint,
    pcr_resultado           text,
    carregado_em            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_internacao_dt_sintomas ON srag.internacao (dt_sintomas);
CREATE INDEX IF NOT EXISTS ix_internacao_uf ON srag.internacao (uf_notificacao);
CREATE INDEX IF NOT EXISTS ix_internacao_evolucao ON srag.internacao (evolucao);
CREATE INDEX IF NOT EXISTS ix_internacao_uti ON srag.internacao (uti);

-- Metadados de cada carga, para conseguir dizer de qual arquivo veio cada numero do relatorio.
CREATE TABLE IF NOT EXISTS srag.carga (
    id              bigserial PRIMARY KEY,
    ano_base        smallint NOT NULL,
    arquivo_origem  text NOT NULL,
    hash_arquivo    text,
    linhas_lidas    integer NOT NULL,
    linhas_gravadas integer NOT NULL,
    linhas_descartadas integer NOT NULL,
    iniciada_em     timestamptz NOT NULL,
    concluida_em    timestamptz NOT NULL DEFAULT now()
);

-- Cabecalho de cada geracao de relatorio.
CREATE TABLE IF NOT EXISTS srag.execucao (
    run_id          text PRIMARY KEY,
    status          text NOT NULL,
    criada_em       timestamptz NOT NULL DEFAULT now(),
    finalizada_em   timestamptz,
    parametros      jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_referencia date,
    relatorio_md    text,
    relatorio_html  text,
    caminho_pdf     text,
    metricas        jsonb,
    fontes          jsonb,
    guardrails      jsonb,
    erro            text
);

-- Trilha de auditoria: um registro por passo do grafo e por chamada de ferramenta.
CREATE TABLE IF NOT EXISTS srag.auditoria (
    id              bigserial PRIMARY KEY,
    run_id          text NOT NULL REFERENCES srag.execucao (run_id) ON DELETE CASCADE,
    sequencia       integer NOT NULL,
    ocorrido_em     timestamptz NOT NULL DEFAULT now(),
    etapa           text NOT NULL,
    acao            text NOT NULL,
    status          text NOT NULL,
    duracao_ms      integer,
    parametros      jsonb,
    resultado       jsonb,
    modelo          text,
    tokens_entrada  integer,
    tokens_saida    integer,
    mensagem        text
);

CREATE INDEX IF NOT EXISTS ix_auditoria_run ON srag.auditoria (run_id, sequencia);

CREATE TABLE IF NOT EXISTS srag.noticia (
    id              bigserial PRIMARY KEY,
    run_id          text NOT NULL,
    url             text NOT NULL,
    titulo          text NOT NULL,
    veiculo         text,
    publicado_em    timestamptz,
    coletado_em     timestamptz NOT NULL DEFAULT now(),
    texto           text,
    aceita          boolean NOT NULL DEFAULT true,
    motivo_recusa   text
);

CREATE INDEX IF NOT EXISTS ix_noticia_run ON srag.noticia (run_id);

CREATE TABLE IF NOT EXISTS srag.noticia_trecho (
    id          bigserial PRIMARY KEY,
    noticia_id  bigint NOT NULL REFERENCES srag.noticia (id) ON DELETE CASCADE,
    run_id      text NOT NULL,
    ordem       smallint NOT NULL,
    texto       text NOT NULL,
    embedding   vector(768)
);

CREATE INDEX IF NOT EXISTS ix_trecho_run ON srag.noticia_trecho (run_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srag_leitura') THEN
        GRANT USAGE ON SCHEMA srag TO srag_leitura;
        GRANT SELECT ON ALL TABLES IN SCHEMA srag TO srag_leitura;
        ALTER DEFAULT PRIVILEGES IN SCHEMA srag GRANT SELECT ON TABLES TO srag_leitura;
    END IF;
END
$$;
