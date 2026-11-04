"""Fetch and publish operational model forecasts for Spiddal."""
import datetime as dt
import html
import json
from pathlib import Path

import requests
from model_run_metadata import OPERATIONAL, collect

LAT, LON = 53.25, -9.30
MODELS = {
    "ecmwf_ifs025": "ECMWF IFS",
    "gfs_global": "GFS Global",
    "icon_global": "ICON Global",
    "gem_global": "GEM Global",
    "meteofrance_arpege_world": "ARPEGE World",
    "ukmo_global_deterministic_10km": "UKMO Global",
    "ukmo_uk_deterministic_2km": "UKMO UKV",
    "icon_eu": "ICON Europe",
    "meteofrance_arpege_europe": "ARPEGE Europe",
    "dmi_harmonie_arome_europe": "DMI HARMONIE Europe",
    "knmi_harmonie_arome_europe": "KNMI HARMONIE Europe",
}
VARIABLES = ("temperature_2m", "precipitation", "wind_gusts_10m")


def retrieve():
    """Request models separately so a failing model cannot hide the others."""
    hourly = {"time": []}
    model_status = {}
    all_times = set()
    responses = {}
    for model in MODELS:
        try:
            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": LAT, "longitude": LON,
                    "timezone": "Europe/Dublin", "forecast_days": 7,
                    "models": model, "hourly": ",".join(VARIABLES),
                },
                timeout=90,
            )
            response.raise_for_status()
            data = response.json()["hourly"]
            if not data.get("time"):
                raise ValueError("No hourly times returned")
            responses[model] = data
            all_times.update(data["time"])
            model_status[model] = {"status": "ok", "hours": len(data["time"]), "valid_hours": {v: sum(x is not None for x in data.get(next((k for k in data if k == v or k == f"{v}_{model}"), ""), [])) for v in VARIABLES}}
        except (requests.RequestException, ValueError, KeyError) as exc:
            model_status[model] = {"status": "error", "detail": str(exc)[:200]}
    if not responses:
        raise RuntimeError("All model requests failed; preserving previous forecast")
    hourly["time"] = sorted(all_times)
    for model, data in responses.items():
        index = {t: i for i, t in enumerate(data["time"])}
        for variable in VARIABLES:
            source_key = next(
                (k for k in data if k == variable or k == f"{variable}_{model}"),
                None,
            )
            values = data.get(source_key, []) if source_key else []
            hourly[f"{variable}_{model}"] = [
                values[index[t]] if t in index and index[t] < len(values) else None
                for t in hourly["time"]
            ]
    return {"latitude": LAT, "longitude": LON, "timezone": "Europe/Dublin",
            "hourly": hourly}, model_status


def main():
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data, status = retrieve()
    hourly = data["hourly"]
    dates = sorted({t[:10] for t in hourly["time"]})
    rows = []
    for date in dates:
        indices = [i for i, t in enumerate(hourly["time"]) if t.startswith(date)]
        for model, label in MODELS.items():
            if status[model]["status"] != "ok":
                continue
            def observed(variable):
                series = hourly.get(f"{variable}_{model}", [])
                return [(i, series[i]) for i in indices if i < len(series) and series[i] is not None]
            rain = observed("precipitation")
            gust = observed("wind_gusts_10m")
            temp = observed("temperature_2m")
            # Do not display partial-day precipitation as a full daily total.
            covered = {i for i, _ in rain}
            full_day = len(covered) == len(indices)
            if not (rain or gust or temp):
                continue
            rainfall = f"{sum(v for _, v in rain):.1f}" if full_day else "partial / n/a"
            gust_max = f"{max(v for _, v in gust):.0f}" if gust else "n/a"
            temp_max = f"{max(v for _, v in temp):.1f}" if temp else "n/a"
            coverage = f"{len(covered)}/{len(indices)}"
            rows.append((date, label, rainfall, gust_max, temp_max, coverage))
    tr = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>" for row in rows)
    errors = [f"{MODELS[m]}: {s['detail']}" for m, s in status.items() if s["status"] != "ok"]
    notice = "<p>Unavailable models: " + html.escape("; ".join(errors)) + "</p>" if errors else ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Spiddal weather models</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}}
tr:nth-child(even){{background:#f6f8fa}}.scroll{{overflow-x:auto}}</style></head>
<body><h1>Spiddal multi-model weather</h1><p><a href="ensemble.html">View ensemble probability dashboard</a></p>
<p>Retrieved (UTC): {html.escape(now)}. Coordinates: {LAT}, {LON}. Source: Open-Meteo.
Retrieval time is not the model initialization time.</p>
<p>Rain = complete local calendar-day total (mm); gust = maximum (km/h);
temperature = maximum (°C). Coverage = available rainfall hours / hours in day.
Partial-day rain totals are suppressed; shorter-range models are omitted after their data ends.
Maximum gust and temperature may be based on partial-day coverage; check the hourly JSON.</p>
{notice}<div class="scroll"><table><thead><tr><th>Date</th><th>Model</th><th>Rain mm</th>
<th>Gust km/h</th><th>Max °C</th><th>Coverage</th></tr></thead><tbody>{tr}</tbody></table></div>
<p><a href="data/latest.json">Full hourly data (JSON)</a></p></body></html>"""
    Path("data").mkdir(exist_ok=True)
    Path("data/latest.json").write_text(json.dumps({
        "retrieved_utc": now, "source": "Open-Meteo",
        "models": MODELS, "model_status": status, "response": data,
        "model_run_metadata": collect(OPERATIONAL),
    }, indent=2))
    Path("index.html").write_text(page)
    print("Updated", now, "rows", len(rows), "models_ok",
          sum(s["status"] == "ok" for s in status.values()))
    for model, s in status.items():
        print(model, json.dumps(s))


if __name__ == "__main__":
    main()
