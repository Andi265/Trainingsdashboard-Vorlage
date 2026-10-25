import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path

import trainer


def profile(**changes) -> dict:
    p = copy.deepcopy(trainer.default_profile())
    for path, value in changes.items():
        node = p
        keys = path.split("__")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return p


class ProfileTests(unittest.TestCase):
    def test_default_profile_is_valid(self):
        self.assertEqual(trainer.validate_profile(trainer.default_profile()), [])

    def test_unknown_sport_rejected(self):
        errors = trainer.validate_profile(profile(sports=["rowing"]))
        self.assertEqual(len(errors), 1)
        self.assertIn("rowing", errors[0])

    def test_strength_needs_confirmation(self):
        errors = trainer.validate_profile(profile(strength__enabled=True, strength__confirmed_at=None))
        self.assertTrue(errors)

    def test_fixed_rest_days_need_days(self):
        errors = trainer.validate_profile(profile(availability__rest_days={"mode": "fixed", "days": [],
                                                                          "min_per_cycle": 1}))
        self.assertTrue(errors)

    def test_event_goal_needs_name_and_date(self):
        errors = trainer.validate_profile(profile(goal={"type": "event", "event": {}}))
        self.assertGreaterEqual(len(errors), 2)

    def test_distance_and_elevation_must_be_numbers(self):
        event = {"name": "Ötztaler", "date": "2027-08-29", "priority": "A", "distance_km": 227, "elevation_m": 5500}
        self.assertEqual(trainer.validate_profile(profile(goal={"type": "event", "event": event})), [])
        tri = dict(event, distance_km={"swimming": 1.5, "cycling": 40, "running": 10})
        self.assertEqual(trainer.validate_profile(profile(goal={"type": "event", "event": tri})), [])
        for bad in (dict(event, elevation_m="ca. 5500"), dict(event, distance_km="227 km"),
                    dict(event, distance_km={"cycling": "40"})):
            errors = trainer.validate_profile(profile(goal={"type": "event", "event": bad}))
            self.assertTrue(any("Zahl" in e for e in errors), (bad, errors))
        discipline = {"sport": "cycling", "focus": "climbing", "distance_km": 120, "elevation_m": "viel"}
        errors = trainer.validate_profile(profile(goal={"type": "discipline", "discipline": discipline}))
        self.assertTrue(any("Zahl" in e for e in errors), errors)

    def test_triathlon_sets_sports(self):
        errors = trainer.validate_profile(profile(multisport="triathlon", sports=["cycling"]))
        text = " ".join(errors)
        self.assertIn("running", text)
        self.assertIn("swimming", text)

    def test_long_day_names(self):
        errors = trainer.validate_profile(profile(
            availability__long_days=[{"day": "samstag", "sport": "cycling", "max_h": 4}]))
        self.assertTrue(errors)


class SeasonAndCountdownTests(unittest.TestCase):
    SEASON = {"created": "2026-10-12", "phases": [
        {"name": "VO2max-Block", "focus": "vo2max", "start": "2026-10-12", "end": "2026-11-01"},
        {"name": "Entlastungswoche", "focus": "recovery", "start": "2026-11-02", "end": "2026-11-08"}]}

    def test_season_phase_lookup(self):
        phase = trainer.season_phase(self.SEASON, date(2026, 10, 20))
        self.assertEqual(phase["name"], "VO2max-Block")
        self.assertEqual(phase["days_left"], 12)
        self.assertEqual(phase["day_in_phase"], 9)
        self.assertEqual(phase["next_name"], "Entlastungswoche")
        self.assertIsNone(trainer.season_phase(self.SEASON, date(2026, 11, 9)))

    def test_countdown_event(self):
        p = profile(goal={"type": "event", "event": {"name": "Ötztaler", "date": "2027-06-06",
                                                     "distance_km": 160, "elevation_m": 3000, "priority": "A"}})
        cd = trainer.countdown(p, date(2027, 6, 1))
        self.assertEqual(cd["days"], 5)
        self.assertEqual(cd["elevation_m"], 3000)
        self.assertIsNone(trainer.countdown(trainer.default_profile(), date(2027, 6, 1)))

    def test_load_profile_missing_file_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(trainer.load_profile(Path(tmp)), trainer.default_profile())


class IsHardTests(unittest.TestCase):
    def test_is_hard_rule(self):
        self.assertTrue(trainer.is_hard({"primary_benefit": "vo2max"}))
        self.assertTrue(trainer.is_hard({"anaerobic_te": 2.0}))
        self.assertTrue(trainer.is_hard({"aerobic_te": 4.0}))
        self.assertFalse(trainer.is_hard({"primary_benefit": "aerobic base", "aerobic_te": 2.5, "anaerobic_te": 0.3}))


if __name__ == "__main__":
    unittest.main()
