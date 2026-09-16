# Configuração

Toda a configuração passa por variável de ambiente, lida por `src/srag/config.py`. Quase tudo
tem default no código e já vem pronto do `docker-compose.yml` — na prática, só a chave do
Gemini precisa ser definida.

## O mínimo para rodar

Um arquivo `.env` na raiz, com uma linha:

```
GOOGLE_API_KEY=sua-chave-aqui
```

Sem ele o sistema sobe do mesmo jeito. O relatório sai com os indicadores, os gráficos e o
apêndice de rastreabilidade; só a análise textual é omitida, porque ela é a única parte que
depende do modelo. `GET /health` informa em que modo o serviço está:

```json
{"status": "degradado", "banco": "ok",
 "modelo": "sem GOOGLE_API_KEY: relatorio sai so com os indicadores", "internacoes": 3402357}
```

## Um aviso sobre fixar nome de modelo

Não coloque `SRAG_MODELO_LLM` nem `SRAG_MODELO_EMBEDDING` no `.env` sem necessidade.

O Google aposenta modelo sem aviso, e um nome fixo no `.env` vence o default do código — que é
atualizado junto com o resto do projeto. Foi exatamente assim que quebrou aqui uma vez: o
`.env` apontava para `models/text-embedding-004`, o modelo saiu do ar, e a API passou a
responder `404 NOT_FOUND` na indexação enquanto o código já tinha o nome novo.

Se aparecer 404 em embedding ou em geração, apague essas linhas do `.env` antes de procurar o
problema em qualquer outro lugar.

## Todas as variáveis

### Modelo

| Variável | Default | Para quê |
| --- | --- | --- |
| `GOOGLE_API_KEY` | — | Chave do Gemini. Sem ela, o relatório sai sem a análise textual |
| `SRAG_MODELO_LLM` | `gemini-3.8-flash` | Modelo que planeja as buscas e redige |
| `SRAG_MODELO_EMBEDDING` | `models/gemini-embedding-001` | Modelo dos embeddings das notícias |
| `SRAG_DIMENSOES_EMBEDDING` | `768` | Dimensões pedidas ao modelo. Precisa casar com a coluna `vector(n)` do schema |
| `SRAG_TEMPERATURA_LLM` | `0.2` | Baixa de propósito: o texto descreve dado, não inventa |

### Guardrail de custo

| Variável | Default | Para quê |
| --- | --- | --- |
| `SRAG_MAX_CHAMADAS_LLM` | `12` | Teto de chamadas ao modelo por execução |
| `SRAG_MAX_TOKENS_EXECUCAO` | `120000` | Teto de tokens por execução |

Estourar qualquer um dos dois interrompe o fluxo e fica registrado na trilha de auditoria.

### Guardrail de banco

| Variável | Default | Para quê |
| --- | --- | --- |
| `SRAG_DATABASE_URL` | — | Conexão de escrita. O compose já define |
| `SRAG_DATABASE_URL_LEITURA` | — | Conexão do papel `srag_leitura`, usada pelas ferramentas do agente. O compose já define |
| `SRAG_STATEMENT_TIMEOUT_MS` | `15000` | Timeout das consultas do agente |
| `SRAG_STATEMENT_TIMEOUT_CARGA_MS` | `600000` | Timeout da ingestão |

São dois timeouts porque são dois problemas diferentes. O curto protege o agente de uma
consulta que degenerou. A carga move mais de um milhão de linhas de uma vez — com o limite do
agente, a ingestão do ano de pico da covid não termina.

### Coleta de notícias

| Variável | Default | Para quê |
| --- | --- | --- |
| `SRAG_NOTICIAS_MAX_ARTIGOS` | `15` | Máximo de matérias por execução |
| `SRAG_NOTICIAS_JANELA_DIAS` | `30` | Só entram matérias publicadas nessa janela |

### Metodologia

| Variável | Default | Para quê |
| --- | --- | --- |
| `SRAG_ATRASO_NOTIFICACAO_DIAS` | `5` | Dias descartados no fim da série, para não ler atraso de digitação como queda de casos |
| `SRAG_K_ANONIMATO` | `5` | Recortes com menos registros que isso não aparecem no relatório |

Os dois estão discutidos em [`decisoes.md`](decisoes.md) e em
[`dicionario_metricas.md`](dicionario_metricas.md). Mexer neles muda o que o relatório diz,
não só como ele roda.

### Caminhos

| Variável | Default | Para quê |
| --- | --- | --- |
| `SRAG_DIR_DADOS` | `data/` | Onde o CSV bruto é baixado |
| `SRAG_DIR_RELATORIOS` | `reports/` | Onde cada execução grava Markdown, HTML, PDF e gráficos |
| `SRAG_DIR_LOGS` | `logs/` | Onde fica o espelho da auditoria em JSONL |

No compose os três são volumes, então o que a API gerar aparece direto na sua cópia do
repositório.
