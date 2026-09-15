# Decisões de arquitetura

Registro curto das escolhas que não são óbvias no código, com o motivo e o que foi
descartado. Ordenado pelo momento em que a decisão apareceu.

---

## 1. PostgreSQL com pgvector, em vez de banco relacional + banco vetorial

O projeto precisa de três coisas: microdados para agregar, embeddings para buscar por
similaridade e trilha de auditoria. Um Postgres com a extensão `vector` resolve as três.

Considerei Chroma ou FAISS para a parte vetorial. Descartei porque um segundo serviço para
guardar algumas centenas de trechos por execução é custo de operação sem contrapartida, e
porque manter o índice no mesmo banco permite juntar, numa consulta só, o trecho recuperado
com a matéria de origem e com o `run_id` da execução — que é exatamente o que a auditoria
precisa mostrar.

DuckDB seria mais rápido nas agregações, mas o arquivo único complica o acesso concorrente
da API e não tem um equivalente maduro de pgvector.

## 2. O modelo de linguagem não calcula número e não escreve SQL

Esta é a decisão central. As quatro métricas saem de funções Python com SQL parametrizado
escrito à mão (`src/srag/metricas/consultas.py`). O modelo recebe o resultado pronto.

Um agente com text-to-SQL seria mais flexível e demonstraria mais "autonomia", mas em
vigilância epidemiológica a flexibilidade não é o requisito: o requisito é que o mesmo pedido
produza o mesmo número duas vezes e que qualquer número seja conferível fora do agente. Com
consultas fixas, dá para publicar o SQL no apêndice do relatório e alguém reproduzir na mão.

Efeito colateral bem-vindo: injeção de SQL sai do mapa de risco, e o pior caso de uma injeção
de prompt bem-sucedida deixa de ser "o agente executou um comando" e passa a ser "o agente
escreveu uma frase errada" — que a verificação de saída pega.

## 3. Grafo determinístico com um ponto de decisão do modelo

O LangGraph aqui não é um loop ReAct. A ordem dos nós é fixa e o único desvio de fluxo é o
retorno de `verificar_saida` para `redigir_analise`.

O modelo decide uma coisa de verdade: quais perguntas usar para recuperar notícias de cada
indicador (nó `planejar_buscas`). É onde a decisão dele agrega — ele sabe que "taxa de
ocupação de UTI" pede notícia sobre pressão hospitalar — e onde o erro é barato, porque existe
um conjunto de perguntas padrão como fallback.

## 4. Índice vetorial escrito à mão, em vez de um vector store de biblioteca

São duas consultas SQL (`src/srag/noticias/indexacao.py`). Um `PGVector` de biblioteca traria
tabelas com esquema próprio e metadados em JSON opaco; com tabela própria, a auditoria mostra
qual trecho de qual matéria entrou no contexto de qual indicador.

A busca é exaustiva por distância de cosseno, sem índice HNSW. São dezenas de matérias por
execução: um índice aproximado aqui só adicionaria configuração para economizar milissegundos.

## 5. A janela de análise termina antes do último dia da base

O SIVEP-Gripe é alimentado com atraso de digitação. Os últimos dias da série sempre aparecem
com menos casos do que realmente houve, e uma "taxa de aumento" calculada até o último
registro leria esse atraso como queda.

Por isso a data de referência padrão é `max(dt_sintomas) - 5 dias`, configurável em
`SRAG_ATRASO_NOTIFICACAO_DIAS`. É uma aproximação grosseira — o ideal seria estimar a curva de
atraso por UF (*nowcasting*, como o InfoGripe faz) — mas cinco dias já evita o erro de leitura
mais comum, e a escolha fica declarada no relatório em vez de escondida.

## 6. Duas fontes de notícia, ambas por RSS público

O Bing News RSS entrega o endereço original da matéria no parâmetro `url` do link, o que
permite extrair o texto integral. O Google News tem cobertura muito melhor da imprensa
regional brasileira, mas o link aponta para o agregador, e o endereço real só é alcançável por
um endpoint interno não documentado do Google.

Optei por não usar esse endpoint. As matérias do Google News entram com título, veículo e
data; o campo `texto_completo` registra qual dos dois casos aconteceu, e o relatório cita a
fonte pelo que de fato foi lido. A alternativa seria uma API paga de busca, que criaria uma
barreira para quem for rodar o projeto.

## 7. Minimização na entrada, não mascaramento na saída

Os campos sensíveis não são filtrados na hora de exibir: eles nunca entram no banco. A leitura
do CSV já descarta tudo que não está em `COLUNAS_ORIGEM`, a idade vira faixa etária e a
geografia é truncada em UF antes do `COPY`.

O custo é perder análises futuras por município. A contrapartida é que não existe caminho de
código — nem bug — capaz de vazar o que não foi armazenado.

## 8. Verificação programática da saída, em vez de confiar na instrução do prompt

O prompt manda o modelo usar apenas os números fornecidos. Isso não é garantia. Então todo
percentual e toda contagem acima de mil que aparecem no texto são comparados com o conjunto de
valores que as consultas produziram, e toda citação `[n]` precisa resolver para uma matéria
efetivamente recuperada.

Só percentuais e contagens grandes são verificados. Conferir todo inteiro geraria falso
positivo em prosa comum ("as quatro métricas", "os últimos 30 dias") sem ganho de segurança —
é uma troca consciente de recall por precisão, documentada em `guardrails/saida.py`.

Quando a verificação reprova duas vezes, o relatório sai sem a análise textual e com a ressalva
explícita. Relatório com um buraco declarado é melhor do que relatório com número não
rastreável.

## 9. Markdown como formato canônico do relatório

O relatório é montado em Markdown e derivado dali para HTML (com os gráficos em base64) e PDF.
Markdown é legível em `git diff`, o que torna fácil comparar duas execuções; o HTML é
autocontido, então serve tanto para a interface quanto de entrada para o WeasyPrint sem
depender de caminho relativo.

## 10. Testes de métrica contra um Postgres de verdade

`tests/conftest.py` cria um banco descartável e aplica o schema. Metade do que essas métricas
fazem é comportamento do Postgres — `count(*) FILTER`, `date_trunc`, o cast explícito dos
parâmetros nulos. Rodar contra SQLite ou contra mock testaria outra coisa.

O preço é precisar do container do banco para rodar a suíte. Para uma PoC que já roda inteira
em Docker, achei um preço justo.
