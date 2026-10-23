# GreenWay Vision — Plano da V2 (Backend)

Plano de desenvolvimento da V2 do backend, na ordem em que faz sentido executar.
Foi escrito para ser lido e executado aos poucos: cada item explica **o que é**,
**por que existe**, **como fazer** e **quando está pronto**.

O dispositivo de borda (câmera embarcada) tem seu próprio documento:
[dispositivo-de-borda.md](../dispositivo-de-borda.md).

---

## 1. Objetivo da V2

A V1 provou o fluxo completo: upload → análise por frame → resultado → mapa. A V2
torna esse fluxo **confiável, correto nos dados e útil para decidir**:

| Tema | V1 (hoje) | V2 |
|---|---|---|
| Datas | saem sem fuso; o front mostra 3 h erradas | sempre UTC com `Z` |
| Falhas | `FAILED` sem explicação | `FAILED` com motivo e log |
| Dados | commits por frame; falha no meio deixa lixo | gravação atômica (tudo ou nada) |
| Upload | a tela trava até a análise terminar | resposta imediata + acompanhamento |
| Modelo | 88,5 % no geral, mas MEDIUM quase nunca é reconhecida | métricas por classe e MEDIUM melhor |
| Decisão | o front só conta inspeções | Agenda e análise de dados (fila de ação, tendência) |

## 2. Como o plano está organizado

Quatro partes, por contexto. A **ordem dos itens é a ordem de execução**, porque
cada item só depende dos anteriores:

| Parte | Contexto | Itens |
|---|---|---|
| A | Base: banco, datas, erros, configuração | 1 a 4 |
| B | Confiabilidade: testes, gravação atômica, arquivos, assíncrono | 5 a 8 |
| C | Modelo de visão | 9 |
| D | Agenda e análise de dados | 10 a 15 |
| E | Condicional (só se surgir necessidade) | PostgreSQL, segurança, borda |

A Parte C pode andar em paralelo com B e D: não depende delas (só a previsão do
item 13 usa o que ela produz).

## 3. Conceitos que aparecem no plano

Leia esta seção uma vez; os itens a usam sem repetir.

- **Esquema (schema) do banco:** a estrutura das tabelas e colunas. Não confundir
  com *schema do Pydantic* (o formato do JSON da API).
- **Migração:** uma mudança versionada no esquema (ex.: "criar a coluna X").
- **Bloco:** pedaço de **0,5 km** de uma rodovia, em um sentido. Não existe no
  banco: é **derivado** do km estimado de cada frame. `block_index = floor(km * 2)`
  (bloco 0 = km 0,0 a 0,5; bloco 22 = km 11,0 a 11,5).
- **Leitura:** o resultado de uma inspeção para um bloco (média do verde + pior
  prioridade entre os frames que caíram nele).
- **Estado do bloco:** a leitura da inspeção mais recente que cobre o bloco.
- **`estimated_km`:** posição do frame obtida por **interpolação** entre o km
  inicial e o final informados no upload. É uma aproximação, não GPS; por isso
  todo valor por bloco também é aproximado.

## 4. Decisões de contrato

Valem para todas as partes; já foram combinadas com o frontend.

| Tema | Decisão |
|---|---|
| Instantes (data + hora) | ISO 8601 em UTC com `Z` (ex.: `2026-10-21T14:00:03Z`) |
| Datas de agenda | `YYYY-MM-DD`, fuso `America/Sao_Paulo`; "hoje" é calculado nesse fuso |
| Intervalos de km | semiabertos: `[km_start, km_end)` — o fim não pertence ao intervalo |
| Chave do bloco | `block_index` inteiro, enviado pronto pelo backend |
| Enums | `status`, `priority`, `direction`, `type` com valores fixos, tipados no OpenAPI |
| Erros | `{"detail": "texto"}` nos 4xx e `{"detail": [{loc, msg}, ...]}` no 422 |
| `direction = null` na agenda | significa "os dois sentidos" |
| Duplicata de evento | 409 só se mesmo tipo + data + sentido + km sobreposto; `?force=true` força |
| Janela de `GET /schedule` | `from` e `to` obrigatórios, máximo 93 dias |
| Tipos do frontend | gerados do `/openapi.json` com `openapi-typescript` |
| CORS | `http://localhost:5173`, com PATCH e DELETE |

---

# PARTE A — Base: banco, datas, erros e configuração

Quatro itens pequenos que corrigem o que o frontend já sofre hoje e preparam todo o resto.

## Item 1 — Migrações do banco com Alembic

**O que é.** Alembic é uma ferramenta que guarda o **histórico de mudanças na estrutura
das tabelas** em arquivos versionados no git (`alembic/versions/`) e sabe aplicá-los em
qualquer banco. **Não substitui o banco**: o SQLite e o `greenway.db` continuam os mesmos.

**O que ele resolve e o que não resolve.** Não corrige nenhum bug da aplicação. Resolve
um problema de processo: o `create_all()` só cria tabelas que **não existem**, então uma
coluna nova em tabela existente (como `failure_reason`) exigiria um `ALTER TABLE` feito
à mão em cada banco. Com um banco só, isso é tolerável; com um segundo ambiente (outra
pessoa rodando o backend, um banco novo, o PostgreSQL) cada um repetiria a lista de
`ALTER` na ordem certa. Com o Alembic, o mesmo comando chega ao mesmo esquema.

**Como funciona.**
```text
você muda o model (app/models/inspection.py)
        ↓
alembic revision --autogenerate -m "descrição"
        → compara os models com o banco e GERA um arquivo em alembic/versions/ (revise-o)
        ↓
alembic upgrade head
        → aplica as migrações pendentes no banco; uma tabela interna (alembic_version)
          guarda qual foi a última, então rodar de novo não repete nada
```
O Alembic **não é automático**: nada acontece ao subir o uvicorn. Se você esquecer o
`upgrade head`, a API sobe, mas falha ao usar a coluna nova ("no such column").

**Como está configurado.**
- `alembic/env.py` aponta para os models (`Base.metadata`) e para a **mesma URL de banco**
  da aplicação. `alembic -x url=sqlite:///outro.db upgrade head` aplica em outro arquivo.
- `0001_esquema_inicial` descreve o esquema atual completo (5 tabelas, incluindo
  `failure_reason`). No banco que já existia, ela **não foi executada**: foi só marcada
  como aplicada (`alembic stamp head`), então nenhum dado mudou. Um banco novo recebe o
  esquema inteiro com um único `alembic upgrade head`.
- O `main.py` **não cria mais tabelas** ao subir. Antes de rodar a API em um banco novo:
  `alembic upgrade head`, e só depois o seed.
- O modo `batch` está ligado (`render_as_batch`): o SQLite não altera nem remove coluna
  diretamente, e o Alembic recria a tabela por baixo quando for preciso. Adicionar coluna
  que aceita `NULL` é simples.

**Colunas novas previstas neste plano** (cada uma vira uma migração):
- confiança do modelo por frame, em `frame_analyses` (item 9);
- posição real por frame, em `frame_analyses` (dispositivo de borda).

**Pronto quando:** `alembic upgrade head` num banco vazio cria o esquema completo;
`alembic check` no `greenway.db` atual não acusa diferenças com os models; e as
inspeções já gravadas continuam lá.

## Item 2 — Datas sempre em UTC com `Z`

**O problema.** A API devolve `2026-08-21T04:18:16.408486`, sem indicar o fuso. O
navegador interpreta como horário **local**, e as horas do Histórico aparecem 3 h
erradas. A causa: o SQLite não guarda fuso, então o Python devolve datas "ingênuas"
(sem `tzinfo`), embora o valor gravado seja UTC.

**Como corrigir (um único ponto).** Nos schemas de resposta, usar um tipo de data que
**trata data ingênua como UTC** e serializa como ISO com `Z`. Os modelos não mudam e
não há migração.

**Cuidado.** Isso vale para instantes (`created_at`, `analyzed_at`, `uploaded_at`).
As datas da Agenda (`YYYY-MM-DD`) são outra coisa e seguem o fuso de São Paulo.

**Pronto quando:** toda data de `GET /inspections` termina em `Z` e a hora do Histórico
bate com a hora real do upload.

## Item 3 — Motivo da falha, logs e enums tipados

**O que muda.**
1. **`failure_reason`** (coluna nova em `Inspection`, texto curto, opcional). Exige
   migração (item 1).
2. **Capturar exceções específicas** em `create_inspection`
   (`app/services/inspection_service.py`), em vez do `except Exception` atual: erro de
   vídeo/imagem inválida (`ValueError`), de leitura/escrita (`OSError`) e do OpenCV.
   Cada um grava um motivo claro e é registrado com `logging` (com a pilha completa no
   log, mas só a mensagem curta no banco).
3. **Enums tipados** nos schemas (`Literal`): `status` (`DONE`, `FAILED`; `PROCESSING`
   entra no item 8), `priority` (`LOW`, `MEDIUM`, `HIGH`) e `direction` (`CAPITAL`,
   `INTERIOR`). Sem isso o OpenAPI mostra `string` solto e o `openapi-typescript` gera
   um tipo genérico.
4. **Validar `direction` na entrada.** Hoje o `POST /inspections` aceita qualquer texto
   no campo `direction`. Deve aceitar só `CAPITAL` ou `INTERIOR` (422 nos demais).

**Por que o motivo importa.** Hoje um vídeo corrompido e um bug de código viram o mesmo
`FAILED` mudo, impossível de diferenciar ou depurar.

**Pronto quando:** enviar um arquivo inválido gera uma inspeção `FAILED` com motivo
legível; o log mostra a causa; o `/openapi.json` lista os valores permitidos.

## Item 4 — Configuração central, `/meta` e o `DELETE` com flag

**Configuração.** Hoje as constantes estão espalhadas (CORS no `main.py`, limites no
service, caminho do banco no `session.py`). A pasta `app/core/` existe e está vazia.
Criar `app/core/config.py` com:
- origens permitidas de CORS, fuso horário, tamanho do bloco (0,5 km);
- limites de upload;
- a flag que libera o `DELETE /inspections`.

Sem biblioteca nova: constantes Python lendo variáveis de ambiente com valor padrão
(`os.environ.get`). Uma biblioteca de configuração só se justificaria com muitas
variáveis.

**`GET /meta` (novo).** Devolve fuso, tamanho do bloco e se o reset administrativo está
liberado. O frontend usa isso para esconder o botão "Resetar análises".

**`DELETE /inspections` atrás da flag.** Hoje apaga todas as análises sem proteção.
Com a flag desligada, responde **403** com uma mensagem explicativa. Em desenvolvimento
fica ligada.

**Pronto quando:** com a flag desligada o `DELETE` retorna 403 e o `/meta` informa isso.

---

# PARTE B — Confiabilidade

O fluxo já funciona; aqui garantimos que continua funcionando quando algo falha e
quando o uso cresce.

## Item 5 — Testes automatizados e carregamento preguiçoso do modelo

**Por que agora.** Os itens 6 e 8 mexem em como os dados são gravados. Sem testes, não
dá para saber se algo quebrou. Hoje `tests/` só tem experimentos soltos.

**O bloqueio.** `app/vision/engine.py` carrega o classificador (`joblib`) e
`feature_extractor_cnn.py` carrega a MobileNet **no momento do import**. Qualquer teste
que importe o service paga esse custo (segundos, mais os pesos da MobileNet em disco).
O mesmo custo atrasa a subida da API.

**Como fazer.**
1. **Carregamento preguiçoso:** carregar o modelo na primeira chamada, uma única vez
   (função com `functools.lru_cache`), não no import.
2. **Proteger o `frame_extractor`:** hoje divide por zero se o vídeo tiver fps ≤ 0 e
   se `fps * intervalo < 1`. Tratar como erro claro (`ValueError`).
3. **`pytest`** (e `httpx`, exigido pelo `TestClient` do FastAPI) no `requirements.txt`.
4. **Banco de teste:** um SQLite temporário por teste, trocando `get_db` pelo mecanismo
   de `dependency_overrides` do FastAPI.
5. **Vision Engine falso:** nos testes da API, substituir `vision_engine.analyze` por
   uma função que devolve um `AnalysisResult` fixo (rápido, sem PyTorch).

**O que testar (só a lógica do projeto, não o framework):**
- upload válido, tipo inválido (400), arquivo grande demais (413);
- falha do engine vira `FAILED` com motivo;
- interpolação de km, incluindo que o último frame não "vaza" para o bloco seguinte;
- agregação do pior caso entre frames;
- `direction` inválido (422).

**Pronto quando:** `pytest` roda em segundos, sem baixar nem carregar modelo, e cobre a
lista acima.

**Como ficou.** `pytest` com 41 testes em menos de 1 segundo, em `tests/`: banco SQLite em
memória por teste (`conftest.py`), pastas de storage temporárias e um Vision Engine falso. O
modelo agora é carregado na primeira classificação (`functools.lru_cache`), e o `torch` só é
importado quando um frame vai ser classificado (um teste garante que importar o engine não
carrega o `torch`). O `frame_extractor` rejeita fps inválido com `ValueError`. Consequência:
o **primeiro** frame classificado depois de subir a API demora alguns segundos a mais (carrega
a rede); como a análise é em segundo plano (item 8), o usuário não espera por isso.

## Item 6 — Gravação atômica da inspeção

**O problema.** Cada `repository.create()` faz `commit()` por conta própria. Uma
inspeção grava `Video`, `Inspection` e **um commit por frame**: um vídeo de 60 s faz
cerca de 60 commits. Duas consequências:
- se o processo cair no meio, fica uma `Inspection` `DONE` com **frames faltando**,
  e qualquer leitura (mapa, análise de dados) trataria isso como dado válido;
- cada commit no SQLite grava em disco, então é lento.

**Conceito: unidade de trabalho.** Uma operação do negócio ("registrar uma inspeção")
deve ser **tudo ou nada**. Na `Session` do SQLAlchemy:
```text
db.add(obj)     → registra o objeto na Session (ainda não está no banco)
db.flush()      → envia o SQL ao banco, dentro da transação, sem confirmar
db.commit()     → confirma tudo de uma vez
db.rollback()   → desfaz tudo desde o último commit
```

**Como fazer.**
1. Repositories fazem `add` e, se precisarem do `id`, `flush` — **sem `commit`**.
2. O service faz **um único `commit`** no fim do caso de uso e `rollback` se algo
   falhar no meio.
3. Os `FrameAnalysis` entram em lote (`add_all`).
4. Decidir e documentar o que fazer com o arquivo já salvo em disco quando a gravação
   falha: apagar ou manter o `Video` com a `Inspection` `FAILED`.

**Pronto quando:** uma falha simulada no meio da gravação não deixa `Inspection` sem
frames, e uma requisição faz exatamente 1 commit (verificado em teste).

**Como ficou.** Os repositories só fazem `add`/`flush` (regra em `app/repositories/__init__.py`).
O upload tem dois passos (item 8): o passo 1 grava `Video` + `Inspection` num commit só; o
passo 2 grava a `Inspection` final e **todos** os `FrameAnalysis` em um único commit. As rotas
`/roads` e `/segments`, que não passam por service, fazem o próprio `commit`.
Decisão sobre o arquivo quando algo falha: se a gravação do passo 1 falha, o arquivo salvo é
apagado; se a análise falha (`FAILED`), o **original é mantido** (a linha do `Video` ainda o
referencia) e só as imagens parciais dos frames são apagadas.

## Item 7 — Controle do espaço em `storage/`

**O problema.** Cada frame analisado é salvo como JPEG em resolução original
(`storage/frames/{video_id}/{i}.jpg`), e os vídeos originais nunca são apagados. Numa
rodovia de 150 km o disco enche.

**Como fazer.**
1. Antes de implementar, **medir**: tamanho médio de `storage/` por inspeção.
2. Salvar a imagem de **exibição** reduzida (largura máxima de 640 px, qualidade ~80).
   O frame em resolução cheia só vai para o modelo e é descartado.
3. Política de retenção configurável (por exemplo, apagar o vídeo original após N dias
   e manter os frames reduzidos).
4. Remover arquivos órfãos quando a análise falha ou a gravação é desfeita (depende
   do item 6).

**Pronto quando:** a medição antes/depois mostra a redução, e inspeções que falham não
deixam arquivos soltos.

**Como ficou (medido).** Frames de exibição reduzidos a 640 px de largura, JPEG qualidade 80.
Aplicado a frames reais já guardados: 2560x1440 de 515 KB para 33 KB (94 % menor) e uma foto
4032x3024 de 2.855 KB para 25 KB (99 % menor). Antes, o `storage/` tinha ~540 KB por frame.
Retenção: `VIDEO_RETENTION_DAYS` (desligada por padrão) apaga só os **originais** mais antigos,
verificando que o caminho está dentro de `storage/`; as linhas do banco e os frames reduzidos
ficam. Arquivos órfãos de gravações desfeitas ou análises falhas são removidos.

## Item 8 — Análise assíncrona do upload

**O problema.** `POST /inspections` só responde depois de extrair os frames, rodar a
MobileNet em CPU e classificar tudo. Vídeos de até 100 MB passam de timeouts do
navegador e travam a tela de upload.

**A ideia.** Responder rápido e processar depois, usando o **`BackgroundTasks` do
FastAPI** (já incluso, sem fila nem Redis):
```text
POST /inspections
   ├─ salva o arquivo, cria Video + Inspection(status = PROCESSING)
   ├─ agenda a análise em segundo plano
   └─ responde 202 imediatamente

(em segundo plano) analisa → atualiza a Inspection para DONE ou FAILED

Frontend: consulta GET /inspections/{id} a cada poucos segundos até sair de PROCESSING
```

**Pontos que merecem atenção.**
- **A tarefa em segundo plano abre a própria `Session`.** A `Session` da requisição é
  fechada quando a resposta sai; a tarefa não pode reutilizá-la.
- **Reinício do processo.** Uma inspeção em `PROCESSING` cuja tarefa morreu junto com o
  servidor ficaria presa para sempre. Ao subir a API, toda `PROCESSING` vira `FAILED`
  com um motivo ("interrompida por reinício").
- **Contrato novo (combinar com o front antes):** o enum `status` ganha `PROCESSING`,
  o `POST` responde 202 com a inspeção ainda parcial, e as telas que listam inspeções
  precisam tratar as em processamento do mesmo jeito que tratam `FAILED`.
- **Depende dos itens 3 e 6:** o motivo da falha precisa existir e a gravação final
  precisa ser atômica.

**Quando não fazer.** Fila de verdade (Celery, Redis) só com muitos usuários ao mesmo
tempo, o que não é o caso.

**Pronto quando:** o `POST` responde em menos de 1 s, a inspeção passa de `PROCESSING`
para `DONE` ou `FAILED`, e reiniciar a API não deixa nenhuma `PROCESSING` órfã.

**Como ficou.** `POST /inspections` responde **202** com a inspeção em `PROCESSING`
(`accept_inspection`) e agenda `process_inspection` com `BackgroundTasks`. A tarefa abre a
própria `Session`. Na subida da API, `PROCESSING` órfão vira `FAILED`. Duas decisões:
- um `AnalysisError` (mídia inválida) vira `FAILED` com o motivo; qualquer **outro** erro, em
  segundo plano, também vira `FAILED`, mas com motivo genérico e o detalhe só no log — não há
  cliente a quem devolver um erro 500, e uma exceção solta deixaria a inspeção em `PROCESSING`
  para sempre (é a única captura geral do projeto, e está comentada no código);
- um arquivo corrompido, que antes voltava `FAILED` na hora, agora volta 202 e vira `FAILED`
  segundos depois: o frontend precisa acompanhar.

---

# PARTE C — Modelo de visão

## Item 9 — Modelo v2: reconhecer melhor a classe MEDIUM

**O que a medição mostra** (130 imagens de teste, `data/mapillary/model/test_predictions.csv`):

| Classe real | Amostras | Acertos |
|---|---|---|
| HIGH | 77 | 75 |
| LOW | 40 | 37 |
| MEDIUM | 13 | **3** (23 %) |

A acurácia geral é 88,5 %, mas ela **esconde** que a classe MEDIUM praticamente não é
reconhecida (9 das 13 viram HIGH). Há muito mais exemplos de HIGH do que de MEDIUM no
treino, e o modelo aprende o que domina. Na prática isso infla HIGH e polui a fila de
ação e as sugestões da Agenda.

**Regra do item:** cada mudança é um **experimento medido** (resultado antes e depois),
nunca um ajuste às cegas. Verifique antes se as imagens do dataset estão disponíveis
localmente.

**Experimentos, nesta ordem:**
1. **Métricas por classe** (precisão, recall, F1 e matriz de confusão) como saída
   padrão do treino, com **validação cruzada** em vez de um único corte treino/teste.
   Com 13 exemplos de MEDIUM, um único corte é estatisticamente fraco.
2. **Pesos por classe** (`class_weight="balanced"` no RandomForest): custa uma linha e
   faz erros em MEDIUM pesarem mais.
3. **Mais dados** de MEDIUM e LOW (rotular mais imagens do Mapillary e de
   `data/images-real-road/`). É o ganho mais provável.
4. **Confiança por frame** (`predict_proba`): guardar quanto o modelo "tem certeza".
   Exige coluna nova (migração, item 1) e permite ao front sinalizar baixa confiança.
5. **Agregação do vídeo.** Hoje vale o **pior caso**: um único frame HIGH define o
   vídeo inteiro. Testar alternativas, como HIGH só se pelo menos *k* frames ou uma
   fração dos frames forem HIGH, e comparar com rótulos de vídeo reais.
6. **Pré-filtro HSV.** Frames com menos de 5 % de verde (`PRE_FILTER_MIN_GREEN_PERCENT`)
   são marcados LOW sem passar pelo modelo. Esse corte nunca foi validado: medir quantos
   frames MEDIUM/HIGH reais ele descarta.
7. **Versionamento.** Gravar junto do `classifier.joblib` os metadados do treino
   (dataset, data, métricas); cada inspeção já guarda `model_version`.
8. **Avaliação em dados reais de câmera** (`data/images-real-road/`) para medir a
   diferença entre as imagens do Mapillary e a captura real.

**Pronto quando:** existe uma tabela antes/depois com as métricas por classe e o recall
de MEDIUM melhorou sem derrubar as outras classes.

---

# PARTE D — Agenda e análise de dados

Dá ao usuário o "como está a malha e o que eu faço agora?". É a parte maior e
depende do frontend para ser consumida; os itens seguem uma ordem em que cada um
usa o anterior.

## Item 10 — Agenda: cadastro e conclusão de eventos

**O que é.** Um evento de agenda é uma **inspeção** ou uma **roçada** planejada para
um trecho de rodovia em uma data.

**Modelo `ScheduleEvent`:** tipo (`INSPECTION`/`MOWING`), status, `road_id`,
`segment_id` (opcional), `direction`, `km_start`, `km_end`, `scheduled_date`, horários
opcionais, responsável (texto livre), observação, origem (`MANUAL`/`SUGGESTION`),
`completed_at`, `inspection_id`, `completion_source` (`MANUAL`/`AUTO`).
`is_overdue` não é gravado: é calculado na resposta (`PLANNED` com data anterior a hoje,
no fuso de São Paulo).

**Estados.**
```text
PLANNED → IN_PROGRESS → DONE
   qualquer um → CANCELED
```
`DONE` é imutável, **exceto** o concluído automaticamente (item 15), que pode ser
reaberto.

**Rotas.**

| Rota | Função |
|---|---|
| `GET /schedule?from=&to=&type=&status=&road_id=&direction=` | lista o período |
| `POST /schedule` | cria |
| `GET /schedule/{id}` | detalhe |
| `PATCH /schedule/{id}` | edição parcial |
| `DELETE /schedule/{id}` | remove |
| `POST /schedule/{id}/complete` | conclui (`completed_at`, `inspection_id`, `notes`) |
| `GET /schedule/summary` | números do topo da tela |

**Regras.**
- `PATCH` com `status=DONE` e `/complete` usam **a mesma função** do service:
  uma única regra de conclusão.
- Validação (422): `km_start < km_end`; o evento deve **tocar** algum segmento da
  rodovia (não precisa estar contido nele, porque os blocos das pontas passam do limite);
  `segment_id` pertence à rodovia; `end_time > start_time`; `inspection_id` existe e é da
  mesma rodovia.
- Duplicata (mesmo tipo, data, sentido e km sobreposto) → 409, `?force=true` força.
- **Armadilha do FastAPI:** `/schedule/summary` e `/schedule/suggestions` precisam ser
  declaradas **antes** de `/schedule/{id}`; senão "summary" é lido como um `id`.
- `summary` nasce com `planned_this_week`, `overdue`, `next_mowing`;
  `critical_unscheduled` entra no item 12.

**Pronto quando:** o calendário do front cria, edita, conclui e remove eventos, e as
validações acima retornam o erro esperado.

## Item 11 — Estado dos blocos: `GET /analytics/blocks`

**O que é.** O núcleo da Visão Geral: para cada bloco de 0,5 km de cada sentido, o que
sabemos agora. Todo o resto da Parte D consome isto.

**Como calcular.**
1. **Gerar os blocos** a partir dos `Segment`s. Blocos nunca inspecionados também
   aparecem (`priority = null`). Com os segmentos atuais (km 11–158 e 13–173) são cerca
   de 300 blocos por sentido.
2. **Leitura de uma inspeção num bloco:** média do `green_percent` dos frames que caíram
   nele + **pior** prioridade (coerente com o Vision Engine).
3. **Estado atual:** a leitura da inspeção **mais recente** que cobre o bloco.
   Inspeções `FAILED` e sem `direction` ficam de fora.
4. Acrescentar `last_mowed_at` (eventos `MOWING` concluídos que tocam o bloco) e
   `next_scheduled` (evento `PLANNED` que toca o bloco).

**Campos do `BlockState`:** `road_id`, `segment_id`, `direction`, `km_start`, `km_end`,
`block_index`, `priority`, `green_percent`, `last_inspected_at`, `last_mowed_at`,
`growth_per_day`, `predicted_critical_date`, `next_scheduled`, `readings_count`,
`last_inspection_id` e, com `?include=history`, `history[{date, green_percent}]`.

**Dois detalhes importantes.**
- A função de cálculo recebe uma data de referência (`as_of`), que o item 12 usa para
  comparar o estado atual com o de um período anterior.
- Começar simples: uma consulta e agregação em Python. Otimizar (SQL com janela,
  índices) só se a medição mostrar lentidão. O tráfego atual é pequeno (25 frames ≈ 4,6 KB).

**Pronto quando:** a resposta lista todos os blocos de uma rodovia, com os nunca
inspecionados como `priority = null`, e bate com o que o mapa já mostra.

## Item 12 — Visão geral e série temporal

- **`GET /analytics/overview`:** indicadores do topo da tela com comparação ao período
  anterior (chama o cálculo do item 11 duas vezes: `as_of = fim do período` e
  `as_of = fim do período anterior`).
  - `coverage_pct` = blocos com ao menos uma leitura no período ÷ total de blocos;
  - `stale_blocks` = blocos sem leitura há mais de N dias (N configurável);
  - `avg_days_since_inspection`, `blocks_by_priority`, `blocks_total` e o bloco `previous`.
- **`GET /analytics/timeseries?bucket=week`:** inspeções por semana, média de verde e
  contagem por criticidade.
- **`summary.critical_unscheduled`** passa a existir (blocos críticos sem evento
  planejado), pois agora há o estado dos blocos.

**Pronto quando:** o painel mostra os indicadores com setas ▲▼ coerentes com o período
anterior.

## Item 13 — Crescimento e previsão

**O que é.** Estimar em quantos dias um bloco chega ao nível crítico.

**Por que não é trivial.** `green_percent` e `priority` **não são ligados por uma
fórmula**: a prioridade vem do RandomForest sobre a imagem; o verde é só o pré-filtro
de cor. Então o "limite crítico" de verde precisa ser **calibrado com dados reais**.

**Como fazer.**
1. Script de análise sobre os `FrameAnalysis` existentes para calibrar
   `CRITICAL_GREEN_PERCENT` (por exemplo, a mediana do verde dos frames HIGH). Guardar
   o valor em config com a justificativa documentada.
2. **Regressão linear** (reta que melhor ajusta) de `green_percent` ao longo do tempo,
   usando só leituras **depois da última roçada**. Sem isso, a queda causada pela
   roçada daria crescimento negativo.
3. Exigir no mínimo 3 leituras e um intervalo mínimo de dias; caso contrário,
   `growth_per_day = null`.
4. `predicted_critical_date = hoje + (limite − verde atual) / crescimento`. Bloco que já
   está crítico não tem previsão (é o caso `CRITICAL_NOW`).

**Aviso para a interface:** é uma estimativa grosseira, baseada em poucos pontos de uma
medida ruidosa. Deve ser rotulada como estimativa.

**Pronto quando:** blocos com leituras suficientes mostram o crescimento por dia e a
data prevista; os demais mostram `null`.

## Item 14 — Sugestões

**O que é.** `GET /schedule/suggestions` devolve 3 a 5 cartões ("inspecionar este
trecho", "roçar este trecho"), cada um com um motivo curto em português.

**Cuidado central: agrupar.** Com cerca de 300 blocos por sentido e quase todos nunca
inspecionados, gerar uma sugestão por bloco criaria centenas de cartões. Por isso:
- **agrupar blocos contíguos** (mesma rodovia, sentido e motivo) em **uma sugestão com
  intervalo** `[km_start, km_end)`;
- **limitar** a quantidade devolvida (`limit`, padrão pequeno).

**Regras (valores fixos em config nesta versão).**
- *Inspeção:* sugerir quando o bloco passa do intervalo máximo sem inspeção — Alta
  7 dias, Média 15, Baixa 30. Bloco nunca inspecionado → `NEVER_INSPECTED`; vencido →
  `STALE_INSPECTION`.
- *Roçada:* prioridade Alta → próximo dia útil livre (`CRITICAL_NOW`); previsão que
  cruza o limite → data prevista menos uma antecedência (`PREDICTED_CRITICAL`).
- Nunca sugerir bloco que já tem evento `PLANNED`. Pular fins de semana (feriados ficam
  para depois).
- `urgency` de 0 a 100, para ordenar: fórmula simples e documentada (criticidade, dias
  sem inspeção, crescimento).

**Como funcionam por dentro.** As sugestões são **calculadas na hora**, não gravadas.
Só os descartes ficam numa tabela `suggestion_dismissals(key, until)`, em que
`key = tipo:road_id:direction:km_start:km_end` identifica a sugestão de forma estável.
`POST /schedule/suggestions/dismiss` esconde uma sugestão.

**Pronto quando:** a Agenda mostra poucas sugestões úteis, agrupadas por trecho, e
"Dispensar" faz uma sugestão sumir até a data informada.

## Item 15 — Conclusão automática e eficácia da roçada

**Conclusão automática.** Quando uma inspeção termina com sucesso (`DONE`), um evento
`INSPECTION` `PLANNED` é concluído sozinho se as **três** condições valerem:
1. mesmo sentido (evento com `direction = null` fica manual);
2. a inspeção cobre pelo menos **80 %** do intervalo do evento, medido em blocos;
3. foi feita até **3 dias antes** da data agendada, ou depois dela.

O evento recebe `inspection_id` e `completion_source = "AUTO"`. Um concluído
automaticamente pode ser **reaberto** (`DONE → PLANNED`); um concluído à mão não.
Roçada nunca é concluída automaticamente. A conclusão automática roda **ao fim da
análise** (item 8), não no `POST`.

**Eficácia da roçada.** Comparar o `green_percent` antes e depois de cada roçada
concluída. Sai quase pronta do item 11.

**Pronto quando:** enviar uma inspeção que cobre um evento planejado o conclui sem
intervenção e permite reabri-lo.

---

# PARTE E — Condicional

Só entram se surgir a necessidade real (o projeto prefere não adicionar complexidade
antes disso).

## PostgreSQL

**Quando:** mais de um usuário ou processo usando o banco ao mesmo tempo, ou consultas
analíticas pesadas. O SQLite atende o uso atual.

**Como:** pré-requisitos são os itens 1 e 5. Mover a URL do banco para a configuração
(hoje está fixa em `app/database/session.py`), remover `check_same_thread`, instalar o
driver (`psycopg`), revisar os tipos (`DateTime(timezone=True)`), migrar os dados com um
script ou recomeçar do seed, e rodar a suíte de testes contra o Postgres.

## Segurança para deploy

Hoje não há autenticação, `/storage` serve arquivos publicamente e o upload só confere
o `content-type` declarado pelo cliente. Se o sistema for exposto: autenticação mínima
(chave de API), CORS por ambiente, endpoints administrativos desligados por padrão (já
previsto no item 4), limite de requisições no upload, validação do conteúdo real do
arquivo e revisão do que `/storage` expõe.

## Dispositivo de borda

Câmera embarcada que captura no veículo e sincroniza depois. Ver
[dispositivo-de-borda.md](../dispositivo-de-borda.md).

---

# Dependências com o frontend

| Backend | O que o frontend precisa fazer |
|---|---|
| Item 2 (UTC com `Z`) | comparar datas como timestamp, não como texto |
| Item 3 (motivo e enums) | exibir o motivo da falha; usar os tipos gerados do OpenAPI |
| Item 3 (erros) | tratar `{detail}` em texto, lista e objeto (`ApiError`) |
| Item 4 (`/meta`) | esconder "Resetar análises" quando o reset estiver desligado |
| Item 8 (`PROCESSING`) | acompanhar a inspeção até terminar; tratar listas com inspeções em processamento |
| Falha em geral | ao escolher a "última inspeção" de um trecho, **ignorar `FAILED`** (hoje uma falha recente faz o trecho aparecer como "sem inspeção") |
| Itens 10 a 15 | calendário, painel de sugestões e Visão Geral |
