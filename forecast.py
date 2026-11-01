import datetime as dt
import html
import json
from pathlib import Path
import requests

LAT, LON = 53.25, -9.30
MODELS = ['ecmwf_ifs025', 'gfs_global', 'icon_global', 'gem_global', 'meteofrance_arpege_world']
PARAMS = {
    'latitude': LAT, 'longitude': LON, 'timezone': 'Europe/Dublin',
    'forecast_days': 7, 'models': ','.join(MODELS),
    'hourly': 'temperature_2m,precipitation,wind_gusts_10m',
}

def retrieve():
    r = requests.get('https://api.open-meteo.com/v1/forecast', params=PARAMS, timeout=90)
    r.raise_for_status()
    return r.json()

def main():
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    data = retrieve()
    Path('data').mkdir(exist_ok=True)
    Path('data/latest.json').write_text(json.dumps({'retrieved_utc': now, 'source': 'Open-Meteo', 'response': data}, indent=2))
    hourly = data['hourly']
    dates = sorted(set(t[:10] for t in hourly['time']))
    rows = []
    for date in dates:
        indices = [i for i, t in enumerate(hourly['time']) if t.startswith(date)]
        for model in MODELS:
            def values(name):
                key = f'{name}_{model}'
                return [hourly[key][i] for i in indices if key in hourly and hourly[key][i] is not None]
            rain, gust, temp = values('precipitation'), values('wind_gusts_10m'), values('temperature_2m')
            rows.append((date, model, f'{sum(rain):.1f}' if rain else 'n/a', f'{max(gust):.0f}' if gust else 'n/a', f'{max(temp):.1f}' if temp else 'n/a'))
    tr = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in row) + '</tr>' for row in rows)
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Spiddal weather models</title><style>body{{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;color:#17202a}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}}tr:nth-child(even){{background:#f6f8fa}}.scroll{{overflow-x:auto}}</style></head><body><h1>Spiddal multi-model weather</h1><p>Retrieved (UTC): {html.escape(now)}. Coordinates: {LAT}, {LON}. Source: Open-Meteo. Daily values are calculated from hourly data, using local dates. Model availability and update times can vary; retrieval time is not the model initialization time.</p><p>Rain = daily sum (mm); gust = daily maximum (km/h); temperature = daily maximum (°C).</p><div class="scroll"><table><thead><tr><th>Date</th><th>Model</th><th>Rain mm</th><th>Gust km/h</th><th>Max °C</th></tr></thead><tbody>{tr}</tbody></table></div><p><a href="data/latest.json">Full hourly data (JSON)</a></p></body></html>'''
    Path('index.html').write_text(page)
    print('Updated', now, 'rows', len(rows))

if __name__ == '__main__':
    main()
