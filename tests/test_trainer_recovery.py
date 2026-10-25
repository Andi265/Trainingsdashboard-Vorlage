import unittest
from datetime import date, timedelta

import trainer
from tests.helpers import make_activity, make_day

TODAY = date(2026, 11, 10)
RULES = trainer.default_profile()["rest_rules"]


def iso(offset: int) -> str:
    return (TODAY - timedelta(days=offset)).isoformat()


def normal_day(**overrides) -> dict:
    values = dict(readiness=72, recovery_h=5, ratio=1.0, hrv=85, hrv_low=78, hrv_high=108, sleep=82, rhr=49,
                  rhr_avg=49)
    values.update(overrides)
    return make_day(**values)


def hit(result: dict, key: str) -> bool:
    return next(s for s in result["signals"] if s["key"] == key)["hit"]


class RecoveryAssessmentTests(unittest.TestCase):
    def test_signal_order(self):
        result = trainer.recovery_assessment({"days": {}, "activities": []}, TODAY, RULES)
        self.assertEqual([s["key"] for s in result["signals"]],
                         ["readiness", "recovery_time", "load_ratio", "hrv", "sleep", "resting_hr", "days_in_row"])

    def test_single_hard_session_is_not_rest(self):
        data = {"days": {iso(1): normal_day(readiness=75), iso(0): normal_day(readiness=45, recovery_h=30)},
                "activities": [make_activity(iso(1), te_aer=3.8, te_ana=2.5, benefit="vo2max", load=130)]}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertIn(result["decision"], ("easy", "train"))

    def test_three_signals_give_rest(self):
        data = {"days": {iso(2): normal_day(sleep=62),
                         iso(1): normal_day(readiness=46, sleep=65, rhr=52),
                         iso(0): normal_day(readiness=45, sleep=60, rhr=52)},
                "activities": [make_activity(iso(1))]}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertEqual(result["decision"], "rest")
        self.assertGreaterEqual(result["hits"], 3)
        self.assertFalse(result["alarm"])

    def test_rhr_and_hrv_alarm(self):
        data = {"days": {iso(0): normal_day(rhr=55, rhr_avg=49, hrv=60, hrv_low=78)}, "activities": []}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertEqual(result["decision"], "rest_now")
        self.assertIs(result["alarm"], True)

    def test_missing_data_never_counts(self):
        data = {"days": {iso(2): {}, iso(1): {}, iso(0): {}}, "activities": []}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["decision"], "train")

    def test_recovery_time_after_easy_day(self):
        data = {"days": {iso(1): normal_day(), iso(0): normal_day(recovery_h=30)},
                "activities": [make_activity(iso(1), te_aer=2.0, te_ana=0.0)]}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertTrue(hit(result, "recovery_time"))

    def test_days_in_row(self):
        data = {"days": {iso(0): normal_day()},
                "activities": [make_activity(iso(n)) for n in range(1, 7)]}
        result = trainer.recovery_assessment(data, TODAY, RULES)
        self.assertTrue(hit(result, "days_in_row"))

    def test_rules_are_configurable(self):
        data = {"days": {iso(1): normal_day(readiness=75), iso(0): normal_day(readiness=45, recovery_h=30)},
                "activities": [make_activity(iso(1), te_aer=3.8, te_ana=2.5, benefit="vo2max", load=130)]}
        result = trainer.recovery_assessment(data, TODAY, {**RULES, "readiness_low": 80})
        self.assertTrue(hit(result, "readiness"))


if __name__ == "__main__":
    unittest.main()
