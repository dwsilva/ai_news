-- Executado uma unica vez, na criacao do volume do Postgres.
CREATE EXTENSION IF NOT EXISTS vector;

-- Papel usado pelas ferramentas do agente. Nao recebe INSERT/UPDATE/DELETE em lugar nenhum:
-- se algum dia alguem trocar as consultas parametrizadas por SQL gerado pelo modelo, o pior
-- caso continua sendo uma leitura.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srag_leitura') THEN
        CREATE ROLE srag_leitura LOGIN PASSWORD 'leitura';
    END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM srag_leitura;
