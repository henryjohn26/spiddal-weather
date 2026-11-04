"""Optional provider-reported model run metadata; never infer the forecast API's actual run."""
import datetime as dt
import requests

# Identifiers validated by the isolated GitHub diagnostics, 4 November 2026.
# None means no trustworthy current mapping was established.
OPERATIONAL = {
    "ecmwf_ifs025": "ecmwf_ifs025",
    "gfs_global": "ncep_gfs025",
    "icon_global": "dwd_icon",
    "gem_global": None,
    "meteofrance_arpege_world": "meteofrance_arpege_world025",
    "ukmo_global_deterministic_10km": "ukmo_global_deterministic_10km",
    "ukmo_uk_deterministic_2km": "ukmo_uk_deterministic_2km",
    "icon_eu": "dwd_icon_eu",
    "meteofrance_arpege_europe": "meteofrance_arpege_europe",
    "dmi_harmonie_arome_europe": "dmi_harmonie_arome_europe",
    "knmi_harmonie_arome_europe": "knmi_harmonie_arome_europe",
}
ENSEMBLE = {
    "ECMWF IFS": "ecmwf_ifs025_ensemble",
    "GFS GEFS": "ncep_gefs025",
    "ICON Europe": "dwd_icon_eu_eps_native",
    "ICON Global": "dwd_icon_global_eps_native",
    "GEM GEPS": "cmc_gem_geps",
    "UKMO Global": "ukmo_global_ensemble_20km",
    "UKMO UK": "ukmo_uk_ensemble_2km",
}
MAX_AGE_HOURS = 48


def _iso(epoch):
    if not isinstance(epoch, (int, float)):
        return None
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat()


def lookup(storage_id, now=None, session=None):
    """Never fail weather collection because of optional metadata."""
    result = {
        "metadata_identifier": storage_id,
        "source": "Open-Meteo model metadata",
        "run_identification": "provider_reported_latest_not_forecast_response_verified",
        "model_run_utc": None,
        "model_available_utc": None,
        "model_modified_utc": None,
        "run_time_verified": False,
        "status": "unavailable",
    }
    if not storage_id:
        result["reason"] = "no_validated_metadata_mapping"
        return result
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        http = session or requests
        response = http.get(
            f"https://api.open-meteo.com/data/{storage_id}/static/meta.json",
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        epoch = payload.get("last_run_initialisation_time")
        if not isinstance(epoch, (int, float)):
            result["reason"] = "missing_initialisation_time"
            return result
        age_hours = (now - dt.datetime.fromtimestamp(epoch, dt.timezone.utc)).total_seconds() / 3600
        result["age_hours"] = round(age_hours, 2)
        result["model_available_utc"] = _iso(payload.get("last_run_availability_time"))
        result["model_modified_utc"] = _iso(payload.get("last_run_modification_time"))
        if age_hours < -1 or age_hours > MAX_AGE_HOURS:
            result["status"] = "stale_or_invalid"
            result["reason"] = "initialisation_outside_48h_window"
            return result
        result["model_run_utc"] = _iso(epoch)
        result["status"] = "provider_reported_current"
        # Intentionally false: the numerical API response does not identify its run.
        return result
    except (requests.RequestException, ValueError, TypeError, OverflowError, OSError) as exc:
        result["reason"] = "metadata_request_failed"
        result["error_type"] = type(exc).__name__
        return result


def collect(mapping, now=None, session=None):
    return {name: lookup(storage_id, now=now, session=session)
            for name, storage_id in mapping.items()}
