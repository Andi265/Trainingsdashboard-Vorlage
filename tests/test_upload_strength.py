import unittest

import calendar_upload as up
import trainer
from garminconnect import Garmin

LIBRARY = trainer.load_sessions()


class FakeApi:
    def __init__(self):
        self.uploaded, self.scheduled = [], []

    def get_scheduled_workouts(self, year, month):
        return {"calendarItems": []}

    def upload_workout(self, payload):
        self.uploaded.append(payload)
        return {"workoutId": 7}

    def schedule_workout(self, workout_id, day):
        self.scheduled.append((workout_id, day))
        return {"workoutScheduleId": 9}


class StrengthWorkoutTests(unittest.TestCase):
    def test_strength_structure(self):
        spec = LIBRARY["str_bike_max"]["spec"]
        workout = up.strength_payload("[HUD] Kraft", "Test", spec)
        self.assertEqual(workout["sportType"]["sportTypeKey"], "strength_training")
        groups = workout["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(len(groups), len(spec["exercises"]))
        first = groups[0]
        self.assertEqual(first["type"], "RepeatGroupDTO")
        self.assertEqual(first["numberOfIterations"], 4)
        exercise, rest = first["workoutSteps"]
        self.assertEqual(exercise["endCondition"]["conditionTypeKey"], "reps")
        self.assertEqual(exercise["endConditionValue"], 5.0)
        self.assertEqual((exercise["category"], exercise["exerciseName"]), ("SQUAT", "BARBELL_BACK_SQUAT"))
        self.assertEqual(rest["stepType"]["stepTypeKey"], "rest")
        self.assertEqual(rest["endConditionValue"], 180.0)
        orders = [g["stepOrder"] for g in groups] + [s["stepOrder"] for g in groups for s in g["workoutSteps"]]
        self.assertEqual(len(orders), len(set(orders)))

    def test_unknown_exercise_raises(self):
        spec = {"sport": "strength", "exercises": [{"name": "Flying Kick", "sets": 1, "reps": 1, "rest_sec": 30}]}
        with self.assertRaises(ValueError):
            up.strength_payload("[HUD] x", "", spec)

    def test_guard_still_blocks_delete(self):
        api = Garmin()
        api.client._run_request = lambda method, path, **kw: "sent"
        up.allow_only_workout_writes(api)
        self.assertEqual(api.client._run_request("POST", "/workout-service/workout"), "sent")
        with self.assertRaises(PermissionError):
            api.client._run_request("DELETE", "/workout-service/workout/1")


class UploadJobTests(unittest.TestCase):
    def test_running_job_skipped(self):
        api = FakeApi()
        job = {"date": "2026-11-03", "sport": "running", "title": "Lauf", "spec": LIBRARY["run_easy_45"]["spec"]}
        result = up.upload_job(api, job, None)
        self.assertIn("skipped", result)
        self.assertEqual(api.uploaded, [])

    def test_strength_job_uploaded(self):
        api = FakeApi()
        job = {"date": "2026-11-03", "sport": "strength", "title": "Kraft Rad", "spec": LIBRARY["str_bike_max"]["spec"]}
        result = up.upload_job(api, job, None)
        self.assertEqual((result["workout_id"], result["schedule_id"]), (7, 9))
        self.assertEqual(api.uploaded[0]["sportType"]["sportTypeKey"], "strength_training")
        self.assertTrue(api.uploaded[0]["workoutName"].startswith("[HUD] "))
        self.assertEqual(api.scheduled, [(7, "2026-11-03")])

    def test_cycling_job_without_sport_still_uploaded(self):
        api = FakeApi()
        job = {"date": "2026-11-03", "title": "VO2max", "ftp": 311, "spec": LIBRARY["vo2_5x4"]["spec"]}
        up.upload_job(api, job, None)
        self.assertEqual(api.uploaded[0]["sportType"]["sportTypeKey"], "cycling")


if __name__ == "__main__":
    unittest.main()
