# Limites de classificação, em percentual de vegetação detectada.
# Ajustáveis conforme o projeto for calibrado com mais dados reais.
LIMITE_BAIXA = 20
LIMITE_MEDIA = 40


def classificar_percentual(percentual: float) -> str:
    """
    Recebe um percentual de vegetação (0 a 100) e retorna a
    classificação de criticidade correspondente.
    """
    if percentual < LIMITE_BAIXA:
        return "Baixa"
    elif percentual < LIMITE_MEDIA:
        return "Média"
    else:
        return "Alta"