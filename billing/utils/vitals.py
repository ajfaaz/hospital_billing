def evaluate_vitals(v):
    alerts = {}

    # Blood Pressure
    if v.blood_pressure_systolic and v.blood_pressure_diastolic:
        if v.blood_pressure_systolic >= 180 or v.blood_pressure_diastolic >= 120:
            alerts["blood_pressure"] = "critical"
        elif v.blood_pressure_systolic >= 140 or v.blood_pressure_diastolic >= 90:
            alerts["blood_pressure"] = "high"
        else:
            alerts["blood_pressure"] = "normal"

    # Temperature
    if v.temperature:
        if v.temperature >= 39:
            alerts["temperature"] = "critical"
        elif v.temperature >= 37.5:
            alerts["temperature"] = "high"
        else:
            alerts["temperature"] = "normal"

    # Pulse
    if v.heart_rate:
        if v.heart_rate >= 130 or v.heart_rate <= 40:
            alerts["pulse"] = "critical"
        elif v.heart_rate >= 100:
            alerts["pulse"] = "high"
        else:
            alerts["pulse"] = "normal"

    # SpO2
    if v.spo2:
        if v.spo2 < 85:
            alerts["spo2"] = "critical"
        elif v.spo2 < 95:
            alerts["spo2"] = "high"
        else:
            alerts["spo2"] = "normal"

    return alerts
