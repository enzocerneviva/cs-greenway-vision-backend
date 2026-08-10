LOW_THRESHOLD_CM = 10
HIGH_THRESHOLD_CM = 30


def classify_priority(measurement_value: float) -> str:
    if measurement_value < LOW_THRESHOLD_CM:
        return "LOW"
    elif measurement_value <= HIGH_THRESHOLD_CM:
        return "MEDIUM"
    else:
        return "HIGH"
