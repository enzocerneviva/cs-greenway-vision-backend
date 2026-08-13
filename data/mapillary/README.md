# Mapillary Dataset — Guia de Handoff

Este documento resume o experimento de aquisição de dados do Mapillary para o
GreenWay Vision: o que já foi feito, as decisões tomadas (e por quê), e o que
falta para chegar a um dataset rotulado utilizável no treinamento do
classificador de vegetação.

## 1. Contexto do projeto

O GreenWay Vision precisa de um `vision_engine.analyze(video_path)` que
retorna uma medição de vegetação (cm) e uma classificação (LOW/MEDIUM/HIGH).
A primeira versão desse engine (feita por outro colaborador) usava um
detector heurístico baseado em faixa de cor HSV — foi descartada porque seus
limiares são calibrados manualmente, não aprendidos a partir de dados, e o
objetivo do projeto é que a fronteira de decisão venha de um modelo treinado.

**Decisão tomada:** construir um classificador supervisionado (ex.: Random
Forest/Logistic Regression do scikit-learn, sobre features extraídas de
frame — reaproveitando `app/vision/frame_extractor.py`, que é agnóstico à
técnica de detecção). Um CNN treinado do zero foi descartado por falta de
dados rotulados e prazo curto (~1 semana para um protótipo demonstrável).

**Por que Mapillary:** não existe (ainda) uma câmera lateral calibrada
gerando dados reais da via. Mapillary é imagem de rua open/crowd-sourced
(licença CC-BY-SA — mais permissiva que o ToS do Google Street View),
usada aqui como **stand-in** para viabilizar um v1 "baseline aproximado".
Isso é uma limitação conhecida e aceita: o ângulo de captura (dashcam) não
bate com o ângulo real de inspeção (lateral), então este modelo v1 deve ser
documentado explicitamente como aproximado, não como o alvo de precisão
final. Quando existir dataset real com gabarito em cm, o pipeline deve ser
retreinável só trocando o dataset — não a arquitetura.

**Nota de licença:** imagens do Mapillary são CC-BY-SA. Para uso interno de
treinamento isso costuma ser tranquilo, mas se em algum momento imagens (ou
resultados derivados publicáveis) forem expostas externamente, checar o
requisito de atribuição antes.

## 2. O que já foi feito

Tudo em `data/mapillary/`, branch `feature/mapillary-dataset`.

### `extraction.py`

Script standalone (não faz parte do `app/` — sem FastAPI, sem banco). Lê o
token em `.env` (`MAPILLARY_ACCESS_TOKEN`, gitignored) e fala com a
**Graph API v4** do Mapillary (`https://graph.mapillary.com/images`).

Fluxo:

```text
.env (token)
    |
    v
fetch_images_by_sequences() ou fetch_images_metadata()   [busca + paginação]
    |
    v
lista de dicts (JSON bruto)
    |
    v
save_metadata_csv()  -> metadata.csv
    |
    v
plot_sequence_distribution() -> sequence_distribution.png
    |
    v
download_sample()  -> images/  (amostra pequena, N configurável)
```

Duas formas de buscar imagens (`main()` escolhe automaticamente):

- **Por bbox** (`fetch_images_metadata` + `generate_bbox_tiles` +
  `fetch_images_in_bbox`) — busca por área geográfica. **Problema
  descoberto e não totalmente satisfatório:** traz ruas aleatórias dentro
  da área, não necessariamente a via de interesse. Além disso a API rejeita
  (HTTP 500, `"reduce the amount of data you're asking for"`) bboxes com
  muita densidade de imagens — não é um limite de área fixo, depende da
  cobertura da região. Por isso o bbox é dividido em tiles (~1km,
  `TILE_SIZE_DEG`) e cada tile é tratado com try/except individual (um tile
  denso demais é pulado, não derruba o script inteiro). **Hoje esse modo é
  só fallback.**

- **Por `sequence_ids`** (`fetch_images_by_sequences`) — **modo atual /
  recomendado.** Você escolhe manualmente, no site/app do Mapillary
  (mapillary.com/app), as sequências de captura que realmente percorrem a
  via de interesse, e a API filtra só por elas. Resolve o problema de ruído
  do bbox. A lista de IDs fica na constante `SEQUENCE_IDS` no topo do
  arquivo.

Mecanismo de paginação (comum aos dois modos): cada resposta da API traz
`paging.next`, a URL já pronta da próxima página. O loop segue esse link até
acabar ou até atingir `MAX_METADATA_RECORDS` (hoje 500 — teto deliberado,
isto é só uma amostra exploratória, não o dataset completo).

### Saídas geradas

- `metadata.csv` — uma linha por imagem: `id, sequence, captured_at,
  compass_angle, longitude, latitude, thumb_1024_url`. Sobrescrito a cada
  execução (não é acumulativo).
- `sequence_distribution.png` — barras de quantidade de imagens por
  `sequence`. Útil para ver se as sequências escolhidas têm cobertura
  razoável ou se estão desbalanceadas (uma sequência de teste anterior
  tinha 500+ imagens sozinha; outras tinham só 1-2 — provavelmente pontos
  isolados, não sequências reais da via).
- `images/<id>.jpg` — amostra baixada (`SAMPLE_DOWNLOAD_COUNT`, hoje 20).
  **Não versionado no git** (está no `.gitignore` — regenerável rodando o
  script; vai crescer bastante quando a amostra aumentar).

### Decisões de repositório

- `data/mapillary/images/` no `.gitignore` (dado regenerável).
- `metadata.csv` e `sequence_distribution.png` versionados (pequenos,
  úteis como referência do que a última consulta trouxe).
- Dependências novas (`requests`, `python-dotenv`, `pandas`, `matplotlib`)
  adicionadas a `requirements.txt`.

## 3. Como rodar hoje

```bash
# 1. edite SEQUENCE_IDS no topo de extraction.py com os IDs de sequência
#    encontrados manualmente em mapillary.com/app (clique na via desejada)

# 2. rode com o Python do venv do projeto
./venv/Scripts/python data/mapillary/extraction.py
```

Isso atualiza `metadata.csv`, `sequence_distribution.png` e baixa uma nova
amostra em `images/`.

## 4. O que falta (próximas etapas)

Nada abaixo foi implementado ainda — são os próximos passos em aberto:

1. **Coletar as sequências reais de interesse.** Hoje só há um ID de
   exemplo em `SEQUENCE_IDS`. Precisa navegar o Mapillary ao longo dos
   trechos de via relevantes (SP-330 e possivelmente outras rodovias) e
   juntar uma lista de sequence_ids que cubram bem a área, evitando
   sequências muito curtas/isoladas (ver `sequence_distribution.png`).

2. **Decidir e implementar o processo de rotulação manual.** Não existe
   ferramenta de rotulação ainda. As labels serão LOW/MEDIUM/HIGH por
   julgamento visual (proporção espacial de vegetação na imagem), já que o
   Mapillary não tem label de vegetação nativo. Opções a avaliar:
   - planilha/CSV manual (abrir as imagens em `images/`, preencher uma
     coluna `label` referenciando o `id`);
   - script simples que mostra a imagem e pede input no terminal;
   - ferramenta de rotulação existente (ex. Label Studio) — provavelmente
     over-engineering para o volume e prazo atuais, mas vale considerar se
     o volume crescer.

   Importante manter rastreável a ligação entre `metadata.csv` (id →
   sequence/coords/etc.) e o arquivo de labels — ex.: adicionar uma coluna
   `label` ao próprio `metadata.csv`, ou um `labels.csv` separado com
   `id,label` para depois fazer merge por `id`.

3. **Expandir a amostra baixada** de acordo com o volume necessário para
   treinar (hoje só 20 imagens, deliberadamente pequeno para o experimento
   inicial). Ajustar `MAX_METADATA_RECORDS` e `SAMPLE_DOWNLOAD_COUNT`, ou
   trocar `download_sample` por "baixar tudo que está em `metadata.csv`"
   quando sair da fase exploratória.

4. **Entregar o contrato para o outro workstream** (arquitetura + CV,
   ver `docs/architecture.md` e a decisão de classificador treinável): o
   resultado final esperado é um dataset de imagens rotuladas (LOW/MEDIUM/
   HIGH) pronto para extração de features via `app/vision/frame_extractor.py`
   e treinamento do classificador. Documentar explicitamente as limitações
   do dataset (ângulo dashcam, rotulação visual aproximada, não é medição
   em cm) onde o modelo v1 for descrito, para não ser confundido com dado
   de precisão real.

## 5. Onde olhar para mais contexto

- `CLAUDE.md` na raiz do projeto — regras de como o projeto é conduzido
  (papel do Claude como mentor, roadmap, arquitetura, etc.).
- `docs/architecture.md` — arquitetura geral e a fronteira do Vision
  Engine.
- Branch `feature/mapillary-dataset` — todo o histórico de commits deste
  experimento.
