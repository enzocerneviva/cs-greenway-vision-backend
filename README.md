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

A classificação inicial será baseada na medida obtida:

| Medição | Classificação |
|---|---|
| < 10 cm | Baixa |
| 10 cm ≤ medida ≤ 30 cm | Média |
| > 30 cm | Alta |

Os valores acima representam as regras definidas para o MVP.

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

Contém os modelos utilizados para representar as entidades persistidas no banco de dados.

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

A API e o motor de visão computacional serão desenvolvidos de forma independente.

Para permitir o desenvolvimento paralelo da equipe, o Vision Engine deverá possuir uma interface clara.

Conceitualmente:

```python
result = vision_engine.analyze(video_path)
```

O resultado deverá conter, no mínimo:

```text
measurement
    value
    unit

classification
    priority
```

Exemplo conceitual:

```json
{
  "measurement": {
    "value": 24.5,
    "unit": "cm"
  },
  "classification": {
    "priority": "MEDIUM"
  }
}
```

A implementação interna utilizada para obter a medida poderá evoluir sem alterar a interface utilizada pelo restante do backend.

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

Projeto em fase inicial de desenvolvimento.

### Fase atual

**Fase 0 — Fundação do projeto**

Objetivos:

- estrutura inicial;
- configuração do ambiente;
- API mínima;
- documentação da arquitetura;
- definição das interfaces entre os módulos.

## Próximos passos

1. Configurar ambiente Python.
2. Configurar FastAPI e Uvicorn.
3. Criar endpoint `/health`.
4. Definir modelos e schemas iniciais.
5. Configurar SQLite.
6. Implementar upload de vídeos.
7. Criar interface do Vision Engine.
8. Implementar protótipo do processamento de vídeo.
9. Implementar medição e classificação.
10. Integrar frontend e backend.
11. Avaliar migração para PostgreSQL.