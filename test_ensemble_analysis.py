import unittest
from ensemble_analysis import analyse_hourly, distribution

class EnsembleAnalysisTests(unittest.TestCase):
    def test_valid_denominator_and_control_exclusion(self):
        h = {"time": ["2026-11-05T00:00"]}
        for i in range(12):
            h[f"precipitation_member{i:02}"] = [2.0 if i < 6 else None]
        h["precipitation_control"] = [999.0]
        result = analyse_hourly(h)["hourly"][0]["precipitation"]
        self.assertEqual(result["valid_members"], 6)
        self.assertIsNone(result["probabilities"])

    def test_probabilities(self):
        result = distribution([0.0] * 5 + [6.0] * 5, (0.1, 5.0, 10.0))
        self.assertEqual(result["probabilities"], {"0.1": 50.0, "5.0": 50.0, "10.0": 0.0})

    def test_partial_day_suppressed(self):
        h = {"time": [f"2026-11-05T{i:02}:00" for i in range(12)]}
        for i in range(12):
            h[f"precipitation_member{i:02}"] = [1.0] * 12
        daily = analyse_hourly(h)["daily"][0]["rain_mm"]
        self.assertIsNone(daily["probabilities"])

    def test_incomplete_member_excluded_from_daily(self):
        h = {"time": [f"2026-11-05T{i:02}:00" for i in range(24)]}
        for i in range(12):
            h[f"precipitation_member{i:02}"] = [1.0] * (23 if i == 0 else 24)
        result = analyse_hourly(h)["daily"][0]["rain_mm"]
        self.assertEqual(result["valid_members"], 11)
        self.assertEqual(result["median"], 24.0)

if __name__ == "__main__":
    unittest.main()
