"""Check live Open-Meteo ensemble member availability for Spiddal."""
import json
import requests

MODELS = {
    "ECMWF IFS": "ecmwf_ifs025_ensemble",
    "GFS GEFS": "ncep_gefs025",
    "ICON Europe": "dwd_icon_eu_eps",
    "ICON Global": "dwd_icon_global_eps",
    "GEM GEPS": "cmc_gem_geps",
    "UKMO Global": "ukmo_global_ensemble_20km",
    "UKMO UK": "ukmo_uk_ensemble_2km",
}
for label, model in MODELS.items():
    try:
        r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble",
            params={"latitude": 53.25, "longitude": -9.30,
                    "timezone": "Europe/Dublin", "forecast_days": 3,
                    "models": model,
                    "hourly": "precipitation,temperature_2m,wind_gusts_10m"},
            timeout=90)
        r.raise_for_status()
        h = r.json()["hourly"]
        result = {}
        for variable in ("precipitation", "temperature_2m", "wind_gusts_10m"):
            keys = [k for k in h if k.startswith(variable + "_member")]
            result[variable] = {"members": len(keys),
                "min_valid_hours": min((sum(v is not None for v in h[k]) for k in keys), default=0),
                "max_valid_hours": max((sum(v is not None for v in h[k]) for k in keys), default=0)}
        print(json.dumps({"model": label, "id": model, "status": "ok", "variables": result}))
    except (requests.RequestException, ValueError, KeyError) as e:
        print(json.dumps({"model": label, "id": model, "status": "error", "detail": str(e)[:250]}))
