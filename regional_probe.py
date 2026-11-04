"""Check regional model coverage and variable availability for Spiddal.

Run on a test branch before adding models to the production forecast.
"""
import json
import requests

URL = "https://api.open-meteo.com/v1/forecast"
MODELS = {
    "UKMO Global 10 km": "ukmo_global_deterministic_10km",
    "UKMO UKV 2 km": "ukmo_uk_deterministic_2km",
    "ICON-EU": "icon_eu",
    "ARPEGE Europe": "meteofrance_arpege_europe",
    "DMI HARMONIE Europe": "dmi_harmonie_arome_europe",
    "KNMI HARMONIE Europe": "knmi_harmonie_arome_europe",
}
VARIABLES = ["temperature_2m", "precipitation", "wind_gusts_10m"]

for label, model in MODELS.items():
    try:
        response = requests.get(
            URL,
            params={
                "latitude": 53.25,
                "longitude": -9.30,
                "timezone": "Europe/Dublin",
                "forecast_days": 3,
                "models": model,
                "hourly": ",".join(VARIABLES),
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
        report = {}
        for variable in VARIABLES:
            key = next((k for k in hourly if k == variable or k.startswith(variable + "_")), None)
            values = hourly.get(key, []) if key else []
            report[variable] = {
                "non_null_hours": sum(v is not None for v in values),
                "first_non_null": next((i for i, v in enumerate(values) if v is not None), None),
            }
        print(json.dumps({"model": label, "id": model, "status": "ok", "variables": report}))
    except (requests.RequestException, ValueError) as exc:
        print(json.dumps({"model": label, "id": model, "status": "error", "detail": str(exc)[:350]}))
