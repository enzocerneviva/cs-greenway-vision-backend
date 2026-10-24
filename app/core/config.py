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
