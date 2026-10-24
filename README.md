# GreenWay Vision — Backend

Backend da plataforma **GreenWay Vision**, desenvolvida para auxiliar no monitoramento automatizado da vegetação em áreas rodoviárias por meio de visão computacional.

O sistema recebe inspeções em vídeo ou foto de trechos de rodovia, processa as imagens com um motor de visão computacional e classifica a criticidade da vegetação (`LOW`, `MEDIUM` ou `HIGH`) frame a frame, estimando a posição (km) de cada frame ao longo do trecho.

## Objetivo do MVP

O MVP tem como objetivo validar o fluxo completo da solução:

```text
Vídeo/foto da inspeção
        ↓
Upload pela API
        ↓
Extração de frames
        ↓
Pré-filtro de vegetação (cor)
        ↓
Classificação da criticidade (modelo treinado)
        ↓
Armazenamento do resultado (inspeção + frames + posição estimada)
        ↓
Consulta pela plataforma
```

### Regra de classificação (referência) × classificador atual

A regra oficial do projeto, baseada em medida física, é:

| Medição | Classificação |
|---|---|
| < 10 cm | LOW |
| 10 cm ≤ medida ≤ 30 cm | MEDIUM |
| > 30 cm | HIGH |

Ela está centralizada em `app/services/classification.py`, mas **não é usada hoje**: com câmera frontal (dashcam) e sem calibração, não há como medir centímetros. O classificador v1 prevê `LOW/MEDIUM/HIGH` diretamente da aparência da imagem, e `measurement_value` fica `None`. A regra em cm só volta a ser usada se existir uma fonte de medição calibrada — ver `docs/architecture.md` §8.

## Tecnologias

- **Python** — linguagem principal
- **FastAPI** — framework para construção da API
- **Uvicorn** — servidor ASGI responsável pela execução da aplicação
- **Pydantic** — validação e modelagem dos dados da API
- **SQLAlchemy** — ORM para comunicação com o banco de dados
- **SQLite** — banco utilizado durante o desenvolvimento
- **PostgreSQL** — banco previsto para uma etapa posterior
- **OpenCV** — leitura de vídeo, extração de frames e pré-filtro de cor
- **NumPy** — manipulação numérica e de matrizes
- **PyTorch / torchvision (MobileNetV2)** — extração de embeddings das imagens (rede pré-treinada, usada só em inferência)
- **scikit-learn / joblib** — classificador RandomForest treinado sobre os embeddings
- **requests** — consulta ao OpenStreetMap (geometria das rodovias) e ao Mapillary (dataset)

## Arquitetura

O backend é um monólito modular, dividido em camadas com responsabilidades específicas.

```text
Frontend (React)
      │ HTTP/REST (+ /storage para as imagens dos frames)
      ▼
FastAPI (rotas finas)  →  Services  →  Repositories  →  SQLAlchemy  →  SQLite
                              │
                              ▼
                        Vision Engine
        frames → pré-filtro HSV → embedding CNN → RandomForest
```

O módulo de visão computacional é desacoplado da API: o motor de visão pode ser testado independentemente do restante da aplicação.

Planos de evolução em `docs/`:
- `docs/plans/plano-v2.md` — plano da V2, na ordem de execução: base (migrações, datas, erros, configuração), confiabilidade, modelo de visão, e Agenda/análise de dados.
- `docs/dispositivo-de-borda.md` — câmera embarcada e sincronização em lote (fase futura).

## Estrutura do projeto

```text
app/
│
├── api/
│   └── routes/
│
├── core/
│
├── database/
│
├── models/
│
├── schemas/
│
├── repositories/
│
├── services/
│
├── vision/
│
├── utils/
│
└── main.py

tests/
data/            # dataset Mapillary, treino do classificador e modelo treinado
scripts/         # seed_roads.py (popula rodovias reais)
storage/         # vídeos, imagens e frames enviados (não versionado)

docs/
├── architecture.md
├── dispositivo-de-borda.md      # câmera embarcada e sincronização (fase futura)
└── plans/
    └── plano-v2.md              # plano da V2, na ordem de execução
```

### `api/`

Contém os endpoints HTTP da aplicação.

Responsável pela comunicação externa com o frontend e outros clientes.

### `services/`

Contém as regras de negócio e coordena o fluxo das operações.

Exemplo:

```text
Receber inspeção
      ↓
Salvar vídeo
      ↓
Executar Vision Engine
      ↓
Persistir resultado
```

### `vision/`

Contém o motor de visão computacional.

Responsabilidades previstas:

- leitura dos vídeos;
- extração de frames;
- detecção da vegetação;
- medição;
- classificação.

O módulo não deve depender diretamente de FastAPI ou do banco de dados.

### `models/`

Contém os modelos utilizados para representar as entidades persistidas no banco de dados: `Road`, `Segment`, `Video`, `Inspection`, `FrameAnalysis`.

### `repositories/`

Contém o acesso a dados (queries e inserts via SQLAlchemy), um módulo por entidade. Services e rotas não montam queries diretamente — sempre passam por aqui.

### `schemas/`

Contém os modelos de entrada e saída da API.

### `database/`

Contém a configuração e integração com o banco de dados.

### `core/`

Contém configurações e componentes centrais da aplicação.

### `utils/`

Contém funções auxiliares reutilizáveis que não pertencem a uma regra de negócio específica.

### `tests/`

Contém os testes automatizados do projeto.

## Contrato entre API e Vision Engine

A API e o motor de visão computacional são desenvolvidos de forma independente, comunicando-se apenas pelo contrato abaixo (`app/vision/engine.py` + `app/vision/analysis_result.py`):

```python
from app.vision import engine as vision_engine
result = vision_engine.analyze(file_path, media_type, frame_image_dir=None)
```

```python
@dataclass
class AnalysisResult:
    priority: str                          # LOW / MEDIUM / HIGH (pior caso entre os frames)
    model_version: str                     # hoje "mapillary-v1-randomforest"
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
    frame_results: List[FrameResult] = ...  # detalhe por frame
```

A classificação é feita pelo modelo treinado (RandomForest sobre embeddings da MobileNetV2). Veja `docs/architecture.md` §8 para detalhes, incluindo por que `measurement_value` fica `None` no v1.

A implementação interna utilizada para obter a classificação pode evoluir sem alterar a interface usada pelo restante do backend.

## Endpoints principais

| Rota | Função |
|---|---|
| `GET /health` | verificação de saúde |
| `GET /meta` | configuração do backend (fuso, tamanho do bloco, se o reset está liberado, limite de baixa confiança) |
| `POST /roads`, `GET /roads` | cadastro/lista de rodovias (a geometria é buscada no OpenStreetMap) |
| `POST /segments`, `GET /segments`, `PATCH /segments/{id}/location` | trechos e suas coordenadas |
| `POST /inspections` | upload de vídeo/foto (multipart: `segment_id`, `file`, opcionais `km_start`, `km_end`, `direction`). Responde **202** com a inspeção em `PROCESSING`; a análise roda em segundo plano |
| `GET /inspections`, `GET /inspections/{id}` | resultados, com os frames classificados. `status`: `PROCESSING`, `DONE` ou `FAILED` (com `failure_reason`) — consulte até sair de `PROCESSING` |
| `DELETE /inspections` | apaga todas as análises (só para testes; ver plano de robustez) |
| `/storage/...` | arquivos estáticos (imagens dos frames) |

`direction` é `CAPITAL` ou `INTERIOR`. `estimated_km` de cada frame é interpolação linear entre `km_start` e `km_end` informados (ou os do trecho inteiro) — aproximação, não GPS.

## Como executar localmente

Os comandos abaixo são para Windows (PowerShell). No Linux/macOS, a única diferença é a ativação do venv: `source venv/bin/activate`.

### Pré-requisitos

- **Python 3.12 ou superior** (o projeto foi desenvolvido com 3.14) — confira com `python --version`
- **Git**
- **Node.js 18+** — só se for rodar também o frontend
- Conexão com a internet na instalação das dependências e no passo de seed (consulta ao OpenStreetMap)

### 1. Clonar e criar o ambiente virtual

```powershell
git clone <url-do-repositorio>
cd cs-greenway-vision-backend

python -m venv venv
.\venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativação, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Com o venv ativo, o prompt mostra `(venv)`. Todos os comandos seguintes devem ser executados com ele ativo.

### 2. Instalar as dependências

O `torch` e o `torchvision` são a build **CPU-only**, que não está no PyPI padrão, então a instalação é feita em dois passos:

```powershell
pip install torch==2.13.0+cpu torchvision==0.28.0+cpu --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

O download é grande (centenas de MB) por causa do PyTorch.

> Na primeira análise de imagem, o `torchvision` baixa os pesos do MobileNetV2 (~14 MB) e os guarda em cache. Isso exige internet apenas nessa primeira vez.

### 3. Criar o banco e rodar a API

O esquema do banco (tabelas e colunas) é gerenciado pelo **Alembic**. Na raiz do projeto, com o venv ativo, aplique as migrações:

```powershell
alembic upgrade head
```

Isso cria o `greenway.db` (SQLite) com todas as tabelas. Rode de novo sempre que baixar mudanças que incluam arquivos novos em `alembic/versions/`; se não houver nada pendente, não faz nada.

Depois, suba a API:

```powershell
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Documentação interativa (Swagger): http://localhost:8000/docs
- Teste rápido: http://localhost:8000/health deve retornar `{"status":"ok"}`

A pasta `storage/` (vídeos, imagens e frames) é criada automaticamente na primeira execução. O classificador treinado já está versionado em `data/mapillary/model/classifier.joblib`, então não é preciso treinar nada.

### 4. Popular as rodovias (seed)

Em outro terminal, com o venv ativo e a partir da raiz do projeto:

```powershell
python scripts/seed_roads.py
```

Cadastra SP-330 (Anhanguera) e SP-348 (Bandeirantes) com a geometria buscada no OpenStreetMap. É idempotente: rodar de novo não duplica. Sem esse passo, não há rodovia/trecho para vincular uma inspeção.

### 5. Testar o fluxo

Pelo Swagger (http://localhost:8000/docs):

1. `GET /roads` — confirme que as rodovias do seed aparecem;
2. `POST /inspections` — envie um vídeo ou uma foto, informando o trecho (responde 202 com `status: "PROCESSING"`);
3. `GET /inspections/{id}` — repita até o `status` virar `DONE` ou `FAILED` e então veja o resultado e os frames classificados.

### 6. Rodar os testes

Com o venv ativo, na raiz do projeto:

```powershell
pytest
```

Os testes usam um banco em memória, pastas temporárias e um Vision Engine falso: não tocam o `greenway.db` nem o `storage/` e não carregam o modelo (rodam em poucos segundos).

### 7. Rodar o frontend (opcional)

O frontend fica em outro repositório (`cs-greenway-vision-frontend`):

```powershell
cd ..\cs-greenway-vision-frontend
npm install
npm run dev
```

Abra http://localhost:5173. Ele espera a API em `http://localhost:8000` (configurável pela variável `VITE_API_BASE_URL`). A API só aceita requisições (CORS) vindas de `http://localhost:5173`, então mantenha essa porta.

### Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Comando rodado fora da raiz do projeto |
| `ModuleNotFoundError` de qualquer outra lib | venv não ativado, ou `pip install` não executado |
| Erro ao instalar `torch==2.13.0+cpu` | Faltou o `--index-url` do passo 2 |
| Frontend não carrega dados / erro de CORS | API fora do ar, ou frontend rodando em porta diferente de 5173 |
| Seed falha ao buscar geometria | Sem internet ou OpenStreetMap indisponível — tente novamente |
| `no such table` / `no such column` | Banco sem as migrações aplicadas — rode `alembic upgrade head` |
| Quer zerar tudo | Pare a API, apague `greenway.db` e `storage/`, rode `alembic upgrade head` e depois o seed (passo 4) |

## Desenvolvimento

O projeto utiliza Git Flow simplificado.

A branch `main` representa uma versão estável e integrada do projeto. O trabalho de arquitetura/backend acontece em `feature/backend-core`.

Novas funcionalidades devem ser desenvolvidas em branches próprias:

```text
feature/<nome-da-funcionalidade>
```

Correções:

```text
fix/<nome-da-correcao>
```

Alterações estruturais:

```text
refactor/<nome-do-refactor>
```

As alterações devem ser integradas à `main` por meio de Pull Requests.

## Status

O fluxo completo do MVP está funcional ponta a ponta, com o modelo de classificação **real** (não mais simulado):

```text
POST /roads, POST /segments   → cadastro de rodovia/trecho
POST /inspections              → upload de vídeo ou foto, extração de frames,
                                  pré-filtro por cor (HSV), embedding via CNN
                                  pré-treinada (MobileNetV2), classificação
                                  por RandomForest treinado, persistência
GET /inspections, GET /inspections/{id} → consulta dos resultados,
                                  incluindo frames classificados e georreferenciamento
```

### Concluído

- API, banco de dados (Road → Segment → Video → Inspection → FrameAnalysis), camada de Repository, upload de vídeo/foto com validação, pipeline de visão computacional completo (extração de frames, pré-filtro HSV, embedding CNN, classificação treinada), persistência de frames classificados, geocodificação automática de trechos via OpenStreetMap, e consulta — tudo integrado e testado ponta a ponta.
- Classificador (`mapillary-v1-randomforest`) treinado sobre 648 imagens rotuladas do dataset Mapillary (ver `data/mapillary/README.md` para a documentação completa do experimento, incluindo a limitação conhecida do dataset — ver "Decisão de captura" abaixo).
- Frontend integrado (repositório `cs-greenway-vision-frontend`), consumindo a API real: Upload, Dashboard, mapa de rodovias, histórico e detalhe de trecho.

### Decisão de captura: dashcam, não lateral

O ângulo de captura do dispositivo (planejado e atual dataset de treino) é **frontal, tipo dashcam** — decisão definitiva, não um meio-termo até migrar para lateral. Motivo: o dataset disponível (Mapillary) é majoritariamente capturado nesse ângulo, então manter a captura de produção consistente com ele reduz o gap entre treino e uso real, em vez de ampliá-lo. Uma câmera lateral exigiria um dataset próprio inexistente hoje.

Isso também define o tipo de saída do modelo: o classificador não tenta medir vegetação em centímetros — sem calibração de câmera ou referência de escala conhecida no frame, uma imagem monocular não permite recuperar distância/tamanho real (ambiguidade de escala clássica em visão computacional). O modelo aprende, sim, um mapeamento direto entre padrão visual (densidade/extensão de verde) e rótulo (LOW/MEDIUM/HIGH) — um proxy visual, não uma medição física. `measurement_value` continua `None` no v1 por esse motivo (ver `docs/architecture.md` §8).

## Computação de borda — câmera embarcada (próxima fase, planejada)

Especificado e documentado; **não construído fisicamente ainda**.

**Componentes:** Raspberry Pi Camera Module 3 (sensor de imagem, CSI) + módulo GPS NEO-6M (sensor de posição/velocidade, UART) + Raspberry Pi Zero 2 W (controlador) + LED de status (atuador, GPIO) + cartão microSD 32GB (armazenamento) + power bank USB 5V/2A ~10.000mAh (alimentação) + case comercial + suporte veicular de ventosa com adaptador 1/4" (fixação tipo dashcam).

**Alimentação:** ~5–8W total (Pi 0,7–1,2A + câmera ~0,25A + GPS ~0,05A + LED desprezível) @5V, via power bank USB-C.

**Algoritmo:** GPS lê posição/velocidade continuamente → velocidade < 5 km/h (parado/trânsito) descarta → em movimento, captura 1 frame a cada X metros percorridos → pré-filtro HSV (`detectar_vegetacao`, reaproveitado sem alteração) → frame com verde ≥5% é salvo no SD com o km calculado via GPS.

**Comunicação:** modo *store-and-forward* — sem rádio Wi-Fi ativo em campo. Os frames ficam gravados localmente durante o trajeto; a sincronização acontece depois, fora do veículo, removendo o cartão SD e rodando um script que faz `POST /inspections` (mesmo endpoint que o frontend já usa para upload de foto) para cada frame relevante.

## Próximos passos

O plano vigente é `docs/plans/plano-v2.md`:

1. **Base (Parte A)** — Alembic, fuso com `Z`, `failure_reason`, enums tipados e configuração central.
2. **Confiabilidade e modelo (Partes B e C)**:
   - transação atômica na criação da inspeção (hoje há um `commit` por frame);
   - controle do crescimento de `storage/`;
   - qualidade do modelo: no teste (130 imagens) a acurácia é ~88,5 %, mas a classe MEDIUM tem recall de ~23 % (3 de 13), por haver muito mais exemplos de HIGH — rebalancear e ampliar o dataset é o caminho mais direto;
   - análise assíncrona do upload, PostgreSQL e segurança para deploy (só se houver necessidade real).
3. **Agenda e análise de dados (Parte D)** — `/schedule` e `/analytics`.
4. **Dispositivo de borda** — ver `docs/dispositivo-de-borda.md`: construir fisicamente o hardware especificado acima e integrar via envio em lote com GPS real.