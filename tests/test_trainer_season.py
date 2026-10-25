import copy
import json
import unittest

import trainer


def phase(name, focus, start, end, strength="off"):
    return {"name": name, "focus": focus, "start": start, "end": end, "strength_phase": strength}


def event_profile(priority="A"):
    p = copy.deepcopy(trainer.default_profile())
    p["goal"] = {"type": "event", "event": {"name": "Ötztaler", "date": "2027-06-06", "priority": priority,
                                            "distance_km": 160, "elevation_m": 3000}}
    return p


def event_season(taper_start, taper_end):
    return {"created": "2027-03-01", "phases": [
        phase("Aufbau", "build", "2027-03-01", (trainer.date.fromisoformat(taper_start)
                                                 - trainer.timedelta(days=1)).isoformat()),
        phase("Tapering", "taper", taper_start, taper_end),
        phase("Wettkampf", "race", (trainer.date.fromisoformat(taper_end) + trainer.timedelta(days=1)).isoformat(),
              "2027-06-07")]}


class SeasonCheckTests(unittest.TestCase):
    def test_gap_rejected(self):
        season = {"created": "2026-11-01", "phases": [phase("A", "base", "2026-11-01", "2026-11-10"),
                                                      phase("B", "build", "2026-11-12", "2026-11-20")]}
        errors = trainer.check_season(season, trainer.default_profile())
        self.assertTrue(any("Lücke" in e for e in errors), errors)

    def test_overlap_rejected(self):
        season = {"created": "2026-11-01", "phases": [phase("A", "base", "2026-11-01", "2026-11-10"),
                                                      phase("B", "build", "2026-11-10", "2026-11-20")]}
        errors = trainer.check_season(season, trainer.default_profile())
        self.assertTrue(any("überschneid" in e for e in errors), errors)

    def test_phase_before_created_rejected(self):
        season = {"created": "2026-11-15", "phases": [phase("A", "base", "2026-11-01", "2026-11-10"),
                                                      phase("B", "build", "2026-11-11", "2026-11-30")]}
        self.assertTrue(trainer.check_season(season, trainer.default_profile()))

    def test_phase_without_name_rejected(self):
        unnamed = phase("A", "base", "2026-11-01", "2026-11-10")
        del unnamed["name"]
        errors = trainer.check_season({"created": "2026-11-01", "phases": [unnamed]}, trainer.default_profile())
        self.assertTrue(any("Namen" in e for e in errors), errors)

    def test_unknown_focus_rejected(self):
        season = {"created": "2026-11-01", "phases": [phase("A", "yoga", "2026-11-01", "2026-11-10")]}
        self.assertTrue(trainer.check_season(season, trainer.default_profile()))

    def test_event_needs_taper_before_race(self):
        season = event_season("2027-05-23", "2027-06-01")
        self.assertTrue(trainer.check_season(season, event_profile()))

    def test_event_taper_length(self):
        self.assertTrue(trainer.check_season(event_season("2027-06-02", "2027-06-05"), event_profile()))
        self.assertEqual(trainer.check_season(event_season("2027-05-27", "2027-06-05"), event_profile()), [])
        self.assertEqual(trainer.check_season(event_season("2027-06-03", "2027-06-05"), event_profile("B")), [])

    def test_strength_phase_off_when_disabled(self):
        season = {"created": "2026-11-01", "phases": [phase("A", "base", "2026-11-01", "2026-11-10", "max")]}
        self.assertTrue(trainer.check_season(season, trainer.default_profile()))

    def test_saved_season_is_valid(self):
        """The real season plan must pass the checks with the real profile (it grows with every extension)."""
        season = trainer.load_season()
        if not season.get("phases"):
            self.skipTest("No season plan yet: it is created by the settings dialog ('Training einrichten').")
        self.assertEqual(trainer.check_season(season, trainer.load_profile()), [])


if __name__ == "__main__":
    unittest.main()
