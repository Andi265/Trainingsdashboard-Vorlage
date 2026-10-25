import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import briefing
import trainer
import workouts
from tests.helpers import make_activity, make_day

DAY = date(2026, 10, 27)
LIBRARY = trainer.load_sessions()

SEASON = {"created": "2026-10-12", "phases": [
    {"name": "VO2max-Block", "focus": "vo2max", "start": "2026-10-12", "end": "2026-11-01", "key_sessions": [],
     "key_per_cycle": [2], "strength_phase": "off"},
    {"name": "Entlastungswoche", "focus": "recovery", "start": "2026-11-02", "end": "2026-11-08", "key_sessions": [],
     "key_per_cycle": [1], "strength_phase": "off"}]}


def plan_day(day: str, sport: str, kind: str, session: str | None, minutes: int) -> dict:
    return {"date": day, "sport": sport, "session": session, "kind": kind, "duration_min": minutes,
            "reason": "Test", "status": "planned"}


SCHEDULE = {"created": "2026-10-26", "cycle": {"start": "2026-10-27", "end": "2026-11-02", "label": "Testabschnitt"},
            "days": [plan_day("2026-10-27", "cycling", "key", "vo2_4x8", 65),
                     plan_day("2026-10-28", "cycling", "easy", "base_z2_60", 60),
                     plan_day("2026-10-29", "rest", "rest_expected", None, 0),
                     plan_day("2026-10-30", "strength", "strength", "str_bike_max", 50),
                     plan_day("2026-10-31", "cycling", "long", "base_long", 180),
                     plan_day("2026-11-01", "running", "easy", "run_easy_45", 45),
                     plan_day("2026-11-02", "rest", "rest", None, 0)]}

ZONES = {"sport": "CYCLING", "zone1Floor": 100, "zone2Floor": 120, "zone3Floor": 140, "zone4Floor": 155,
         "zone5Floor": 170, "maxHeartRateUsed": 185}


def analysis(spec: str | None, title: str = "Testeinheit") -> dict:
    a = {"status": "green", "status_text": "bereit", "headline": "Systeme bereit", "summary": "Kurz und gut.",
         "notes": [], "outlook": "Morgen locker.", "week": "Gute Woche.", "bedtime": "22:30"}
    if spec:
        a["workout"] = {"title": title, "why": "Weil es passt.", "focus": "Test", "science": "Studie 2020",
                        "spec": spec}
    return a


class BriefingTrainerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "training").mkdir()
        shutil.copy(trainer.ROOT / "training" / "sessions.json", self.root / "training" / "sessions.json")
        days = {(DAY - timedelta(days=i)).isoformat(): make_day(
            readiness=72, recovery_h=8, ratio=1.1, hrv=62, hrv_low=55, hrv_high=72, sleep=84, rhr=47, rhr_avg=48)
            for i in range(21)}
        data = {"last_sync": "2026-10-27T07:00:00+01:00", "units": {},
                "athlete": {"cycling_ftp_w": 300, "heart_rate_zones": [ZONES]}, "devices": [], "days": days,
                "activities": [make_activity("2026-10-25", te_aer=3.8, te_ana=2.4, benefit="vo2max", load=140),
                               make_activity("2026-10-26", load=55)]}
        self.write("data/data.json", data)
        profile = trainer.default_profile()
        profile["setup_done"] = True
        self.write("training/profile.json", profile)
        self.write("training/season.json", SEASON)
        self.write("training/schedule.json", SCHEDULE)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, content: dict) -> None:
        (self.root / name).write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    def set_today(self, sport: str, kind: str, session: str | None, minutes: int) -> None:
        schedule = json.loads(json.dumps(SCHEDULE))
        schedule["days"][0] = plan_day(DAY.isoformat(), sport, kind, session, minutes)
        self.write("training/schedule.json", schedule)

    def ctx(self, day: date = DAY) -> briefing.Ctx:
        return briefing.Ctx(day, root=self.root)

    def morning(self, spec: str | None, day: date = DAY) -> str:
        return briefing.morning(self.ctx(day), analysis(spec))

    def test_context_has_trainer_keys(self):
        out = briefing.context(self.ctx(), "morning")
        for key in ("profile", "setup_done", "season_phase", "countdown", "schedule", "today_plan", "schedule_stale",
                    "recovery"):
            self.assertIn(key, out)
        self.assertNotIn("block", out)
        self.assertNotIn("time_change_notice", out)
        self.assertTrue(out["setup_done"])
        self.assertEqual(out["profile"]["sports"], ["cycling"])
        self.assertIs(out["profile"]["strength_enabled"], False)
        self.assertEqual(out["season_phase"]["name"], "VO2max-Block")
        self.assertEqual(out["season_phase"]["days_left"], 5)
        self.assertIsNone(out["countdown"])
        self.assertEqual(out["today_plan"]["session"], "vo2_4x8")
        self.assertFalse(out["schedule_stale"])
        self.assertTrue(all(x["date"] >= DAY.isoformat() for x in out["schedule"]))
        self.assertEqual(len(out["recovery"]["signals"]), 7)
        self.assertIn(out["recovery"]["decision"], ("rest_now", "rest", "easy", "train"))
        self.assertEqual(out["session_library"]["run_easy_45"]["sport"], "running")
        wrap = briefing.context(self.ctx(), "wrapup")
        self.assertNotIn("tomorrow_block", wrap)
        self.assertEqual(wrap["tomorrow_plan"]["session"], "base_z2_60")
        json.dumps(out, default=str)

    def test_pages_greet_with_name_from_settings(self):
        self.assertIn('<p class="greet">Guten Morgen</p>', self.morning("vo2_4x8"))
        self.write("dashboard.json", {"name": "Mia"})
        self.assertIn("Guten Morgen, Mia", self.morning("vo2_4x8"))
        self.assertIn("Guten Abend, Mia", briefing.wrapup(self.ctx(), analysis(None)))

    def test_morning_shows_setup_hint(self):
        hint = "Training noch nicht eingerichtet – schreib im Projekt ‚Training einrichten‘"
        self.assertNotIn(hint, self.morning("vo2_4x8"))
        self.write("training/profile.json", trainer.default_profile())
        self.assertIn(hint, self.morning("vo2_4x8"))

    def test_morning_strength_has_table_no_download(self):
        self.set_today("strength", "strength", "str_bike_max", 50)
        page = self.morning("str_bike_max")
        first = LIBRARY["str_bike_max"]["spec"]["exercises"][0]
        self.assertIn(briefing.esc(first.get("label") or first["name"]), page)
        self.assertIn(f'{first["reps"]} Wdh.', page)
        self.assertNotIn('id="dl"', page)
        self.assertNotIn("data-zip", page)

    def test_morning_running_uses_describe(self):
        self.set_today("running", "easy", "run_easy_45", 45)
        page = self.morning("run_easy_45")
        for _, label, amount, _ in workouts.describe(LIBRARY["run_easy_45"]["spec"]):
            self.assertIn(briefing.esc(label), page)
            self.assertIn(briefing.esc(amount), page)
        self.assertNotIn('id="dl"', page)

    def test_morning_duration_as_text_does_not_crash(self):
        a = analysis("run_easy_45", "Lauf statt Rad")
        a["workout"]["duration_min"] = "45"  # today_plan is vo2_4x8, so the analysis' own duration is used
        self.assertIn("45 min", briefing.morning(self.ctx(), a))
        a["workout"]["duration_min"] = "etwa eine Stunde"
        self.assertIn("Lauf statt Rad", briefing.morning(self.ctx(), a))

    def test_morning_cycling_keeps_download(self):
        page = self.morning("vo2_4x8")
        self.assertIn('id="dl"', page)
        self.assertIn("data-zip=", page)
        self.assertIn("% FTP", page)

    def test_morning_preview_and_season(self):
        profile = trainer.default_profile()
        profile.update(setup_done=True, goal={"type": "event", "event": {
            "name": "Ötztaler", "date": "2027-08-29", "distance_km": 227, "elevation_m": 5500, "priority": "A"}})
        self.write("training/profile.json", profile)
        page = self.morning("vo2_4x8")
        self.assertIn('class="preview"', page)
        self.assertIn("Ruhetag voraussichtlich", page)
        self.assertIn("Schlüsseleinheit", page)
        self.assertIn("Lange Einheit", page)
        self.assertIn("VO2max-Block", page)
        self.assertIn("Ötztaler", page)
        self.assertIn("306", page)  # days until 29.08.2027
        self.assertIn("5.500 Hm", page)

    def test_morning_recovery_panel(self):
        page = self.morning("vo2_4x8")
        for label in ("Trainingsbereitschaft", "Erholungszeit", "Belastungsverhältnis", "HRV der letzten Nächte",
                      "Schlaf-Scores", "Ruhepuls-Entwicklung", "Trainingstage in Folge"):
            self.assertIn(label, page)
        self.assertIn("Training nach Plan", page)

    def test_stale_schedule_does_not_crash(self):
        schedule = json.loads(json.dumps(SCHEDULE))
        schedule["days"] = [plan_day("2026-10-25", "cycling", "easy", "base_z2_60", 60),
                            plan_day("2026-10-26", "rest", "rest", None, 0)]
        self.write("training/schedule.json", schedule)
        out = briefing.context(self.ctx(), "morning")
        self.assertIsNone(out["today_plan"])
        self.assertTrue(out["schedule_stale"])
        self.assertEqual(out["schedule"], [])
        self.assertIn("Vorschau veraltet", self.morning("base_z2_60"))
        self.assertIn("Vorschau veraltet", briefing.wrapup(self.ctx(), analysis(None)))

    def test_wrapup_has_preview(self):
        page = briefing.wrapup(self.ctx(date(2026, 10, 28)), analysis(None))
        self.assertIn('class="preview"', page)
        self.assertIn("Ruhetag voraussichtlich", page)
        self.assertIn("VO2max-Block", page)

    def test_no_dst_notice(self):
        day = date(2026, 10, 23)  # two days before the switch to winter time
        for page in (self.morning("vo2_4x8", day), briefing.wrapup(self.ctx(day), analysis(None))):
            self.assertNotIn("Zeitumstellung", page)
            self.assertNotIn("Winterzeit", page)
        self.assertFalse(hasattr(briefing, "dst_notice"))

    def test_write_schedule_only_with_calendar_consent(self):
        self.assertIsNone(briefing.write_schedule(self.ctx(), analysis("vo2_4x8")))  # default: switched off
        self.assertFalse((self.root / "scheduled").exists())

    def test_write_schedule_records_sport(self):
        self.write("dashboard.json", {"calendar_upload": True})
        target = briefing.write_schedule(self.ctx(), analysis("vo2_4x8"))
        self.assertEqual(target, self.root / "scheduled" / "2026-10-27.json")
        job = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual((job["sport"], job["ftp"]), ("cycling", 300))
        target.unlink()
        job = json.loads(briefing.write_schedule(self.ctx(), analysis("str_bike_max")).read_text(encoding="utf-8"))
        self.assertEqual(job["sport"], "strength")
        self.assertEqual(job["spec"]["exercises"], LIBRARY["str_bike_max"]["spec"]["exercises"])

    def test_write_schedule_skips_running(self):
        self.write("dashboard.json", {"calendar_upload": True})
        self.assertIsNone(briefing.write_schedule(self.ctx(), analysis("run_easy_45")))
        self.assertFalse((self.root / "scheduled").exists())


if __name__ == "__main__":
    unittest.main()
