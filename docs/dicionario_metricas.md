# Dicionário de métricas

Cada indicador do relatório está definido aqui com numerador, denominador, janela e limitação.
O SQL correspondente vive em [`src/srag/metricas/consultas.py`](../src/srag/metricas/consultas.py)
e é reproduzido no apêndice de rastreabilidade de todo relatório gerado.

## Convenções que valem para todos os indicadores

**Data de evento.** A série temporal é montada pela **data de início dos sintomas**
(`DT_SIN_PRI`), não pela data de notificação. A data de notificação depende do ritmo do
serviço de vigilância; a de sintomas é a que aproxima o momento em que a pessoa adoeceu.

**Data de referência.** Por padrão é `max(dt_sintomas) - 5 dias`. O desconto existe porque o
SIVEP-Gripe é preenchido com atraso: sem ele, os dias mais recentes apareceriam artificialmente
baixos e a tendência seria lida como queda. O valor é configurável em
`SRAG_ATRASO_NOTIFICACAO_DIAS`.

**Campo em branco nunca vira "Não".** Os códigos do dicionário do SIVEP (`1` = Sim, `2` = Não,
`9` = Ignorado) são traduzidos literalmente, e vazio ou código desconhecido vira `Ignorado`.
Registro ignorado fica **fora do denominador** e é reportado na coluna "Sem informação" de cada
indicador. Tratar em branco como negativa infla o denominador e derruba artificialmente todas
as taxas.

**Supressão de recortes pequenos.** Quebras (por faixa etária, por exemplo) com menos de
`SRAG_K_ANONIMATO` registros — 5 por padrão — não aparecem no relatório. Percentual sobre três
pessoas não informa nada epidemiologicamente e abre espaço para reidentificação quando cruzado
com UF e faixa etária.

---

## 1. Taxa de aumento de casos

| | |
| --- | --- |
| **Fórmula** | `(casos no período atual ÷ casos no período anterior − 1) × 100` |
| **Numerador** | casos com `dt_sintomas` nos últimos *N* dias até a data de referência |
| **Denominador** | casos com `dt_sintomas` nos *N* dias imediatamente anteriores |
| **Unidade** | variação percentual (pode ser negativa) |
| **Indisponível quando** | não há caso no período anterior (divisão por zero) |

Mede aceleração, não volume: dois períodos consecutivos de mesmo tamanho são comparados um com
o outro.

**Limitações.** O atraso de notificação afeta desigualmente os dois períodos — o mais recente
está sempre mais incompleto —, o que enviesa a taxa para baixo. O desconto de cinco dias na
data de referência reduz o efeito, mas não o elimina. Para uma janela de 30 dias, a comparação
também absorve efeito de calendário (feriados, finais de semana) sem ajuste.

## 2. Taxa de mortalidade

| | |
| --- | --- |
| **Fórmula** | `óbitos por SRAG ÷ casos encerrados × 100` |
| **Numerador** | `EVOLUCAO = 'Óbito'` |
| **Denominador** | `EVOLUCAO ∈ {'Cura', 'Óbito', 'Óbito por outras causas'}` |
| **Fora do cálculo** | `EVOLUCAO = 'Ignorado'` (caso ainda em aberto), reportado à parte |

É letalidade entre casos **hospitalizados e notificados**, não mortalidade populacional. Óbito
por outras causas entra no denominador (o caso está encerrado) mas não no numerador, e é
mostrado como quebra separada.

**Limitações.** Casos recentes ainda não têm desfecho registrado, então a taxa dos últimos dias
tende a ser subestimada — é o viés clássico de censura à direita. O relatório informa quantos
casos da janela estão sem desfecho, justamente para dimensionar esse efeito. Como o denominador
são casos graves o suficiente para virar notificação de SRAG, o valor é muito maior do que a
letalidade da infecção na população.

## 3. Taxa de ocupação de UTI

| | |
| --- | --- |
| **Fórmula** | `internações com passagem por UTI ÷ internações com o campo preenchido × 100` |
| **Numerador** | `UTI = 'Sim'` |
| **Denominador** | `UTI ∈ {'Sim', 'Não'}` |
| **Complemento** | permanência média em UTI, a partir de `DT_ENTUTI` e `DT_SAIDUTI` |

**Limitação mais importante deste relatório.** O SIVEP-Gripe não informa leitos disponíveis nem
leitos ocupados. Isto **não é taxa de ocupação de leitos de UTI**: é a proporção de internações
por SRAG que passaram pela UTI. Serve como indicador de gravidade dos casos, não de capacidade
instalada da rede.

Medir ocupação real exigiria cruzar com o CNES (leitos habilitados) e com dados de ocupação
hospitalar, que não estão nesta base. A permanência média em UTI é oferecida como aproximação
de pressão assistencial: quanto mais longa, mais tempo cada caso grave mantém um leito ocupado.

Dias de UTI negativos (saída antes da entrada) ou maiores que 365 são descartados como erro de
preenchimento.

## 4. Taxa de vacinação contra covid-19

| | |
| --- | --- |
| **Fórmula** | `casos que declararam vacinação ÷ casos com o campo preenchido × 100` |
| **Numerador** | `VACINA_COV = 'Sim'` |
| **Denominador** | `VACINA_COV ∈ {'Sim', 'Não'}` |
| **Quebra** | por faixa etária, com supressão de faixas com menos de 5 registros |

**Limitação mais importante desta métrica.** É cobertura vacinal **entre os casos notificados de
SRAG**, não cobertura da população. A base só enxerga quem adoeceu o suficiente para ser
notificado, então ela não responde "quantos brasileiros estão vacinados" — responde "qual o
perfil vacinal de quem está internando".

Isso ainda é útil: a quebra por faixa etária permite comparar o perfil vacinal entre grupos de
casos graves. Mas para cobertura populacional é preciso outra fonte (as bases de campanha de
vacinação do Ministério da Saúde). O diretório `data/referencia/` está reservado para plugar
cobertura oficial por UF, com citação de fonte, caso a PoC evolua.

O campo é autodeclarado na ficha de notificação e tem proporção alta de `Ignorado`, que fica
fora do denominador e é reportada.

---

## Gráficos

| Gráfico | Definição |
| --- | --- |
| Casos diários, últimos 30 dias | contagem por `dt_sintomas`, dias sem notificação preenchidos com zero, mais média móvel de 7 dias |
| Casos mensais, últimos 12 meses | contagem por `date_trunc('month', dt_sintomas)`, do mês da data de referência para trás |

O último mês da série mensal quase sempre está incompleto, já que a janela termina na data de
referência. A barra correspondente é desenhada em tom claro e identificada na legenda, para não
ser lida como despencada.

## Como conferir qualquer número

O endpoint `GET /api/metricas` devolve o painel inteiro em JSON — valor, numerador,
denominador, ignorados e janela de cada indicador — sem passar pelo modelo de linguagem. É o
caminho mais direto para verificar se um número do relatório corresponde ao dado.
