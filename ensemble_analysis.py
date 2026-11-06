"""Ensemble probabilities and ranges for Spiddal; separate from live operational forecast."""
import datetime as dt
import json
import math
from pathlib import Path
import re
import statistics

import requests
from model_run_metadata import ENSEMBLE, collect

LAT, LON = 53.25, -9.30
MODELS = {
    "ECMWF IFS": "ecmwf_ifs025_ensemble",
    "GFS GEFS": "ncep_gefs025",
    "ICON Europe": "dwd_icon_eu_eps",
    "ICON Global": "dwd_icon_global_eps",
    "GEM GEPS": "cmc_gem_geps",
    "UKMO Global": "ukmo_global_ensemble_20km",
    "UKMO UK": "ukmo_uk_ensemble_2km",
}
VARIABLES = ("precipitation", "wind_gusts_10m")
FORECAST_DAYS = {"ECMWF IFS": 15, "GFS GEFS": 15}
DEFAULT_FORECAST_DAYS = 7
MIN_MEMBERS = 10
RAIN_THRESHOLDS_MM = (0.1, 1.0, 5.0, 10.0)
GUST_THRESHOLDS_KMH = (50, 70, 90)
# Member keys only; never count the control run or the ensemble mean.
MEMBER_PATTERN = re.compile(r"^(precipitation|wind_gusts_10m)_member([0-9]+)$")


def percentile(values, fraction):
    """Linearly interpolated percentile; requires nonempty finite values."""
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 2)


def distribution(values, thresholds):
    """Percentages always use the count of valid members as denominator."""
    if len(values) < MIN_MEMBERS:
        return {"valid_members": len(values), "probabilities": None,
                "p10": None, "median": None, "p90": None}
    return {
        "valid_members": len(values),
        "probabilities": {
            str(threshold): round(100 * sum(v >= threshold for v in values) / len(values), 1)
            for threshold in thresholds
        },
        "p10": percentile(values, .1),
        "median": percentile(values, .5),
        "p90": percentile(values, .9),
    }


def analyse_hourly(hourly):
    times = hourly["time"]
    series = {"precipitation": {}, "wind_gusts_10m": {}}
    for key, values in hourly.items():
        match = MEMBER_PATTERN.fullmatch(key)
        if match and isinstance(values, list):
            series[match.group(1)][match.group(2)] = values
    output = []
    for i, timestamp in enumerate(times):
        row = {"time": timestamp}
        for variable, thresholds in (
            ("precipitation", RAIN_THRESHOLDS_MM),
            ("wind_gusts_10m", GUST_THRESHOLDS_KMH),
        ):
            valid = [values[i] for values in series[variable].values()
                     if i < len(values) and isinstance(values[i], (int, float))
                     and math.isfinite(values[i]) and values[i] >= 0]
            row[variable] = distribution(valid, thresholds)
        output.append(row)
    daily = []
    for day in sorted({t[:10] for t in times}):
        indices = [i for i, t in enumerate(times) if t.startswith(day)]
        rain_totals = []
        gust_maxima = []
        for values in series["precipitation"].values():
            # Complete local calendar days only. Never interpret partial coverage as daily total.
            if all(i < len(values) and isinstance(values[i], (int, float))
                   and math.isfinite(values[i]) and values[i] >= 0 for i in indices):
                rain_totals.append(sum(values[i] for i in indices))
        for values in series["wind_gusts_10m"].values():
            if all(i < len(values) and isinstance(values[i], (int, float))
                   and math.isfinite(values[i]) and values[i] >= 0 for i in indices):
                gust_maxima.append(max(values[i] for i in indices))
        # First and last days may be partial calendar days, even if all returned hours are present.
        full_day = len(indices) in (23, 24, 25)
        daily.append({
            "date": day,
            "hours_in_response": len(indices),
            "rain_mm": distribution(rain_totals if full_day else [], RAIN_THRESHOLDS_MM),
            "max_gust_kmh": distribution(gust_maxima if full_day else [], GUST_THRESHOLDS_KMH),
        })
    return {"hourly": output, "daily": daily,
            "member_series": {v: len(members) for v, members in series.items()}}


def coverage(analysis):
    """Report actual usable complete-day probabilities, not merely requested days."""
    daily = analysis["daily"]
    result = {}
    for field in ("rain_mm", "max_gust_kmh"):
        usable = [day["date"] for day in daily
                  if day[field]["probabilities"] is not None]
        result[field] = {
            "usable_days": len(usable),
            "first_usable_date": usable[0] if usable else None,
            "last_usable_date": usable[-1] if usable else None,
            "unusable_dates": [day["date"] for day in daily
                               if day[field]["probabilities"] is None],
        }
    result["returned_hourly_steps"] = len(analysis["hourly"])
    result["returned_calendar_dates"] = len(daily)
    return result


def retrieve(model, forecast_days=DEFAULT_FORECAST_DAYS):
    response = requests.get(
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        params={"latitude": LAT, "longitude": LON,
                "timezone": "Europe/Dublin", "forecast_days": forecast_days,
                "models": model, "hourly": ",".join(VARIABLES)},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["hourly"]



def combine_gefs(high_res, extended):
    """Use 0.25-degree members first and 0.5-degree members for missing hours."""
    high_times = high_res["time"]
    low_indices = {t: i for i, t in enumerate(extended["time"])}
    if len(low_indices) != len(extended["time"]) or not set(high_times).issubset(low_indices):
        raise ValueError("Incompatible GEFS timestamps")
    combined = {"time": list(high_times)}
    provenance = {"ncep_gefs025_hours": 0, "ncep_gefs05_hours": 0, "missing_hours": 0}
    for key, high_values in high_res.items():
        if not MEMBER_PATTERN.fullmatch(key):
            continue
        low_values = extended.get(key)
        if not isinstance(low_values, list):
            raise ValueError("Missing extended GEFS member " + key)
        merged = []
        for i, timestamp in enumerate(high_times):
            j = low_indices[timestamp]
            hi = high_values[i] if i < len(high_values) else None
            lo = low_values[j] if j < len(low_values) else None
            if isinstance(hi, (int, float)) and math.isfinite(hi) and hi >= 0:
                merged.append(hi)
                provenance["ncep_gefs025_hours"] += 1
            elif isinstance(lo, (int, float)) and math.isfinite(lo) and lo >= 0:
                merged.append(lo)
                provenance["ncep_gefs05_hours"] += 1
            else:
                merged.append(None)
                provenance["missing_hours"] += 1
        combined[key] = merged
    return combined, provenance

def main():
    result = {"retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source": "Open-Meteo ensemble API", "latitude": LAT, "longitude": LON,
              "minimum_members_for_probabilities": MIN_MEMBERS,
              "note": "Model-relative member frequencies, not calibrated probabilities. "
                      "Daily figures require a complete local calendar day and valid member hours.",
              "models": {}, "model_run_metadata": collect(ENSEMBLE)}
    for label, model in MODELS.items():
        try:
            provenance = None
            if label == "GFS GEFS":
                high_res = retrieve(model, FORECAST_DAYS[label])
                extended = retrieve("ncep_gefs05", FORECAST_DAYS[label])
                combined, provenance = combine_gefs(high_res, extended)
                analysis = analyse_hourly(combined)
            else:
                analysis = analyse_hourly(retrieve(model, FORECAST_DAYS.get(label, DEFAULT_FORECAST_DAYS)))
            result["models"][label] = {"model_id": model, "forecast_days_requested": FORECAST_DAYS.get(label, DEFAULT_FORECAST_DAYS), "status": "ok", "coverage": coverage(analysis), **({"resolution_sources": {"primary": model, "extension": "ncep_gefs05", "priority": "0.25-degree values first", "value_counts": provenance}} if provenance is not None else {}), **analysis}
            print(label, "OK", analysis["member_series"],
                  "days_with_rain_probability",
                  sum(d["rain_mm"]["probabilities"] is not None for d in analysis["daily"]))
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            result["models"][label] = {"model_id": model, "forecast_days_requested": FORECAST_DAYS.get(label, DEFAULT_FORECAST_DAYS), "status": "error",
                                       "error": str(exc)[:250]}
            print(label, "ERROR", str(exc)[:250])
    if not any(v["status"] == "ok" and
               any(d["rain_mm"]["probabilities"] is not None for d in v["daily"])
               for v in result["models"].values()):
        raise RuntimeError("No usable ensemble forecasts; previous output retained")
    Path("data").mkdir(exist_ok=True)
    Path("data/ensemble_latest.json").write_text(json.dumps(result, indent=2))
    print("Saved data/ensemble_latest.json")


if __name__ == "__main__":
    main()
