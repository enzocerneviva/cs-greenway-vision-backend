# GreenWay Vision — Arquitetura

## 1. Visão geral

O GreenWay Vision é uma plataforma destinada ao monitoramento automatizado da vegetação em áreas rodoviárias.

O backend será responsável por receber as inspeções, coordenar o processamento, armazenar os resultados e disponibilizar as informações para o frontend.

O processamento de visão computacional será encapsulado em um módulo independente denominado **Vision Engine**.

A arquitetura inicial será monolítica modular, e não baseada em microsserviços.

Isso reduz a complexidade do MVP sem impedir que componentes sejam extraídos para serviços independentes no futuro, caso exista necessidade técnica.

---

# 2. Arquitetura de alto nível

```text
                    ┌─────────────────────┐
                    │      Frontend       │
                    │       React         │
                    └──────────┬──────────┘
                               │
                               │ HTTP/REST
                               ▼
                    ┌─────────────────────┐
                    │      FastAPI        │
                    │        API          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Services       │
                    │   Business Logic    │
                    └───────┬───────┬─────┘
                            │       │
                            │       │
                            ▼       ▼
                   ┌────────────┐ ┌──────────────┐
                   │   Vision   │ │   Database   │
                   │   Engine   │ │   SQLAlchemy │
                   └─────┬──────┘ └──────┬───────┘
                         │                │
                         ▼                ▼
                  ┌────────────┐   ┌─────────────┐
                  │ OpenCV /   │   │   SQLite    │
                  │ NumPy      │   │ PostgreSQL* │
                  └────────────┘   └─────────────┘
```

`PostgreSQL*` representa a evolução prevista do banco após a validação inicial do MVP.

---

# 3. Princípio de separação de responsabilidades

Cada módulo deve possuir uma responsabilidade clara.

```text
API
↓
Comunicação HTTP

Services
↓
Regras de negócio e orquestração

Vision Engine
↓
Processamento de visão computacional

Repositories
↓
Acesso a dados (queries, inserts) isolado do restante da aplicação

Database
↓
Persistência

Models
↓
Representação das entidades persistidas

Schemas
↓
Contratos de entrada e saída da API
```

Um módulo não deve assumir responsabilidades pertencentes a outro módulo sem necessidade.

---

# 4. API

A camada de API será implementada utilizando FastAPI.

Sua responsabilidade é:

- receber requisições HTTP;
- validar dados de entrada;
- chamar os serviços apropriados;
- retornar respostas HTTP;
- definir os contratos externos da aplicação.

A API não deve conter diretamente a lógica de processamento da visão computacional.

Exemplo conceitual:

```text
POST /inspections

Request
   ↓
Inspection Route
   ↓
Inspection Service
   ↓
Vision Engine
   ↓
Database
   ↓
Response
```

---

# 5. Services

A camada de serviços contém a lógica de aplicação.

Ela funciona como uma camada de orquestração entre a API, o Vision Engine e o banco.

Exemplo:

```text
InspectionService

1. Receber vídeo
2. Armazenar vídeo
3. Solicitar análise ao Vision Engine
4. Receber resultado
5. Persistir resultado
6. Retornar resultado
```

O Service não deve implementar diretamente algoritmos de processamento de imagem.

---

# 5.1 Repositories

A camada de Repository isola o acesso a dados (queries e inserts via SQLAlchemy) do restante da aplicação.

```text
Service
   ↓
Repository
   ↓
SQLAlchemy Session
```

Sem essa camada, cada Service (ou rota) precisaria montar suas próprias queries diretamente, espalhando conhecimento sobre a estrutura do banco pela aplicação. Com o Repository, o Service pede o dado (`inspection_repository.get_by_id(db, id)`) sem saber como a busca é feita internamente.

Cada entidade (`Road`, `Segment`, `Video`, `Inspection`) tem seu próprio módulo de repository em `app/repositories/`, com operações básicas (`create`, `get_by_id`, `list_all`).

---

# 6. Vision Engine

O Vision Engine é o principal componente técnico do projeto.

Sua responsabilidade é transformar um vídeo de inspeção em informações mensuráveis sobre a vegetação.

Fluxo esperado:

```text
Vídeo
  ↓
Extração de frames
  ↓
Detecção da vegetação
  ↓
Medição
  ↓
Classificação
  ↓
AnalysisResult
```

O Vision Engine deverá ser independente da camada HTTP e do banco de dados.

Ele deve ser possível de executar conceitualmente desta forma:

```python
result = vision_engine.analyze(video_path)
```

sem que seja necessário iniciar o FastAPI.

---

# 7. Pipeline de visão computacional

A implementação inicial será desenvolvida em etapas.

## 7.1 Extração

O vídeo será dividido em frames para processamento.

```text
Video
 ↓
Frame 1
Frame 2
Frame 3
...
Frame N
```

## 7.2 Detecção

Cada frame poderá ser analisado para identificar a região correspondente à vegetação.

A técnica exata ainda será definida durante o desenvolvimento experimental.

## 7.3 Medição

A região detectada deverá ser convertida em uma medida física em centímetros.

Esta etapa é dependente dos dados disponíveis no vídeo e do método de calibração adotado.

O objetivo do MVP é produzir uma medida que possa ser utilizada pela regra de classificação definida pelo projeto.

## 7.4 Classificação

A classificação será determinada pela medida obtida.

```text
measurement < 10 cm
        ↓
LOW

10 cm ≤ measurement ≤ 30 cm
        ↓
MEDIUM

measurement > 30 cm
        ↓
HIGH
```

Os valores devem ser centralizados em uma regra de negócio, evitando que sejam espalhados pelo código.

---

# 8. Contrato Vision Engine

A comunicação entre o restante da aplicação e o Vision Engine é feita através de um contrato explícito, implementado em `app/vision/analysis_result.py` e `app/vision/engine.py`.

Entrada:

```python
from app.vision import engine as vision_engine
vision_engine.analyze(video_path)
```

Saída (`AnalysisResult`):

```python
@dataclass
class AnalysisResult:
    priority: str                          # LOW / MEDIUM / HIGH
    model_version: str
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
```

**Nota importante sobre `measurement_value`**: o classificador v1 (baseado em imagens de referência sem calibração de câmera) prevê a `priority` diretamente a partir da imagem — ele não produz uma medida física real em centímetros. Por isso `measurement_value`/`measurement_unit` ficam `None` nesse caminho. `classify_priority()` (`app/services/classification.py`), que aplica a regra oficial baseada em cm, permanece centralizado e será usado quando existir uma fonte real de medição calibrada (ex.: câmera lateral).

O restante da aplicação não deve depender de como a medida foi obtida. Por exemplo, o Service não deve saber se o Vision Engine utilizou:

- segmentação por cor;
- análise geométrica;
- modelo de machine learning;
- modelo de deep learning;
- calibração da câmera.

Esses detalhes pertencem ao Vision Engine.

## 8.1 Implementação atual (v1 — baseline)

```text
Vídeo
  ↓
extrair_frames()               → app/vision/frame_extractor.py
  ↓
pré-filtro por cor (HSV)       → app/vision/vegetation_detector.py
  (descarta frames sem vegetação relevante, barato de rodar)
  ↓
classificador                  → hoje MOCKADO (app/vision/engine.py);
                                  será um classificador scikit-learn
                                  treinado sobre embeddings extraídos
                                  por uma CNN pré-treinada (transfer
                                  learning, sem treinar a rede do zero)
  ↓
AnalysisResult
```

---

# 9. Banco de dados

O banco será inicialmente utilizado para persistir informações das inspeções e seus resultados.

Durante o desenvolvimento inicial será utilizado SQLite para reduzir a complexidade de configuração.

A arquitetura será preparada para posterior utilização de PostgreSQL.

A comunicação da aplicação com o banco será realizada através do SQLAlchemy.

Conceitualmente:

```text
Application
    ↓
SQLAlchemy
    ↓
Database Driver
    ↓
SQLite / PostgreSQL
```

A aplicação não deverá depender de SQL específico do banco sempre que isso puder ser evitado.

---

# 10. Models e Schemas

## Models

Representam entidades persistidas (`app/models/`). O modelo de dados reflete o domínio real, não uma tabela única:

```text
Road (rodovia)
  id, name
        │
        ▼
Segment (trecho da rodovia, com sentido/direção)
  id, road_id, km_start, km_end, direction
        │
        ▼
Video (o vídeo enviado numa inspeção)
  id, segment_id, file_path, original_filename, uploaded_at
        │
        ▼
Inspection (resultado de UMA análise — vínculo 1:1 com Video)
  id, video_id (único), measurement_value, measurement_unit,
  priority, model_version, status (DONE/FAILED), analyzed_at, created_at
```

`Road`/`Segment` existem como cadastro relativamente estável. `Video` nasce no upload. `Inspection` nasce (ou falha) na análise — por isso são tabelas separadas: cada uma tem um ciclo de vida diferente.

## Schemas

Representam os contratos utilizados pela API (`app/schemas/`): `RoadCreate`/`RoadResponse`, `SegmentCreate`/`SegmentResponse`, `InspectionResponse`.

Essa separação evita acoplar diretamente a estrutura interna do banco aos contratos públicos da API.

---

# 11. Fluxo completo de uma inspeção

Implementado (`POST /inspections`, multipart: `segment_id` + vídeo):

```text
                 FRONTEND
                    │
                    │ POST /inspections
                    │ segment_id + video
                    ▼
              ROTA (app/api/routes/inspection.py)
                    │  fina — delega tudo pro service
                    ▼
       INSPECTION SERVICE (app/services/inspection_service.py)
                    │
                    │ 1. valida que o Segment existe (404 se não)
                    │ 2. salva o vídeo em disco (storage/videos/)
                    │ 3. persiste o Video (via Repository)
                    ▼
              VISION ENGINE (app/vision/engine.py)
                    │
                    ▼
                VIDEO FRAMES  →  PRÉ-FILTRO (HSV)  →  CLASSIFICAÇÃO
                    │
                    ▼
              ANALYSIS RESULT
                    │
          ┌─────────┴─────────┐
          │ sucesso            │ exceção
          ▼                    ▼
   Inspection(status=DONE)  Inspection(status=FAILED)
                    │
                    ▼
       persiste via Repository → DATABASE
                    │
                    ▼
                RESPONSE
                    │
                    ▼
                FRONTEND
```

---

# 12. Desenvolvimento paralelo

O desenvolvimento será dividido em duas frentes principais.

## Backend / Arquitetura

Responsável por:

- FastAPI;
- Uvicorn;
- endpoints;
- upload;
- schemas;
- services;
- banco de dados;
- persistência;
- testes de integração.

## Vision Engine

Responsável por:

- leitura dos vídeos;
- extração de frames;
- detecção;
- medição;
- classificação;
- testes do processamento de imagem.

---

# 13. Regra de integração entre as equipes

As duas frentes devem se comunicar somente através de interfaces definidas.

O backend deve depender do contrato do Vision Engine, e não de sua implementação interna.

Exemplo:

```text
InspectionService
       │
       ▼
VisionEngine.analyze(video_path)
       │
       ▼
AnalysisResult
```

O desenvolvedor do backend não precisa conhecer a implementação interna do algoritmo.

O desenvolvedor do Vision Engine não precisa conhecer FastAPI, React ou SQLAlchemy.

---

# 14. Desenvolvimento orientado a contrato

Antes da implementação paralela, a equipe deve definir:

- formato de entrada;
- formato de saída;
- unidades utilizadas;
- estados possíveis;
- classificação;
- tratamento de erros.

Isso permite que cada componente seja desenvolvido e testado independentemente.

Durante o desenvolvimento inicial, o backend poderá utilizar um resultado simulado enquanto o Vision Engine ainda estiver sendo desenvolvido.

Exemplo:

```json
{
  "measurement": {
    "value": 25.0,
    "unit": "cm"
  },
  "classification": {
    "priority": "MEDIUM"
  }
}
```

Posteriormente, o resultado simulado será substituído pela implementação real.

---

# 15. Estratégia de evolução

A arquitetura será construída inicialmente para o MVP.

Não serão introduzidos microsserviços ou infraestrutura complexa sem necessidade.

A evolução planejada é:

```text
MVP

Monólito modular
      ↓
Validação da solução
      ↓
Identificação de gargalos
      ↓
Possível separação de componentes
```

Caso o processamento de visão computacional exija recursos ou escalabilidade diferentes do restante da API, o Vision Engine poderá futuramente ser transformado em um serviço independente.

---

# 16. Princípios técnicos

Durante o desenvolvimento, serão priorizados:

- baixo acoplamento;
- alta coesão;
- interfaces explícitas;
- separação de responsabilidades;
- testes independentes;
- código simples antes de abstrações desnecessárias;
- documentação das decisões arquiteturais;
- desenvolvimento incremental.

A prioridade é construir primeiro uma solução funcional e compreensível, evoluindo a arquitetura conforme necessidades reais forem identificadas.