"""Check that published forecast files are fresh and contain usable model data."""
import datetime as dt
import json
from pathlib import Path

MAX_AGE_HOURS = 8
EXPECTED_OPERATIONAL = 11
EXPECTED_ENSEMBLES = 7

def validate(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    problems = []
    for filename in ("data/latest.json", "data/ensemble_latest.json"):
        try:
            data = json.loads(Path(filename).read_text())
            stamp = dt.datetime.fromisoformat(data["retrieved_utc"].replace("Z", "+00:00"))
            age = (now - stamp).total_seconds() / 3600
            print(f"{filename}: age {age:.2f} hours; retrieved {stamp.isoformat()}")
            if age < -0.25 or age > MAX_AGE_HOURS:
                problems.append(f"{filename} is stale or timestamp invalid: age {age:.1f}h")
            if filename.endswith("ensemble_latest.json"):
                models = data["models"]
                if len(models) != EXPECTED_ENSEMBLES:
                    problems.append(f"Ensemble count {len(models)} vs {EXPECTED_ENSEMBLES}")
                for name in ("ECMWF IFS", "GFS GEFS"):
                    m = models.get(name, {})
                    usable = sum(day.get("rain_mm", {}).get("probabilities") is not None
                                 for day in m.get("daily", []))
                    print(f"{name}: status {m.get('status')}; usable daily rain forecasts {usable}")
                    if m.get("status") != "ok" or usable < 7:
                        problems.append(f"{name} has only {usable} usable rain days or failed")
            else:
                statuses = data.get("model_status", {})
                healthy = sum(v.get("status") == "ok" for v in statuses.values())
                print(f"Operational models: {healthy}/{EXPECTED_OPERATIONAL} successful")
                if healthy < 8:
                    problems.append(f"Only {healthy} operational models successful")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append(f"{filename}: {exc}")
    if problems:
        raise RuntimeError("Weather monitoring FAILED:\n" + "\n".join(problems))
    print("Weather monitoring PASSED")

if __name__ == "__main__":
    validate()
