# GreenWay Vision — Backend

Backend da plataforma **GreenWay Vision**, desenvolvida para auxiliar no monitoramento automatizado da vegetação em áreas rodoviárias por meio de visão computacional.

O sistema recebe inspeções em vídeo, processa as imagens utilizando um motor de visão computacional e produz uma medição da vegetação em centímetros, utilizada para classificar a criticidade da ocorrência.

## Objetivo do MVP

O MVP tem como objetivo validar o fluxo completo da solução:

```text
Vídeo da inspeção
        ↓
Upload pela API
        ↓
Processamento do vídeo
        ↓
Detecção da vegetação
        ↓
Medição em centímetros
        ↓
Classificação da criticidade
        ↓
Armazenamento do resultado
        ↓
Consulta pela plataforma
```

A classificação oficial do projeto é baseada na medida em centímetros:

| Medição | Classificação |
|---|---|
| < 10 cm | LOW |
| 10 cm ≤ medida ≤ 30 cm | MEDIUM |
| > 30 cm | HIGH |

Essa regra está centralizada em `app/services/classification.py`. O classificador v1 (primeira versão do modelo treinável, sem calibração de câmera) prevê a classificação diretamente da imagem, sem produzir uma medida em cm real — ver `docs/architecture.md` §8 para o contrato completo.

## Tecnologias

- **Python** — linguagem principal
- **FastAPI** — framework para construção da API
- **Uvicorn** — servidor ASGI responsável pela execução da aplicação
- **Pydantic** — validação e modelagem dos dados da API
- **SQLAlchemy** — ORM para comunicação com o banco de dados
- **SQLite** — banco utilizado inicialmente durante o desenvolvimento
- **PostgreSQL** — banco previsto para uma etapa posterior
- **OpenCV** — processamento e análise dos vídeos e imagens
- **NumPy** — manipulação numérica e de matrizes utilizada pelo processamento de imagens

## Arquitetura

O backend será dividido em módulos com responsabilidades específicas.

```text
                         GreenWay Vision Backend

                                  │
                                  ▼
                            FastAPI / API
                                  │
                                  ▼
                         Application Services
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
              Vision Engine                Database
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      Detection           Measurement
                              │
                              ▼
                        Classification
```

O módulo de visão computacional será desacoplado da API. Dessa forma, o motor de visão poderá ser testado independentemente do restante da aplicação.

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

docs/
└── architecture.md
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

Contém os modelos utilizados para representar as entidades persistidas no banco de dados: `Road`, `Segment`, `Video`, `Inspection`.

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
result = vision_engine.analyze(video_path)
```

```python
@dataclass
class AnalysisResult:
    priority: str                          # LOW / MEDIUM / HIGH
    model_version: str
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
```

Hoje a classificação é **simulada** (`model_version = "mock-v0"`) — o modelo treinável real (classificador scikit-learn sobre embeddings de uma CNN pré-treinada) entra depois, sem mudar essa interface. Veja `docs/architecture.md` §8 para detalhes, incluindo por que `measurement_value` fica `None` no v1.

A implementação interna utilizada para obter a classificação pode evoluir sem alterar a interface usada pelo restante do backend.

## Desenvolvimento

O projeto utiliza Git Flow simplificado.

A branch `master` representa uma versão estável e integrada do projeto.

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

As alterações devem ser integradas à `master` por meio de Pull Requests.

## Status

O fluxo completo do MVP está funcional ponta a ponta, com o modelo de classificação simulado:

```text
POST /roads, POST /segments   → cadastro de rodovia/trecho
POST /inspections              → upload do vídeo, extração de frames,
                                  pré-filtro por cor, classificação
                                  (simulada), persistência
GET /inspections, GET /inspections/{id} → consulta dos resultados
```

### Fase atual

**Vision Engine — integração do modelo real**

O que falta pra sair do "v1 simulado" pro modelo de verdade:

- treinar o classificador com o dataset rotulado (~700 imagens com gabarito, em preparação por outro desenvolvedor);
- extrair embeddings com uma CNN pré-treinada (transfer learning, sem treinar a rede) e treinar um classificador `scikit-learn` (Random Forest) em cima;
- substituir `_classify_frame_mock()` (`app/vision/engine.py`) pela chamada ao modelo treinado, carregado uma vez na inicialização.

### Concluído

- API, banco de dados (Road → Segment → Video → Inspection), camada de Repository, upload de vídeo com validação, pipeline de visão computacional (extração de frames + pré-filtro), classificação simulada, persistência e consulta — tudo integrado e testado ponta a ponta.

## Próximos passos

1. Treinar e integrar o modelo real de classificação (ver "Fase atual").
2. Testes automatizados cobrindo Vision Engine e API isoladamente.
3. Integrar frontend e backend.
4. Avaliar migração para PostgreSQL.
5. Avaliar georreferenciamento das inspeções (fase futura, fora do escopo atual).