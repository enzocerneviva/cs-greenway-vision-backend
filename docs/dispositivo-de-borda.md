# Dispositivo de borda — câmera embarcada e sincronização

Documento separado do [plano da V2](plans/plano-v2.md): descreve uma fase **futura**, que só
faz sentido quando o hardware existir. Está aqui para você ler com calma depois.

## 1. O que é "computação de borda" neste projeto

*Borda* (edge) significa processar o dado **perto de onde ele nasce**, em vez de enviar
tudo para o servidor. Aqui, um pequeno computador no veículo faz o trabalho barato, e o
servidor (este backend) faz o trabalho caro.

```text
Veículo (dispositivo)                        Servidor (este backend)
─────────────────────                        ───────────────────────
câmera + GPS                                 
  ↓                                          
descarta quando o carro está parado          
  ↓                                          
1 foto a cada X metros percorridos           
  ↓                                          
filtro de cor: tem vegetação? (≥ 5 % verde)  
  ↓                                          
guarda só as fotos relevantes no cartão SD   
  ↓  (depois, fora do veículo)               
envia o lote  ───────────────────────────►   classifica com o modelo,
                                             grava e mostra no mapa
```

**Por que assim:** em campo não há internet estável. Enviar só as fotos relevantes,
depois, reduz custo e dependência de rede. O filtro de cor é a mesma função que o
backend já usa (`detectar_vegetacao`).

## 2. O dispositivo (especificado, não construído)

Raspberry Pi Zero 2 W (controlador), Camera Module 3 (imagem), GPS NEO-6M (posição e
velocidade), LED de status, cartão microSD de 32 GB e power bank USB de ~10.000 mAh
(consumo estimado de 5 a 8 W). A câmera é **frontal, tipo dashcam** (decisão definitiva;
ver README).

## 3. O que o backend não faz hoje

1. **A posição do frame é estimada.** Hoje o backend recebe "este arquivo cobre do km 11
   ao km 12" e **interpola** o km de cada frame pelo índice. O dispositivo terá o GPS
   real de cada foto, e a interpolação deveria virar só um *plano B*.
2. **Reenviar duplica tudo.** Se o cartão SD for sincronizado duas vezes (algo comum),
   o backend criaria as mesmas fotos de novo.

## 4. Pré-requisitos no plano da V2

- esquema do banco (item 1): serão necessárias colunas e uma tabela novas;
- gravação atômica (item 6): um lote não pode ficar pela metade;
- análise assíncrona (item 8): um lote tem centenas de fotos e não cabe numa resposta
  imediata;
- segurança (Parte E): hoje a API é aberta; um dispositivo exigiria autenticar o aparelho.

## 5. Contrato proposto para o envio em lote

**Rascunho para aprovação.** Segue as mesmas convenções do plano da V2 (UTC com `Z`,
enums tipados, erros no formato `{"detail": ...}`, km semiaberto).

### `POST /edge/syncs` — recebe um lote (`multipart/form-data`)

| Campo | Tipo | Descrição |
|---|---|---|
| `manifest` | texto (JSON) | metadados do lote |
| `frames` | arquivos JPEG (repetido) | um por item do manifest, **na mesma ordem** |

```jsonc
// manifest
{
  "device_id": "dev-001",
  "trip_id": "20261021T140000Z-dev-001",
  "segment_id": 1,
  "direction": "CAPITAL",              // "CAPITAL" | "INTERIOR" | null
  "stats": {                            // opcional: telemetria do aparelho
    "frames_seen": 300, "discarded_speed": 23, "saved": 60, "km_covered": 2.99
  },
  "frames": [
    { "capture_id": "20261021T140000Z-dev-001-000001",  // único por foto
      "captured_at": "2026-10-21T14:00:03.250Z",
      "lat": -22.9012, "lng": -47.0583,
      "km": 11.02,                      // opcional: se faltar, o servidor calcula
      "speed_kmh": 78.4, "green_percent": 31.2, "filename": "000001.jpg" }
  ]
}
```

**Resposta `202`:** `{ "sync_id": 12, "status": "PROCESSING", "received": 60, "duplicates": 0 }`

### `GET /edge/syncs/{sync_id}` e `GET /edge/syncs?device_id=&limit=`

Devolvem o andamento do lote (`PROCESSING`/`DONE`/`FAILED`, `failure_reason`,
`received`, `duplicates`, `frames_analyzed`, `inspection_id`, datas e `stats`).

## 6. Regras

1. **Idempotência.** A chave única de cada foto é `(device_id, capture_id)`. Uma foto
   repetida é **ignorada e contada** em `duplicates`; reenviar o lote inteiro não cria
   fotos nem inspeções novas (devolve o envio existente).
2. **Posição real.** `FrameAnalysis` ganha `lat`, `lng`, `captured_at` e `km` reais
   (nulos nas inspeções antigas). Se o `km` não vier, o servidor o calcula **projetando**
   `lat/lng` sobre `Road.geometry`; a interpolação por índice fica só para uploads
   antigos.
3. **Uma inspeção por lote**, com a `direction` do manifest. Os blocos de 0,5 km
   continuam derivados do `km` de cada foto.
4. **Assíncrono.** Responde 202 e classifica em segundo plano.
5. **Validação (422):** número de itens do manifest igual ao de arquivos; `capture_id`
   únicos no lote; `captured_at` em UTC com `Z`; `segment_id` existente; cada JPEG com
   até 15 MB; no máximo 500 fotos por lote (configurável).
6. **Autenticação do aparelho:** fora deste documento; depende da Parte E do plano.

## 7. Decisões a tomar quando chegar a hora

| # | Decisão | Proposta |
|---|---|---|
| 1 | Rota | `/edge/syncs` |
| 2 | Chave de idempotência | `(device_id, capture_id)` por foto |
| 3 | Uma inspeção por lote ou por trajeto | por lote (mais simples; o km real já separa os blocos) |
| 4 | Limite de fotos por lote | 500, configurável |
