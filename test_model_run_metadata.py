import datetime as dt
import unittest
from unittest.mock import Mock
from model_run_metadata import lookup, OPERATIONAL, ENSEMBLE

NOW = dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc)
def session(payload=None, error=None):
    r=Mock()
    r.raise_for_status.side_effect=error
    r.json.return_value=payload or {}
    s=Mock()
    s.get.return_value=r
    return s

class TestMetadata(unittest.TestCase):
    def test_current_is_provider_reported_not_verified(self):
        value=lookup("test",NOW,session({"last_run_initialisation_time":int(NOW.timestamp())-21600,
                    "last_run_availability_time":int(NOW.timestamp())-18000}))
        self.assertEqual(value["status"],"provider_reported_current")
        self.assertFalse(value["run_time_verified"])
        self.assertEqual(value["model_run_utc"],"2026-11-04T06:00:00+00:00")
    def test_stale_is_not_published_as_current(self):
        value=lookup("test",NOW,session({"last_run_initialisation_time":int(NOW.timestamp())-86400*30}))
        self.assertEqual(value["status"],"stale_or_invalid")
        self.assertIsNone(value["model_run_utc"])
    def test_future_is_not_current(self):
        value=lookup("test",NOW,session({"last_run_initialisation_time":int(NOW.timestamp())+7200}))
        self.assertEqual(value["status"],"stale_or_invalid")
    def test_missing_mapping(self):
        self.assertEqual(lookup(None)["reason"],"no_validated_metadata_mapping")
    def test_missing_field(self):
        self.assertEqual(lookup("test",NOW,session({}))["status"],"unavailable")
    def test_request_failure_does_not_raise(self):
        from requests import HTTPError
        self.assertEqual(lookup("test",NOW,session(error=HTTPError("404")))["status"],"unavailable")
    def test_all_expected_mappings(self):
        self.assertEqual(len(OPERATIONAL),11)
        self.assertEqual(len(ENSEMBLE),7)
        self.assertIsNone(OPERATIONAL["gem_global"])
        self.assertEqual(ENSEMBLE["ICON Global"],"dwd_icon_global_eps_native")
        self.assertEqual(ENSEMBLE["ICON Europe"],"dwd_icon_eu_eps_native")

if __name__=="__main__":
    unittest.main()
