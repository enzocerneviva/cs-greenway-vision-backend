import os

# Configuração central da aplicação. Cada valor tem um padrão pensado para
# desenvolvimento local; em outro ambiente dá pra sobrescrever com uma
# variável de ambiente, sem editar o código.

# Origens que o navegador pode usar pra chamar a API (CORS). Várias origens
# se separam por vírgula: CORS_ORIGINS="http://localhost:5173,https://meu.site"
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

# Fuso usado para "hoje" nas datas de agenda (os instantes da API são sempre UTC).
TIMEZONE = "America/Sao_Paulo"

# Tamanho de um bloco de rodovia, em km (ver plano da V2, "Conceitos").
BLOCK_SIZE_KM = 0.5

# Limites de upload.
MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB — imagem é bem menor que vídeo

# Libera o DELETE /inspections (apaga todas as análises). Ligado por padrão
# em desenvolvimento; desligar com ADMIN_RESET_ENABLED=false.
ADMIN_RESET_ENABLED = os.environ.get("ADMIN_RESET_ENABLED", "true").lower() == "true"

# Abaixo disto a confiança do classificador num frame é considerada "baixa"
# (o frontend sinaliza o frame). Escolhido na avaliação do Mapillary com
# validação por blocos: >= 0,6 mantém ~56 % dos frames com ~92 % de acerto.
# É um sinal relativo, não uma probabilidade — ver docs/plans/plano-v2.md, item 9.
LOW_CONFIDENCE_THRESHOLD = 0.6

# Imagem de exibição de cada frame analisado (a que o frontend mostra). O frame
# em resolução cheia só serve ao modelo e não é guardado.
FRAME_DISPLAY_MAX_WIDTH = 640
FRAME_JPEG_QUALITY = 80

# Apaga o arquivo ORIGINAL (vídeo/foto) depois de N dias; os frames reduzidos e
# os resultados ficam. Desligado por padrão (None) pra nunca apagar nada sem
# querer — ligar com VIDEO_RETENTION_DAYS=30, por exemplo.
_retention = os.environ.get("VIDEO_RETENTION_DAYS")
VIDEO_RETENTION_DAYS = int(_retention) if _retention else None

# --- Agenda e análise de dados (Parte D do plano V2) ------------------------
# Todos são valores FIXOS nesta versão; ficam aqui pra serem fáceis de achar e
# ajustar. (Uma tela de configurações pode vir depois.)

# Janela máxima de GET /schedule (o calendário em mês mostra até 42 dias).
SCHEDULE_MAX_WINDOW_DAYS = 93

# Verde (%) a partir do qual um bloco é tratado como "no nível crítico" na
# PREVISÃO de crescimento. Calibrado com data/mapillary/calibrate_critical_green.py:
# mediana do verde (detectar_vegetacao) das imagens rotuladas HIGH do dataset de
# treino. O verde é só o pré-filtro de cor; a prioridade vem do modelo — então
# isto é uma aproximação grosseira, usada só pra estimar tendência.
CRITICAL_GREEN_PERCENT = 13.7

# Crescimento só é estimado com leituras suficientes (depois da última roçada).
MIN_READINGS_FOR_GROWTH = 3
MIN_DAYS_FOR_GROWTH = 7

# Bloco sem leitura há mais que isto é considerado "desatualizado" (stale).
STALE_INSPECTION_DAYS = 30

# Intervalo máximo (dias) sem inspeção, conforme a prioridade da última leitura.
INSPECTION_MAX_DAYS = {"HIGH": 7, "MEDIUM": 15, "LOW": 30}

# Roçada sugerida pela previsão: antecedência (dias) em relação à data prevista
# de chegada ao nível crítico, e até onde olhar pra frente.
MOWING_LEAD_DAYS = 7
PREDICTION_HORIZON_DAYS = 45

# Sugestões: quantas devolver por padrão (e no máximo) e por quantos dias
# "Dispensar" esconde uma sugestão quando o cliente não informa `until`.
SUGGESTIONS_DEFAULT_LIMIT = 5
SUGGESTIONS_MAX_LIMIT = 20
DISMISS_DEFAULT_DAYS = 14

# Conclusão automática de eventos de inspeção.
AUTO_COMPLETE_MIN_COVERAGE = 0.8
AUTO_COMPLETE_DAYS_BEFORE = 3
