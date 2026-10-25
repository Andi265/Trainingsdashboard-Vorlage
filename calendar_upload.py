"""Put the Morning Briefing's workout into the Garmin Connect calendar.

This is the only script that writes to Garmin, and it may do exactly two things:
create a workout (POST /workout-service/workout) and put it in the calendar
(POST /workout-service/schedule/<id>). Every other write is blocked before it
leaves the machine. It never edits or deletes anything. It does nothing at all unless
the user agreed to the upload during setup (calendar_upload in dashboard.json).

Reads scheduled/<date>.json (written by `briefing.py morning --schedule`) for today
or later that has not been uploaded yet, uploads it as "[HUD] <title>" with power
targets in watts, schedules it on that date and records the result in the file.
Skips a date that already has a "[HUD]" workout in the calendar.

  python calendar_upload.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

import settings
import workouts
from sync import TOKENSTORE

ROOT = Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
TZ = settings.timezone()
PREFIX = "[HUD] "
ALLOWED_WRITES = (re.compile(r"^/workout-service/workout$"), re.compile(r"^/workout-service/schedule/\d+$"))

SPORT = {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2}
STEP_TYPES = {"warmup": (1, "warmup"), "cooldown": (2, "cooldown"), "interval": (3, "interval"),
              "steady": (3, "interval"), "recovery": (4, "recovery")}
TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
POWER = {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2}


def allow_only_workout_writes(api: Garmin) -> None:
    """Let GET requests through, plus POSTs that create or schedule a workout. Block everything else."""
    run_request = api.client._run_request

    def guarded(method: str, path: str, **kwargs):
        verb = method.upper()
        if verb != "GET" and not (verb == "POST" and any(p.match(path) for p in ALLOWED_WRITES)):
            raise PermissionError(f"Blocked {method} {path}: only creating and scheduling workouts is allowed.")
        return run_request(method, path, **kwargs)

    api.client._run_request = guarded


def workout_payload(name: str, description: str, items: list, ftp: int, zones: dict | None) -> dict:
    """Build the JSON that Garmin Connect's workout editor itself sends."""
    order = 0

    def step(s: workouts.Step) -> dict:
        nonlocal order
        order += 1
        type_id, type_key = STEP_TYPES[s.kind]
        hr = workouts.hr_range(s, zones)
        return {"type": "ExecutableStepDTO", "stepOrder": order,
                "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
                "endCondition": TIME, "endConditionValue": float(s.seconds), "targetType": POWER,
                "targetValueOne": float(workouts.watts(s.lo, ftp)), "targetValueTwo": float(workouts.watts(s.hi, ftp)),
                "description": s.label + (f" · Puls {hr[0]}-{hr[1]}" if hr else "")}

    steps = []
    for item in items:
        if isinstance(item, workouts.Repeat):
            order += 1
            group = {"type": "RepeatGroupDTO", "stepOrder": order,
                     "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                     "numberOfIterations": item.count, "smartRepeat": False, "endCondition": ITERATIONS,
                     "endConditionValue": float(item.count)}
            group["workoutSteps"] = [step(s) for s in item.steps]
            steps.append(group)
        else:
            steps.append(step(item))
    return {"workoutName": name[:50], "description": description[:500], "sportType": SPORT,
            "estimatedDurationInSecs": workouts.total_seconds(items),
            "workoutSegments": [{"segmentOrder": 1, "sportType": SPORT, "workoutSteps": steps}]}


STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": True}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}


def strength_payload(name: str, description: str, spec: dict) -> dict:
    """A strength workout as the Garmin workout editor builds it: per exercise a set group of reps and rest."""
    from garminconnect import exercises

    order = 0
    groups = []
    total = 0
    for entry in spec.get("exercises") or []:
        found = exercises.resolve(entry["name"])
        if not found:
            raise ValueError(f"Unknown Garmin exercise: {entry['name']}")
        sets, reps, rest = int(entry["sets"]), int(entry["reps"]), int(entry.get("rest_sec", 60))
        group_order, order = order + 1, order + 3
        groups.append({
            "type": "RepeatGroupDTO", "stepOrder": group_order,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
            "numberOfIterations": sets, "smartRepeat": False, "endCondition": ITERATIONS,
            "endConditionValue": float(sets),
            "workoutSteps": [
                {"type": "ExecutableStepDTO", "stepOrder": group_order + 1,
                 "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
                 "endCondition": REPS, "endConditionValue": float(reps), "targetType": NO_TARGET,
                 "category": found["category"], "exerciseName": found["exercise"],
                 "description": " · ".join(x for x in (entry.get("label"), entry.get("load")) if x)},
                {"type": "ExecutableStepDTO", "stepOrder": group_order + 2,
                 "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
                 "endCondition": TIME, "endConditionValue": float(rest), "targetType": NO_TARGET}]})
        total += sets * (reps * 4 + rest)
    return {"workoutName": name[:50], "description": description[:500], "sportType": STRENGTH,
            "estimatedDurationInSecs": total,
            "workoutSegments": [{"segmentOrder": 1, "sportType": STRENGTH, "workoutSteps": groups}]}


UPLOADABLE = ("cycling", "strength")


def upload_job(api, job: dict, zones: dict | None) -> dict:
    """Upload one scheduled workout and put it in the calendar; returns the job's `upload` record."""
    sport = job.get("sport", "cycling")
    if sport not in UPLOADABLE:
        return {"skipped": f"Sport '{sport}' is not uploaded to Garmin yet (stage 2)."}
    if already_scheduled(api, job["date"]):
        return {"skipped": "A [HUD] workout is already in the calendar for this day."}
    name = PREFIX + str(job.get("title") or job["spec"].get("name") or "Workout")
    description = job.get("description") or ""
    if sport == "strength":
        payload = strength_payload(name, description, job["spec"])
    else:
        payload = workout_payload(name, description, workouts.normalize(job["spec"]["steps"]), int(job["ftp"]), zones)
    workout_id = api.upload_workout(payload).get("workoutId")
    scheduled = api.schedule_workout(workout_id, job["date"])
    return {"workout_id": workout_id, "schedule_id": (scheduled or {}).get("workoutScheduleId"), "name": name,
            "uploaded_at": datetime.now(TZ).isoformat(timespec="seconds")}


def pending(today: str) -> list[tuple[Path, dict]]:
    jobs = []
    for path in sorted(SCHEDULED.glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (job.get("date") or "") >= today and not job.get("upload"):
            jobs.append((path, job))
    return jobs


def already_scheduled(api: Garmin, day: str) -> bool:
    items = (api.get_scheduled_workouts(int(day[:4]), int(day[5:7])) or {}).get("calendarItems") or []
    return any(i.get("date") == day and i.get("itemType") == "workout" and (i.get("title") or "").startswith(PREFIX)
               for i in items)


def cycling_zones() -> dict | None:
    try:
        zones = json.loads((ROOT / "data" / "data.json").read_text(encoding="utf-8")).get("athlete", {}).get("heart_rate_zones") or []
    except (OSError, ValueError):
        return None
    return next((z for z in zones if z.get("sport") == "CYCLING"), zones[0] if zones else None)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not settings.load().get("calendar_upload"):
        print("The Garmin calendar upload is switched off (calendar_upload in dashboard.json); nothing is sent.")
        return 0
    today = datetime.now(TZ).date().isoformat()
    jobs = pending(today)
    if not jobs:
        print("No new workout to upload.")
        return 0

    api = Garmin()
    allow_only_workout_writes(api)
    try:
        api.login(TOKENSTORE)
        zones = cycling_zones()
        for path, job in jobs:
            job["upload"] = upload_job(api, job, zones)
            if "skipped" in job["upload"]:
                print(f"{job['date']}: skipped – {job['upload']['skipped']}")
            else:
                print(f"{job['date']}: uploaded '{job['upload']['name']}' and added it to the Garmin calendar.")
            path.write_text(json.dumps(job, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    except GarminConnectAuthenticationError:
        print("Garmin rejected the saved login. Run login.py and 'token_vault.py upload' on the PC.")
        return 2
    except GarminConnectTooManyRequestsError:
        print("Garmin is rate-limiting requests right now. Please try again later.")
        return 3
    except GarminConnectConnectionError as err:
        print(f"Garmin did not accept the workout: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
