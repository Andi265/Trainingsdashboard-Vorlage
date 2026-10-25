import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import trainer
from tests.test_trainer_schedule import LIBRARY, valid_schedule


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(trainer.ROOT / "trainer.py"), "--root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "training").mkdir()
        shutil.copy(trainer.ROOT / "training" / "profile.json", self.tmp / "training" / "profile.json")
        (self.tmp / "training" / "sessions.json").write_text(json.dumps({"sessions": LIBRARY}), encoding="utf-8")
        self.schedule_file = self.tmp / "training" / "schedule.json"
        self.schedule_file.write_text(json.dumps(valid_schedule()), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_write_schedule_invalid_keeps_file(self):
        before = self.schedule_file.read_text(encoding="utf-8")
        bad = valid_schedule()
        bad["days"][0]["session"] = "nope"
        bad_file = self.tmp / "bad.json"
        bad_file.write_text(json.dumps(bad), encoding="utf-8")
        result = run(self.tmp, "write-schedule", str(bad_file))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.schedule_file.read_text(encoding="utf-8"), before)

    def test_write_schedule_valid_saves(self):
        good = valid_schedule()
        good["days"][0]["reason"] = "neu"
        good_file = self.tmp / "good.json"
        good_file.write_text(json.dumps(good), encoding="utf-8")
        result = run(self.tmp, "write-schedule", str(good_file))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.schedule_file.read_text(encoding="utf-8"))["days"][0]["reason"], "neu")

    def test_set_day_marks_changed(self):
        result = run(self.tmp, "set-day", "2026-11-03", "--status", "changed", "--reason", "Bereitschaft 45")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        saved = json.loads(self.schedule_file.read_text(encoding="utf-8"))
        target = next(d for d in saved["days"] if d["date"] == "2026-11-03")
        self.assertEqual(target["status"], "changed")
        self.assertEqual(target["reason"], "Bereitschaft 45")

    def test_show_mentions_goal(self):
        result = run(self.tmp, "show")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ziel", result.stdout)


if __name__ == "__main__":
    unittest.main()
