import copy
import unittest

import trainer

LIBRARY = {"base_z2_60": {}, "base_z2_90": {}, "base_long": {}, "base_z2_spinups": {}, "vo2_5x4": {},
           "vo2_30_15": {}, "vo2_6x3": {}, "run_vo2": {"sport": "running"}, "str_x": {"sport": "strength"}}


def day(date, kind, session=None, minutes=60, sport="cycling"):
    if kind in ("rest", "rest_expected"):
        return {"date": date, "sport": "rest", "session": None, "kind": kind, "duration_min": 0, "reason": "",
                "status": "planned"}
    return {"date": date, "sport": sport, "session": session, "kind": kind, "duration_min": minutes, "reason": "",
            "status": "planned"}


def valid_schedule() -> dict:
    return {"created": "2026-11-01", "days": [
        day("2026-11-02", "easy", "base_z2_60"), day("2026-11-03", "key", "vo2_5x4"),
        day("2026-11-04", "easy", "base_z2_60"), day("2026-11-05", "rest_expected"),
        day("2026-11-06", "key", "vo2_30_15"), day("2026-11-07", "long", "base_long", 180),
        day("2026-11-08", "easy", "base_z2_90", 90), day("2026-11-09", "rest"),
        day("2026-11-10", "normal", "base_z2_spinups")]}


def profile(**changes) -> dict:
    p = copy.deepcopy(trainer.default_profile())
    for path, value in changes.items():
        node = p
        keys = path.split("__")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return p


def replace(schedule: dict, date: str, new_day: dict) -> dict:
    s = copy.deepcopy(schedule)
    s["days"] = [new_day if d["date"] == date else d for d in s["days"]]
    return s


class ScheduleCheckTests(unittest.TestCase):
    def check(self, schedule, p=None):
        return trainer.check_schedule(schedule, p or trainer.default_profile(), LIBRARY)

    def test_valid_schedule_passes(self):
        self.assertEqual(self.check(valid_schedule()), [])

    def test_two_sessions_same_day(self):
        s = valid_schedule()
        s["days"].append(day("2026-11-02", "easy", "base_z2_60"))
        self.assertTrue(self.check(s))

    def test_fixed_rest_day_used(self):
        p = profile(availability__rest_days={"mode": "fixed", "days": ["mon"], "min_per_cycle": 1})
        self.assertTrue(self.check(valid_schedule(), p))

    def test_long_only_on_long_days(self):
        p = profile(availability__long_days=[{"day": "sun", "sport": "cycling", "max_h": 4}])
        errors = self.check(valid_schedule(), p)
        self.assertTrue(any("2026-11-07" in e for e in errors), errors)

    def test_long_any_day_when_no_long_days(self):
        self.assertEqual(self.check(valid_schedule(), profile(availability__long_days=[])), [])

    def test_consecutive_keys_same_sport(self):
        s = replace(valid_schedule(), "2026-11-04", day("2026-11-04", "key", "vo2_6x3"))
        self.assertTrue(self.check(s))

    def test_consecutive_keys_different_sports_ok(self):
        p = profile(sports=["cycling", "running"])
        s = replace(valid_schedule(), "2026-11-04", day("2026-11-04", "key", "run_vo2", sport="running"))
        self.assertEqual(self.check(s, p), [])

    def test_strength_disabled_rejected(self):
        s = replace(valid_schedule(), "2026-11-04", day("2026-11-04", "strength", "str_x", sport="strength"))
        self.assertTrue(self.check(s, profile(sports=["cycling", "strength"])))

    def test_strength_before_key_rejected(self):
        p = profile(sports=["cycling", "strength"], strength__enabled=True, strength__confirmed_at="2026-11-01")
        s = replace(valid_schedule(), "2026-11-02", day("2026-11-02", "strength", "str_x", 45, sport="strength"))
        errors = self.check(s, p)
        self.assertTrue(any("2026-11-02" in e for e in errors), errors)
        ok = replace(valid_schedule(), "2026-11-04", day("2026-11-04", "strength", "str_x", 45, sport="strength"))
        self.assertEqual(self.check(ok, p), [])

    def test_unknown_session(self):
        s = replace(valid_schedule(), "2026-11-02", day("2026-11-02", "easy", "nope"))
        self.assertTrue(self.check(s))

    def test_session_sport_must_match(self):
        p = profile(sports=["cycling", "running"])
        s = replace(valid_schedule(), "2026-11-02", day("2026-11-02", "easy", "run_vo2", sport="cycling"))
        self.assertTrue(self.check(s, p))

    def test_min_rest_per_cycle(self):
        s = replace(valid_schedule(), "2026-11-05", day("2026-11-05", "easy", "base_z2_60"))
        s = replace(s, "2026-11-09", day("2026-11-09", "easy", "base_z2_60"))
        self.assertTrue(self.check(s))

    def test_duration_over_budget(self):
        s = replace(valid_schedule(), "2026-11-02", day("2026-11-02", "easy", "base_z2_60", 120))
        self.assertTrue(self.check(s))

    def test_zero_hours_only_rest(self):
        hours = dict(trainer.default_profile()["availability"]["hours"], mon=0)
        self.assertTrue(self.check(valid_schedule(), profile(availability__hours=hours)))

    def test_set_day_returns_copy(self):
        s = valid_schedule()
        changed = trainer.set_day(s, "2026-11-03", status="changed", reason="Bereitschaft 45")
        self.assertEqual(changed["days"][1]["status"], "changed")
        self.assertEqual(changed["days"][1]["reason"], "Bereitschaft 45")
        self.assertEqual(s["days"][1]["status"], "planned")
        with self.assertRaises(KeyError):
            trainer.set_day(s, "2026-11-03", colour="red")
        with self.assertRaises(KeyError):
            trainer.set_day(s, "2030-01-01", status="done")


if __name__ == "__main__":
    unittest.main()
