import unittest

import trainer
import workouts

NEW_IDS = ("run_easy_45", "run_long_90", "run_tempo_3x10", "run_vo2_5x3", "run_hills_8x60", "run_strides_6",
           "swim_tech_2000", "swim_css_10x100", "swim_endurance_3000", "str_adapt", "str_bike_max",
           "str_bike_maint", "str_run", "str_swim", "brick_bike90_run20", "climb_sst_3x20", "climb_lowcad_5x6")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.library = trainer.load_sessions()

    def test_new_sessions_exist_with_evidence(self):
        for ident in NEW_IDS:
            self.assertIn(ident, self.library)
            self.assertTrue(self.library[ident].get("evidence"), ident)

    def test_every_session_has_known_sport(self):
        for ident, entry in self.library.items():
            self.assertIn(entry.get("sport"), trainer.SPORTS + ("brick",), ident)
            self.assertEqual(entry["spec"].get("sport", "cycling"), entry["sport"], ident)

    def test_cycling_specs_normalize(self):
        for ident, entry in self.library.items():
            if entry["sport"] == "cycling":
                self.assertTrue(workouts.normalize(entry["spec"]["steps"]), ident)

    def test_describe_non_cycling(self):
        for ident, entry in self.library.items():
            if entry["sport"] == "cycling":
                continue
            rows = workouts.describe(entry["spec"])
            self.assertTrue(rows, ident)
            for row in rows:
                self.assertEqual(len(row), 4, ident)
                self.assertTrue(row[1] and row[2], (ident, row))

    def test_strength_names_resolve(self):
        from garminconnect import exercises
        for ident, entry in self.library.items():
            if entry["sport"] == "strength":
                for exercise in entry["spec"]["exercises"]:
                    self.assertIsNotNone(exercises.resolve(exercise["name"]), (ident, exercise["name"]))

    def test_describe_strength_row(self):
        first = workouts.describe(self.library["str_bike_max"]["spec"])[0]
        self.assertTrue(first[0].endswith("×"))
        self.assertIn("Wdh.", first[2])

    def test_describe_cycling_uses_ftp_percent(self):
        rows = workouts.describe(self.library["vo2_5x4"]["spec"])
        self.assertTrue(any("% FTP" in row[3] for row in rows))

    def test_describe_brick_has_both_parts(self):
        labels = " ".join(row[1] for row in workouts.describe(self.library["brick_bike90_run20"]["spec"]))
        self.assertIn("Rad", labels)
        self.assertIn("Lauf", labels)


if __name__ == "__main__":
    unittest.main()
