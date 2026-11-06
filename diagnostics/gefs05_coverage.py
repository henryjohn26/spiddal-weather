"""Isolated GEFS 0.5-degree 15-day coverage diagnostic. No production writes."""
import json
import math
from collections import defaultdict
import requests

URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
VARIABLES = ("precipitation", "wind_gusts_10m")
MODELS = ("ncep_gefs025", "ncep_gefs05")
results = {}
for model in MODELS:
    response = requests.get(URL, params={
        "latitude": 53.25, "longitude": -9.30, "timezone": "Europe/Dublin",
        "models": model, "hourly": ",".join(VARIABLES), "forecast_days": 15
    }, timeout=120)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    dates = defaultdict(list)
    for i, timestamp in enumerate(hourly["time"]):
        dates[timestamp[:10]].append(i)
    model_result = {}
    for variable in VARIABLES:
        members = {k: v for k, v in hourly.items()
                   if k.startswith(variable + "_member") and isinstance(v, list)}
        days = {}
        for date, indices in dates.items():
            complete_day = len(indices) in (23, 24, 25)
            valid = []
            for series in members.values():
                if complete_day and all(i < len(series)
                        and isinstance(series[i], (int, float))
                        and math.isfinite(series[i]) and series[i] >= 0 for i in indices):
                    valid.append(sum(series[i] for i in indices) if variable == "precipitation"
                                 else max(series[i] for i in indices))
            valid.sort()
            days[date] = {
                "hours": len(indices), "valid_members": len(valid),
                "median": valid[len(valid)//2] if valid else None,
                "minimum": valid[0] if valid else None,
                "maximum": valid[-1] if valid else None,
            }
        model_result[variable] = {"returned_member_series": len(members), "days": days}
    results[model] = model_result

print(json.dumps(results, indent=2))
for variable in VARIABLES:
    baseline = results["ncep_gefs025"][variable]["days"]
    candidate = results["ncep_gefs05"][variable]["days"]
    extended = [(day, row["valid_members"]) for day, row in candidate.items()
                if day in baseline and baseline[day]["valid_members"] < 10]
    print(f"{variable}: extended candidate daily member counts: {extended}")
    assert sum(row["valid_members"] >= 10 for row in candidate.values()) >= 14, (
        f"0.5-degree {variable} does not provide 14 complete usable calendar days")
print("PASS: ncep_gefs05 has at least 14 complete days for both variables")
