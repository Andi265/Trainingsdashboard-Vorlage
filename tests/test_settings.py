import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import briefing
import settings


class SettingsTests(unittest.TestCase):
    def test_defaults_without_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = settings.load(Path(tmp))
        self.assertEqual(values["name"], "")
        self.assertEqual(values["timezone"], "Europe/Berlin")
        self.assertEqual(values["links"], {"morning_briefing": "", "daily_wrapup": ""})
        self.assertIs(values["calendar_upload"], False)  # the only write to Garmin needs explicit consent
        self.assertIs(values["push_notifications"], True)

    def test_file_values_win_and_missing_keys_keep_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "dashboard.json").write_text(
                json.dumps({"name": "Mia", "timezone": "Europe/Vienna", "links": {"morning_briefing": "x"}}),
                encoding="utf-8")
            values = settings.load(Path(tmp))
            zone = settings.timezone(Path(tmp))
        self.assertEqual(values["name"], "Mia")
        self.assertEqual(zone, ZoneInfo("Europe/Vienna"))
        self.assertEqual(values["links"], {"morning_briefing": "x", "daily_wrapup": ""})

    def test_greeting(self):
        self.assertEqual(briefing.greeting("Guten Morgen", "Mia"), "Guten Morgen, Mia")
        self.assertEqual(briefing.greeting("Guten Abend", ""), "Guten Abend")

    def test_template_ships_empty_settings(self):
        values = settings.load()
        self.assertEqual(values["name"], "")
        self.assertEqual(values["links"], {"morning_briefing": "", "daily_wrapup": ""})
        self.assertIs(values["calendar_upload"], False)

    def test_upload_does_nothing_without_consent(self):
        import calendar_upload as up

        def no_login(*args, **kwargs):
            raise AssertionError("must not contact Garmin")

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "2099-01-01.json").write_text(json.dumps({"date": "2099-01-01", "spec": {"steps": []}}),
                                                    encoding="utf-8")  # a workout waiting for upload
            with mock.patch.object(up.settings, "load", return_value={**settings.DEFAULTS, "calendar_upload": False}), \
                    mock.patch.object(up, "SCHEDULED", Path(tmp)), mock.patch.object(up, "Garmin", no_login):
                self.assertEqual(up.main(), 0)


if __name__ == "__main__":
    unittest.main()
