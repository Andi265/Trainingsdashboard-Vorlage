"""Read-only sync of Garmin Connect data into the data/ folder.

Writes:
  data/data.json                              everything in one machine-readable file
  data/wellness/YYYY-MM-DD.md                 one plain-English note per day
  data/activities/YYYY-MM-DD_<type>_<id>.md   one note per workout

Only GET requests reach the Garmin Connect API; anything else is blocked before
it leaves this computer, so nothing can ever be written back to Garmin.
The login token is read from ~/.garminconnect (or the TOKENSTORE_DIR environment
variable) and is never copied into data/.

Usage:
  py -3.13 sync.py              # last 3 days
  py -3.13 sync.py --days 28    # backfill four weeks
  py -3.13 sync.py --days auto  # every day since the last sync (at least 3, at most 30)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import settings
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "data"
TOKENSTORE = os.getenv("TOKENSTORE_DIR") or "~/.garminconnect"
TZ = settings.timezone()
CURVE_DAYS = 14  # intraday curves are kept only for the most recent days
PAUSE_S = 0.4  # pause between API calls, to be gentle with Garmin
AUTO_DAYS = (3, 30)  # --days auto: at least the last 3 days, catch up at most 30

SLEEP_STAGES = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
UNITS = {
    "durations": "minutes (fields ending in _min) or hours (_h)",
    "distance": "km",
    "speed": "km/h",
    "heart_rate": "bpm",
    "hrv": "ms",
    "power": "W",
    "elevation": "m",
    "stress": "0-100 (0-25 rest, 26-50 low, 51-75 medium, 76-100 high)",
    "body_battery": "0-100",
    "training_effect": "0-5 (1 minor, 2 maintaining, 3 improving, 4 highly improving, 5 overreaching)",
    "curves": "[local time HH:MM, value] pairs",
}


# --------------------------------------------------------------------------- helpers


def dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    """Safely walk nested dicts/lists; return default if anything is missing."""
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return default
        if obj is None:
            return default
    return obj


def num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def rnd(value: Any, digits: int = 1) -> float | int | None:
    value = num(value)
    if value is None:
        return None
    return round(value) if digits == 0 else round(value, digits)


def minutes(seconds: Any) -> int | None:
    seconds = num(seconds)
    return round(seconds / 60) if seconds is not None else None


def label(key: Any) -> str | None:
    """Garmin enum like 'HIGH_AEROBIC' -> 'high aerobic'."""
    if not isinstance(key, str) or not key:
        return None
    return key.replace("_", " ").strip().lower()


def phrase(key: Any) -> str | None:
    """Garmin feedback key like 'PRODUCTIVE_6' -> 'productive'."""
    if not isinstance(key, str) or not key:
        return None
    parts = key.split("_")
    while parts and parts[-1].isdigit():
        parts.pop()
    text = label("_".join(parts))
    return None if text in ("none", "no feedback") else text


def gmt_to_local(value: Any) -> datetime | None:
    """Garmin GMT timestamp (epoch ms or ISO string) -> local datetime."""
    if num(value) is not None:
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "")[:19]).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    else:
        return None
    return dt.astimezone(TZ)


def wall_clock(value: Any) -> datetime | None:
    """Garmin '...TimestampLocal' epoch ms: local wall time encoded as if it were UTC."""
    if num(value) is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)


def hhmm(dt: datetime | None) -> str | None:
    return dt.strftime("%H:%M") if dt else None


def bucket(points: Iterable[tuple[datetime | None, Any]], step_min: int) -> list[list[Any]]:
    """Average (time, value) points into fixed-size time buckets -> [["HH:MM", value], ...]."""
    groups: dict[datetime, list[float]] = {}
    for dt, value in points:
        if dt is None or num(value) is None:
            continue
        start = dt.replace(minute=dt.minute - dt.minute % step_min, second=0, microsecond=0)
        groups.setdefault(start, []).append(value)
    return [[k.strftime("%H:%M"), round(sum(v) / len(v))] for k, v in sorted(groups.items())]


def clean(obj: Any) -> Any:
    """Drop empty values so data.json stays compact."""
    if isinstance(obj, dict):
        out = {k: clean(v) for k, v in obj.items()}
        return {k: v for k, v in out.items() if v is not None and v != {} and v != [] and v != ""}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


# ----------------------------------------------------------------------- connection


def make_read_only(api: Garmin) -> None:
    """Block every Garmin Connect API call that is not a plain GET request."""
    run_request = api.client._run_request

    def get_only(method: str, path: str, **kwargs: Any) -> Any:
        if method.upper() != "GET":
            raise PermissionError(f"Blocked {method} {path}: this sync is read-only.")
        return run_request(method, path, **kwargs)

    api.client._run_request = get_only


def connect() -> Garmin:
    api = Garmin()
    make_read_only(api)
    api.login(TOKENSTORE)
    return api


class Fetcher:
    """Calls one Garmin endpoint; missing data for a day is normal and only noted."""

    def __init__(self) -> None:
        self.missing: list[str] = []

    def __call__(self, what: str, fn: Callable[..., Any], *args: Any) -> Any:
        time.sleep(PAUSE_S)
        try:
            return fn(*args)
        except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError, PermissionError):
            raise
        except Exception as err:  # noqa: BLE001 - one failing endpoint must not stop the sync
            self.missing.append(f"{what} ({type(err).__name__})")
            return None


# ------------------------------------------------------------------- daily wellness


def build_sleep(raw: dict) -> dict | None:
    dto = raw.get("dailySleepDTO") or {}
    if not num(dto.get("sleepTimeSeconds")):
        return None
    start, end = wall_clock(dto.get("sleepStartTimestampLocal")), wall_clock(dto.get("sleepEndTimestampLocal"))
    heart = [p.get("value") for p in raw.get("sleepHeartRate") or [] if isinstance(p, dict) and num(p.get("value"))]
    return {
        "start": start.isoformat(timespec="minutes") if start else None,
        "end": end.isoformat(timespec="minutes") if end else None,
        "total_min": minutes(dto.get("sleepTimeSeconds")),
        "deep_min": minutes(dto.get("deepSleepSeconds")),
        "light_min": minutes(dto.get("lightSleepSeconds")),
        "rem_min": minutes(dto.get("remSleepSeconds")),
        "awake_min": minutes(dto.get("awakeSleepSeconds")),
        "nap_min": minutes(dto.get("napTimeSeconds")) or None,
        "score": dig(dto, "sleepScores", "overall", "value"),
        "quality": label(dig(dto, "sleepScores", "overall", "qualifierKey")),
        "feedback": phrase(dto.get("sleepScoreFeedback")),
        "need_min": dig(dto, "sleepNeed", "actual"),
        "awake_count": dto.get("awakeCount"),
        "avg_hr": round(sum(heart) / len(heart)) if heart else None,
        "avg_respiration": rnd(dto.get("averageRespirationValue")),
        "avg_spo2": rnd(dto.get("averageSpO2Value")),
        "lowest_spo2": dto.get("lowestSpO2Value"),
        "avg_sleep_stress": rnd(dto.get("avgSleepStress")),
        "body_battery_gain": raw.get("bodyBatteryChange"),
    }


def build_hrv(raw: dict) -> dict | None:
    hs = raw.get("hrvSummary")
    if not isinstance(hs, dict):
        return None
    return {
        "last_night_avg": hs.get("lastNightAvg"),
        "last_night_high_5min": hs.get("lastNight5MinHigh"),
        "weekly_avg": hs.get("weeklyAvg"),
        "status": label(hs.get("status")),
        "baseline_low": dig(hs, "baseline", "balancedLow"),
        "baseline_high": dig(hs, "baseline", "balancedUpper"),
        "feedback": phrase(hs.get("feedbackPhrase")),
    }


def build_body_battery(s: dict, bb_day: dict) -> dict:
    events = []
    for e in bb_day.get("bodyBatteryActivityEvent") or []:
        if not isinstance(e, dict):
            continue
        events.append({
            "type": label(e.get("eventType")),
            "start": hhmm(gmt_to_local(e.get("eventStartTimeGmt"))),
            "duration_min": rnd((num(e.get("durationInMilliseconds")) or 0) / 60000, 0),
            "impact": e.get("bodyBatteryImpact"),
            "feedback": phrase(e.get("shortFeedback")),
        })
    return {
        "at_wake": s.get("bodyBatteryAtWakeTime"),
        "highest": s.get("bodyBatteryHighestValue"),
        "lowest": s.get("bodyBatteryLowestValue"),
        "latest": s.get("bodyBatteryMostRecentValue"),
        "charged": s["bodyBatteryChargedValue"] if s.get("bodyBatteryChargedValue") is not None else bb_day.get("charged"),
        "drained": s["bodyBatteryDrainedValue"] if s.get("bodyBatteryDrainedValue") is not None else bb_day.get("drained"),
        "events": events,
    }


def build_stress(s: dict) -> dict:
    def level(v: Any) -> Any:
        return v if num(v) is not None and v >= 0 else None

    return {
        "avg": level(s.get("averageStressLevel")),
        "max": level(s.get("maxStressLevel")),
        "quality": label(s.get("stressQualifier")),
        "rest_min": minutes(s.get("restStressDuration")),
        "low_min": minutes(s.get("lowStressDuration")),
        "medium_min": minutes(s.get("mediumStressDuration")),
        "high_min": minutes(s.get("highStressDuration")),
        "activity_min": minutes(s.get("activityStressDuration")),
    }


def build_readiness(entries: Any) -> dict | None:
    if isinstance(entries, dict):
        entries = [entries]
    entries = [e for e in entries or [] if isinstance(e, dict) and num(e.get("score")) is not None]
    if not entries:
        return None
    entries.sort(key=lambda e: e.get("timestampLocal") or e.get("timestamp") or "")
    morning = next((e for e in entries if e.get("inputContext") == "AFTER_WAKEUP_RESET"), entries[0])

    def pick(e: dict) -> dict:
        return {
            "time": (e.get("timestampLocal") or "")[11:16] or None,
            "score": e.get("score"),
            "level": label(e.get("level")),
            "feedback": phrase(e.get("feedbackShort")),
            "recovery_time_h": rnd((num(e.get("recoveryTime")) or 0) / 60) if num(e.get("recoveryTime")) is not None else None,
            "acute_load": e.get("acuteLoad"),
            "hrv_weekly_avg": e.get("hrvWeeklyAverage"),
            "factors_pct": {
                "sleep": e.get("sleepScoreFactorPercent"),
                "sleep_history": e.get("sleepHistoryFactorPercent"),
                "hrv": e.get("hrvFactorPercent"),
                "recovery_time": e.get("recoveryTimeFactorPercent"),
                "acute_load": e.get("acwrFactorPercent"),
                "stress_history": e.get("stressHistoryFactorPercent"),
            },
            "factors_rating": {
                "sleep": label(e.get("sleepScoreFactorFeedback")),
                "sleep_history": label(e.get("sleepHistoryFactorFeedback")),
                "hrv": label(e.get("hrvFactorFeedback")),
                "recovery_time": label(e.get("recoveryTimeFactorFeedback")),
                "acute_load": label(e.get("acwrFactorFeedback")),
                "stress_history": label(e.get("stressHistoryFactorFeedback")),
            },
        }

    return {"morning": pick(morning), "latest": pick(entries[-1])}


def primary_device_entry(device_map: Any) -> dict:
    """Garmin keys training data per device; use the primary training device."""
    if not isinstance(device_map, dict):
        return {}
    values = [v for v in device_map.values() if isinstance(v, dict)]
    return next((v for v in values if v.get("primaryTrainingDevice")), values[0] if values else {})


def build_training_status(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    st = primary_device_entry(dig(raw, "mostRecentTrainingStatus", "latestTrainingStatusData"))
    bal = primary_device_entry(dig(raw, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap"))
    acute = st.get("acuteTrainingLoadDTO") or {}
    return {
        "as_of": st.get("calendarDate"),
        "status": phrase(st.get("trainingStatusFeedbackPhrase")),
        "weekly_load": st.get("weeklyTrainingLoad"),
        "acute_load": acute.get("dailyTrainingLoadAcute"),
        "chronic_load": acute.get("dailyTrainingLoadChronic"),
        "chronic_load_min": rnd(acute.get("minTrainingLoadChronic"), 0),
        "chronic_load_max": rnd(acute.get("maxTrainingLoadChronic"), 0),
        "load_ratio": rnd(acute.get("dailyAcuteChronicWorkloadRatio"), 2),
        "load_ratio_status": label(acute.get("acwrStatus")),
        "vo2max_running": dig(raw, "mostRecentVO2Max", "generic", "vo2MaxPreciseValue"),
        "vo2max_cycling": dig(raw, "mostRecentVO2Max", "cycling", "vo2MaxPreciseValue"),
        "load_focus_4_weeks": {
            "low_aerobic": rnd(bal.get("monthlyLoadAerobicLow"), 0),
            "low_aerobic_target": [rnd(bal.get("monthlyLoadAerobicLowTargetMin"), 0), rnd(bal.get("monthlyLoadAerobicLowTargetMax"), 0)],
            "high_aerobic": rnd(bal.get("monthlyLoadAerobicHigh"), 0),
            "high_aerobic_target": [rnd(bal.get("monthlyLoadAerobicHighTargetMin"), 0), rnd(bal.get("monthlyLoadAerobicHighTargetMax"), 0)],
            "anaerobic": rnd(bal.get("monthlyLoadAnaerobic"), 0),
            "anaerobic_target": [rnd(bal.get("monthlyLoadAnaerobicTargetMin"), 0), rnd(bal.get("monthlyLoadAnaerobicTargetMax"), 0)],
            "feedback": phrase(bal.get("trainingBalanceFeedbackPhrase")),
        } if bal else None,
    }


def packed_series(rows: Any, descriptors: Any, value_key: str, default_index: int) -> list[tuple[datetime | None, Any]]:
    """Garmin packs intraday values as rows plus a list of column descriptors."""
    index = {}
    for d in descriptors or []:
        if isinstance(d, dict):
            key = d.get("key", d.get("bodyBatteryValueDescriptorKey"))
            pos = d.get("index", d.get("bodyBatteryValueDescriptorIndex"))
            if key is not None and pos is not None:
                index[key] = pos
    t_i, v_i = index.get("timestamp", 0), index.get(value_key, default_index)
    return [(gmt_to_local(r[t_i]), r[v_i]) for r in rows or [] if isinstance(r, list) and len(r) > max(t_i, v_i)]


def sleep_stage_segments(raw: dict) -> list[list[Any]]:
    segments: list[list[Any]] = []
    for lv in raw.get("sleepLevels") or []:
        if not isinstance(lv, dict) or num(lv.get("activityLevel")) is None:
            continue
        stage = SLEEP_STAGES.get(int(lv["activityLevel"]), "unknown")
        start, end = hhmm(gmt_to_local(lv.get("startGMT"))), hhmm(gmt_to_local(lv.get("endGMT")))
        if segments and segments[-1][2] == stage and segments[-1][1] == start:
            segments[-1][1] = end
        else:
            segments.append([start, end, stage])
    return segments


def build_curves(sleep_raw: dict, hrv_raw: dict, stress_raw: dict, bb_day: dict) -> dict:
    # The stress endpoint carries a much denser Body Battery series than the Body Battery endpoint.
    bb_points = max(
        packed_series(stress_raw.get("bodyBatteryValuesArray"), stress_raw.get("bodyBatteryValueDescriptorsDTOList"), "bodyBatteryLevel", 2),
        packed_series(bb_day.get("bodyBatteryValuesArray"), bb_day.get("bodyBatteryValueDescriptorDTOList"), "bodyBatteryLevel", 1),
        key=len,
    )
    stress_points = [
        (t, v) for t, v in packed_series(stress_raw.get("stressValuesArray"), stress_raw.get("stressValueDescriptorsDTOList"), "stressLevel", 1)
        if num(v) is not None and v >= 0
    ]
    return {
        "sleep_stages": sleep_stage_segments(sleep_raw),  # [start, end, stage]
        "sleep_hr": bucket(((gmt_to_local(p.get("startGMT")), p.get("value")) for p in sleep_raw.get("sleepHeartRate") or [] if isinstance(p, dict)), 10),
        "hrv_overnight": bucket(((gmt_to_local(r.get("readingTimeGMT")), r.get("hrvValue")) for r in hrv_raw.get("hrvReadings") or [] if isinstance(r, dict)), 15),
        "body_battery": bucket(bb_points, 15),
        "stress_hourly": bucket(stress_points, 60),
    }


def build_day(day: str, raw: dict, bb_day: dict, now: datetime) -> dict:
    s = raw.get("summary") or {}
    sleep_raw, hrv_raw, stress_raw = raw.get("sleep") or {}, raw.get("hrv") or {}, raw.get("stress") or {}
    in_progress = day == now.date().isoformat()
    return clean({
        "date": day,
        "day_in_progress": True if in_progress else None,
        "updated": now.strftime("%H:%M") if in_progress else None,
        "sleep": build_sleep(sleep_raw),
        "hrv": build_hrv(hrv_raw),
        "resting_hr": {
            "today": s.get("restingHeartRate") or sleep_raw.get("restingHeartRate"),
            "avg_7d": s.get("lastSevenDaysAvgRestingHeartRate"),
        },
        "body_battery": build_body_battery(s, bb_day),
        "stress": build_stress(s),
        "steps": {
            "total": s.get("totalSteps"),
            "goal": s.get("dailyStepGoal"),
            "distance_km": rnd((num(s.get("totalDistanceMeters")) or 0) / 1000, 2) if num(s.get("totalDistanceMeters")) else None,
            "floors": rnd(s.get("floorsAscended"), 0),
        },
        "energy": {
            "active_kcal": rnd(s.get("activeKilocalories"), 0),
            "total_kcal": rnd(s.get("totalKilocalories"), 0),
            "intensity_min_moderate": s.get("moderateIntensityMinutes"),
            "intensity_min_vigorous": s.get("vigorousIntensityMinutes"),
        },
        "training_readiness": build_readiness(raw.get("readiness")),
        "training_status": build_training_status(raw.get("training_status")),
        "curves": build_curves(sleep_raw, hrv_raw, stress_raw, bb_day),
    })


# ----------------------------------------------------------------------- activities


def sport_group(type_key: str) -> str:
    k = type_key.lower()
    if any(w in k for w in ("cycl", "bik", "ride", "gravel")):
        return "cycling"
    if "run" in k:
        return "running"
    if "swim" in k:
        return "swimming"
    if any(w in k for w in ("walk", "hik")):
        return "walking/hiking"
    if any(w in k for w in ("strength", "fitness", "hiit", "yoga", "pilates", "cardio")):
        return "strength/fitness"
    return "other"


def zone_minutes(a: dict, prefix: str, count: int) -> list[int] | None:
    zones = [minutes(a.get(f"{prefix}{i}")) for i in range(1, count + 1)]
    return [z or 0 for z in zones] if any(zones) else None


def build_activity(a: dict, devices: dict) -> dict:
    type_key = dig(a, "activityType", "typeKey") or "other"
    start = (a.get("startTimeLocal") or "")[:16].replace(" ", "T")
    speed = num(a.get("averageSpeed"))
    distance = num(a.get("distance"))
    return clean({
        "id": a.get("activityId"),
        "name": a.get("activityName"),
        "type": type_key,
        "sport": sport_group(type_key),
        "date": start[:10],
        "start": start,
        "device": devices.get(str(a.get("deviceId"))),
        "duration_min": rnd((num(a.get("duration")) or 0) / 60, 0),
        "moving_min": rnd(num(a.get("movingDuration")) / 60, 0) if num(a.get("movingDuration")) else None,
        "distance_km": rnd(distance / 1000, 2) if distance else None,
        "avg_speed_kmh": rnd(speed * 3.6) if speed else None,
        "max_speed_kmh": rnd(num(a.get("maxSpeed")) * 3.6) if num(a.get("maxSpeed")) else None,
        "elevation_gain_m": rnd(a.get("elevationGain"), 0),
        "avg_hr": rnd(a.get("averageHR"), 0),
        "max_hr": rnd(a.get("maxHR"), 0),
        "avg_power": rnd(a.get("avgPower"), 0),
        "norm_power": rnd(a.get("normPower"), 0),
        "max_power": rnd(a.get("maxPower"), 0),
        "max_20min_power": rnd(a.get("max20MinPower"), 0),
        "avg_cadence": rnd(a.get("averageBikingCadenceInRevPerMinute") or a.get("averageRunningCadenceInStepsPerMinute"), 0),
        "calories": rnd(a.get("calories"), 0),
        "training_load": rnd(a.get("activityTrainingLoad"), 0),
        "tss": rnd(a.get("trainingStressScore"), 0),
        "intensity_factor": rnd(a.get("intensityFactor"), 2),
        "aerobic_te": rnd(a.get("aerobicTrainingEffect")),
        "anaerobic_te": rnd(a.get("anaerobicTrainingEffect")),
        "primary_benefit": label(a.get("trainingEffectLabel")),
        "aerobic_te_message": phrase(a.get("aerobicTrainingEffectMessage")),
        "anaerobic_te_message": phrase(a.get("anaerobicTrainingEffectMessage")),
        "hr_zones_min": zone_minutes(a, "hrTimeInZone_", 5),
        "power_zones_min": zone_minutes(a, "powerTimeInZone_", 7),
        "body_battery_impact": a.get("differenceBodyBattery"),
        "avg_temp_c": rnd(a.get("averageTemperature") if a.get("averageTemperature") is not None else a.get("avgTemperature")),
        "vo2max": a.get("vO2MaxValue"),
        "description": a.get("description"),
    })


def flag_overlaps(activities: list[dict]) -> None:
    """Fenix and Edge can record the same ride twice - mark such pairs."""
    for a in activities:
        a.pop("overlaps_with", None)
    ordered = sorted(activities, key=lambda a: a.get("start") or "")
    for prev, cur in zip(ordered, ordered[1:]):
        try:
            gap = datetime.fromisoformat(cur["start"]) - datetime.fromisoformat(prev["start"])
        except (KeyError, ValueError):
            continue
        if prev.get("sport") == cur.get("sport") and gap <= timedelta(minutes=15):
            cur["overlaps_with"] = prev.get("id")
            prev["overlaps_with"] = cur.get("id")


def build_athlete(ftp_raw: Any, zones_raw: Any) -> dict:
    ftp = ftp_raw[0] if isinstance(ftp_raw, list) and ftp_raw else ftp_raw
    keep = ("sport", "trainingMethod", "restingHeartRateUsed", "lactateThresholdHeartRateUsed",
            "maxHeartRateUsed", "zone1Floor", "zone2Floor", "zone3Floor", "zone4Floor", "zone5Floor")
    zones = [{k: z.get(k) for k in keep} for z in zones_raw or [] if isinstance(z, dict)]
    return clean({
        "cycling_ftp_w": dig(ftp, "functionalThresholdPower"),
        "cycling_ftp_date": dig(ftp, "calendarDate"),
        "heart_rate_zones": zones,
    })


# --------------------------------------------------------------- markdown notes


def fmt_min(m: Any) -> str:
    if num(m) is None:
        return "–"
    h, mm = divmod(round(m), 60)
    return f"{h} h {mm:02d} min" if h else f"{mm} min"


def fmt(v: Any, unit: str = "", digits: int = 0) -> str:
    if v is None:
        return "–"
    text = f"{v:,.{digits}f}" if num(v) is not None else str(v)
    return f"{text} {unit}".strip()


def long_date(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"


def bar(value: Any, maximum: Any, width: int = 20) -> str:
    if not num(value) or not num(maximum):
        return ""
    return "█" * max(1, round(width * value / maximum))


def te_word(v: Any) -> str:
    if num(v) is None:
        return "–"
    for limit, word in ((1, "no effect"), (2, "minor"), (3, "maintaining"), (4, "improving"), (5, "highly improving")):
        if v < limit:
            return word
    return "overreaching"


def stress_word(v: Any) -> str:
    if num(v) is None:
        return "–"
    return "resting" if v <= 25 else "low" if v <= 50 else "medium" if v <= 75 else "high"


def frontmatter(fields: dict) -> list[str]:
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items() if v is not None] + ["---", ""]
    return lines


def table(rows: list[tuple[str, str]]) -> list[str]:
    rows = [r for r in rows if r[1] not in ("–", "", None)]
    if not rows:
        return ["No data."]
    return ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]


def pretty_type(type_key: str) -> str:
    return type_key.replace("_", " ").capitalize()


def activity_filename(act: dict) -> str:
    return f"{act.get('date')}_{act.get('type', 'other')}_{act.get('id')}.md"


def wellness_note(d: dict, workouts: list[dict]) -> str:
    sl, hrv, rhr = d.get("sleep") or {}, d.get("hrv") or {}, d.get("resting_hr") or {}
    bb, st, steps = d.get("body_battery") or {}, d.get("stress") or {}, d.get("steps") or {}
    energy, ts = d.get("energy") or {}, d.get("training_status") or {}
    tr = (d.get("training_readiness") or {}).get("morning") or {}

    out = frontmatter({
        "date": d["date"],
        "sleep_hours": rnd((sl.get("total_min") or 0) / 60) if sl else None,
        "sleep_score": sl.get("score"),
        "hrv_ms": hrv.get("last_night_avg"),
        "hrv_status": hrv.get("status"),
        "resting_hr": rhr.get("today"),
        "body_battery_at_wake": bb.get("at_wake"),
        "training_readiness": tr.get("score"),
        "stress_avg": st.get("avg"),
        "steps": steps.get("total"),
    })
    out.append(f"# Wellness · {long_date(d['date'])}")
    out.append("")
    if d.get("day_in_progress"):
        out += [f"> Updated at {d.get('updated')}. This day is still in progress, so steps, stress and Body Battery will keep changing.", ""]

    summary = []
    if sl:
        summary.append(f"**Sleep:** {fmt_min(sl.get('total_min'))}, sleep score {fmt(sl.get('score'))} ({sl.get('quality') or 'no rating'}).")
    if hrv:
        rng = f" Your balanced range is {hrv['baseline_low']}–{hrv['baseline_high']} ms." if hrv.get("baseline_low") and hrv.get("baseline_high") else ""
        summary.append(f"**HRV:** {fmt(hrv.get('last_night_avg'), 'ms')} overnight, status {hrv.get('status') or 'unknown'}.{rng}")
    if rhr.get("today"):
        summary.append(f"**Resting heart rate:** {rhr['today']} bpm (7-day average {fmt(rhr.get('avg_7d'), 'bpm')}).")
    if bb.get("at_wake") is not None or bb.get("highest") is not None:
        summary.append(f"**Body Battery:** {fmt(bb.get('at_wake'))} when you woke up, highest {fmt(bb.get('highest'))}, lowest {fmt(bb.get('lowest'))}, latest {fmt(bb.get('latest'))}.")
    if tr:
        summary.append(f"**Training readiness:** {tr.get('score')} ({tr.get('level') or '–'}) this morning" + (f" – {tr['feedback']}." if tr.get("feedback") else "."))
    if ts.get("status"):
        summary.append(f"**Training status:** {ts['status']}" + (f", load ratio {ts['load_ratio']} ({ts.get('load_ratio_status') or '–'})." if ts.get("load_ratio") is not None else "."))
    if st.get("avg") is not None:
        summary.append(f"**Stress:** average {st['avg']} ({stress_word(st['avg'])}), peak {fmt(st.get('max'))}.")
    if steps.get("total") is not None:
        summary.append(f"**Steps:** {fmt(steps['total'])} of {fmt(steps.get('goal'))} goal.")
    out += ["## In short", ""] + ([f"- {s}" for s in summary] or ["No data for this day."]) + [""]

    out += ["## Sleep", ""]
    if sl:
        total = sl.get("total_min") or 0

        def share(m: Any) -> str:
            return f"{fmt_min(m)} ({round(100 * m / total)} %)" if num(m) is not None and total else fmt_min(m)

        start, end = (sl.get("start") or "")[11:16], (sl.get("end") or "")[11:16]
        out += table([
            ("Asleep", f"{start} → {end}" if start and end else "–"),
            ("Total sleep", fmt_min(sl.get("total_min"))),
            ("Sleep need (Garmin)", fmt_min(sl.get("need_min"))),
            ("Deep", share(sl.get("deep_min"))),
            ("Light", share(sl.get("light_min"))),
            ("REM", share(sl.get("rem_min"))),
            ("Awake", fmt_min(sl.get("awake_min"))),
            ("Times awake", fmt(sl.get("awake_count"))),
            ("Sleep score", f"{fmt(sl.get('score'))} ({sl.get('quality') or '–'})"),
            ("Garmin's feedback", sl.get("feedback") or "–"),
            ("Average heart rate asleep", fmt(sl.get("avg_hr"), "bpm")),
            ("Average breathing rate", fmt(sl.get("avg_respiration"), "breaths/min", 1)),
            ("Average blood oxygen (SpO2)", fmt(sl.get("avg_spo2"), "%", 0)),
            ("Average stress while asleep", fmt(sl.get("avg_sleep_stress"), "", 0)),
            ("Body Battery recharged", f"+{sl['body_battery_gain']}" if sl.get("body_battery_gain") is not None else "–"),
            ("Naps", fmt_min(sl.get("nap_min")) if sl.get("nap_min") else "–"),
        ])
    else:
        out.append("No sleep recorded.")
    out.append("")

    out += ["## Heart rate variability (HRV)", ""]
    out += table([
        ("Last night average", fmt(hrv.get("last_night_avg"), "ms")),
        ("Highest 5-minute value", fmt(hrv.get("last_night_high_5min"), "ms")),
        ("7-day average", fmt(hrv.get("weekly_avg"), "ms")),
        ("Balanced range", f"{hrv['baseline_low']}–{hrv['baseline_high']} ms" if hrv.get("baseline_low") and hrv.get("baseline_high") else "–"),
        ("Status", hrv.get("status") or "–"),
        ("Garmin's feedback", hrv.get("feedback") or "–"),
    ]) if hrv else ["No HRV recorded."]
    out.append("")

    out += ["## Training readiness", ""]
    if tr:
        f_pct, f_rating = tr.get("factors_pct") or {}, tr.get("factors_rating") or {}
        names = {"sleep": "Sleep score", "sleep_history": "Sleep history", "hrv": "HRV status",
                 "recovery_time": "Recovery time", "acute_load": "Acute load", "stress_history": "Stress history"}
        out += [f"Score **{tr.get('score')}** ({tr.get('level') or '–'}) at {tr.get('time') or '–'}."
                + (f" Recovery time left: {fmt(tr.get('recovery_time_h'), 'h', 0)}." if tr.get("recovery_time_h") is not None else ""), ""]
        out += ["| Factor | Rating | Contribution |", "|---|---|---|"]
        out += [f"| {names[k]} | {f_rating.get(k) or '–'} | {fmt(f_pct.get(k), '%')} |" for k in names if k in f_pct or k in f_rating]
    else:
        out.append("No training readiness recorded.")
    out.append("")

    out += ["## Training status", ""]
    if ts:
        focus = ts.get("load_focus_4_weeks") or {}

        def target(key: str) -> str:
            lo_hi = focus.get(f"{key}_target") or []
            return f"{fmt(focus.get(key))} (target {lo_hi[0]}–{lo_hi[1]})" if len(lo_hi) == 2 and None not in lo_hi else fmt(focus.get(key))

        out += table([
            ("Status", ts.get("status") or "–"),
            ("7-day training load", fmt(ts.get("weekly_load"))),
            ("Acute load (short-term)", fmt(ts.get("acute_load"))),
            ("Chronic load (long-term)", fmt(ts.get("chronic_load"))),
            ("Load ratio (acute ÷ chronic)", f"{ts['load_ratio']} ({ts.get('load_ratio_status') or '–'})" if ts.get("load_ratio") is not None else "–"),
            ("VO2max cycling", fmt(ts.get("vo2max_cycling"), "", 1)),
            ("VO2max running", fmt(ts.get("vo2max_running"), "", 1)),
            ("4-week load: low aerobic", target("low_aerobic")),
            ("4-week load: high aerobic", target("high_aerobic")),
            ("4-week load: anaerobic", target("anaerobic")),
            ("Load focus feedback", focus.get("feedback") or "–"),
        ])
    else:
        out.append("No training status recorded.")
    out.append("")

    out += ["## Body Battery", ""]
    out += table([
        ("At wake-up", fmt(bb.get("at_wake"))),
        ("Highest", fmt(bb.get("highest"))),
        ("Lowest", fmt(bb.get("lowest"))),
        ("Latest", fmt(bb.get("latest"))),
        ("Charged", f"+{bb['charged']}" if bb.get("charged") is not None else "–"),
        ("Drained", f"−{bb['drained']}" if bb.get("drained") is not None else "–"),
    ])
    if bb.get("events"):
        out += ["", "| Time | Event | Duration | Impact | Feedback |", "|---|---|---|---|---|"]
        out += [f"| {e.get('start') or '–'} | {e.get('type') or '–'} | {fmt_min(e.get('duration_min'))} | {e.get('impact', '–')} | {e.get('feedback') or '–'} |" for e in bb["events"]]
    out.append("")

    out += ["## Stress", ""]
    durations = [("Resting", st.get("rest_min")), ("Low", st.get("low_min")), ("Medium", st.get("medium_min")),
                 ("High", st.get("high_min")), ("During activity", st.get("activity_min"))]
    longest = max((m for _, m in durations if num(m)), default=0)
    if st.get("avg") is not None:
        out += [f"Average {st['avg']} ({stress_word(st['avg'])}), peak {fmt(st.get('max'))}.", ""]
    if longest:
        out += ["| Level | Time | |", "|---|---|---|"] + [f"| {n} | {fmt_min(m)} | {bar(m, longest)} |" for n, m in durations if num(m) is not None]
    elif st.get("avg") is None:
        out.append("No stress data.")
    out.append("")

    out += ["## Steps and activity", ""]
    out += table([
        ("Steps", f"{fmt(steps.get('total'))} (goal {fmt(steps.get('goal'))})" if steps.get("total") is not None else "–"),
        ("Distance on foot and on the move", fmt(steps.get("distance_km"), "km", 1)),
        ("Floors climbed", fmt(steps.get("floors"))),
        ("Active calories", fmt(energy.get("active_kcal"), "kcal")),
        ("Total calories", fmt(energy.get("total_kcal"), "kcal")),
        ("Intensity minutes (moderate / vigorous)", f"{fmt(energy.get('intensity_min_moderate'))} / {fmt(energy.get('intensity_min_vigorous'))}" if energy.get("intensity_min_moderate") is not None else "–"),
    ])
    out.append("")

    out += ["## Workouts", ""]
    if workouts:
        for w in workouts:
            bits = [fmt_min(w.get("duration_min"))]
            if w.get("distance_km"):
                bits.append(f"{w['distance_km']:.1f} km")
            if w.get("training_load") is not None:
                bits.append(f"load {w['training_load']}")
            out.append(f"- [{(w.get('start') or '')[11:16]} {pretty_type(w.get('type', 'other'))} – {', '.join(bits)}](../activities/{activity_filename(w)})")
    else:
        out.append("No workouts recorded.")
    out.append("")
    return "\n".join(out)


def activity_note(a: dict) -> str:
    out = frontmatter({
        "id": a.get("id"),
        "date": a.get("date"),
        "start": a.get("start"),
        "type": a.get("type"),
        "sport": a.get("sport"),
        "duration_min": a.get("duration_min"),
        "distance_km": a.get("distance_km"),
        "training_load": a.get("training_load"),
        "aerobic_te": a.get("aerobic_te"),
        "anaerobic_te": a.get("anaerobic_te"),
        "primary_benefit": a.get("primary_benefit"),
    })
    out.append(f"# {pretty_type(a.get('type', 'other'))} · {long_date(a['date'])}, {(a.get('start') or '')[11:16]}")
    out.append("")
    head = f"**{a.get('name') or 'Workout'}**"
    if a.get("device"):
        head += f" · recorded with {a['device']}"
    out += [head, ""]
    if a.get("overlaps_with"):
        out += [f"> This workout overlaps with activity {a['overlaps_with']} – probably the same session recorded on two devices. Count its training load only once.", ""]

    sentence = [f"{fmt_min(a.get('duration_min'))} of {pretty_type(a.get('type', 'other')).lower()}"]
    if a.get("distance_km"):
        sentence.append(f" over {a['distance_km']:.1f} km")
    if a.get("avg_speed_kmh") and a.get("sport") == "cycling":
        sentence.append(f" at an average of {a['avg_speed_kmh']:.1f} km/h")
    if a.get("elevation_gain_m"):
        sentence.append(f" with {a['elevation_gain_m']} m of climbing")
    text = "".join(sentence) + "."
    if a.get("avg_hr"):
        text += f" Average heart rate {a['avg_hr']} bpm (max {fmt(a.get('max_hr'))})."
    if a.get("avg_power"):
        text += f" Average power {a['avg_power']} W" + (f", normalized {a['norm_power']} W" if a.get("norm_power") else "") + "."
    if a.get("aerobic_te") is not None:
        text += (f" Training effect: aerobic {a['aerobic_te']} ({te_word(a['aerobic_te'])}),"
                 f" anaerobic {fmt(a.get('anaerobic_te'), '', 1)} ({te_word(a.get('anaerobic_te'))}).")
    if a.get("primary_benefit"):
        text += f" Main benefit according to Garmin: **{a['primary_benefit']}**."
    if a.get("training_load") is not None:
        text += f" Training load {a['training_load']}."
    out += ["## In short", "", text, ""]

    out += ["## Numbers", ""]
    out += table([
        ("Start", (a.get("start") or "").replace("T", " ")),
        ("Duration (moving)", f"{fmt_min(a.get('duration_min'))} ({fmt_min(a.get('moving_min'))})" if a.get("moving_min") else fmt_min(a.get("duration_min"))),
        ("Distance", fmt(a.get("distance_km"), "km", 2)),
        ("Average / max speed", f"{fmt(a.get('avg_speed_kmh'), '', 1)} / {fmt(a.get('max_speed_kmh'), 'km/h', 1)}" if a.get("avg_speed_kmh") else "–"),
        ("Climbing", fmt(a.get("elevation_gain_m"), "m")),
        ("Average / max heart rate", f"{fmt(a.get('avg_hr'))} / {fmt(a.get('max_hr'), 'bpm')}" if a.get("avg_hr") else "–"),
        ("Average / normalized / max power", f"{fmt(a.get('avg_power'))} / {fmt(a.get('norm_power'))} / {fmt(a.get('max_power'), 'W')}" if a.get("avg_power") else "–"),
        ("Best 20-minute power", fmt(a.get("max_20min_power"), "W")),
        ("Average cadence", fmt(a.get("avg_cadence"), "rpm" if a.get("sport") == "cycling" else "spm")),
        ("Training Stress Score (TSS)", fmt(a.get("tss"))),
        ("Intensity factor (IF)", fmt(a.get("intensity_factor"), "", 2)),
        ("Garmin training load", fmt(a.get("training_load"))),
        ("Aerobic training effect", f"{a['aerobic_te']} – {te_word(a['aerobic_te'])}" if a.get("aerobic_te") is not None else "–"),
        ("Anaerobic training effect", f"{a['anaerobic_te']} – {te_word(a['anaerobic_te'])}" if a.get("anaerobic_te") is not None else "–"),
        ("Main benefit", a.get("primary_benefit") or "–"),
        ("Body Battery impact", fmt(a.get("body_battery_impact"))),
        ("Calories", fmt(a.get("calories"), "kcal")),
        ("Average temperature", fmt(a.get("avg_temp_c"), "°C", 0)),
    ])
    out.append("")

    for title, key, n in (("Time in heart-rate zones", "hr_zones_min", 5), ("Time in power zones", "power_zones_min", 7)):
        zones = a.get(key)
        if not zones:
            continue
        top = max(zones) or 1
        out += [f"## {title}", "", "| Zone | Time | |", "|---|---|---|"]
        out += [f"| Z{i} | {fmt_min(m)} | {bar(m, top)} |" for i, m in enumerate(zones[:n], start=1)]
        out.append("")

    if a.get("description"):
        out += ["## Your notes", "", a["description"], ""]
    return "\n".join(out)


# ----------------------------------------------------------------------------- main


def load_existing(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def print_summary(data: dict, days: list[str], new_acts: list[dict], missing: list[str]) -> None:
    print(f"\nSynced {len(days)} day(s) ({days[0]} to {days[-1]}) and {len(new_acts)} workout(s).\n")
    print(f"{'Date':<11} {'Sleep':>12} {'Score':>5} {'HRV':>4} {'RHR':>4} {'BB wake':>7} {'Ready':>5} {'Stress':>6} {'Steps':>7}")
    for day in days:
        d = data["days"].get(day, {})
        sl = d.get("sleep") or {}
        print(f"{day:<11} {fmt_min(sl.get('total_min')):>12} {fmt(sl.get('score')):>5} "
              f"{fmt(dig(d, 'hrv', 'last_night_avg')):>4} {fmt(dig(d, 'resting_hr', 'today')):>4} "
              f"{fmt(dig(d, 'body_battery', 'at_wake')):>7} {fmt(dig(d, 'training_readiness', 'morning', 'score')):>5} "
              f"{fmt(dig(d, 'stress', 'avg')):>6} {fmt(dig(d, 'steps', 'total')):>7}")
    if new_acts:
        print("\nWorkouts:")
        for a in sorted(new_acts, key=lambda a: a.get("start") or ""):
            print(f"  {(a.get('start') or '').replace('T', ' ')}  {pretty_type(a.get('type', 'other')):<20} "
                  f"{fmt_min(a.get('duration_min')):>12}  {fmt(a.get('distance_km'), 'km', 1):>9}  "
                  f"TE {fmt(a.get('aerobic_te'), '', 1)}/{fmt(a.get('anaerobic_te'), '', 1)}  load {fmt(a.get('training_load'))}")
    if missing:
        print(f"\nNot available from Garmin ({len(missing)}): " + "; ".join(missing))
    print(f"\nNotes and data.json written to: {OUT_DIR}")


def days_to_sync(arg: str, last_sync: str | None, today: date) -> int:
    """A number of days as given, or 'auto': every day since the last sync, so a pause leaves no gap."""
    if arg != "auto":
        return int(arg)
    low, high = AUTO_DAYS
    try:
        last = datetime.fromisoformat(last_sync).date()
    except (TypeError, ValueError):
        return high
    return max(low, min(high, (today - last).days + 1))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Read-only Garmin Connect sync.")
    parser.add_argument("--days", default="3",
                        help="how many days back to sync, including today (default 3), or 'auto' for every day "
                             "since the last sync")
    args = parser.parse_args()
    if args.days != "auto" and not (args.days.isdigit() and 1 <= int(args.days) <= 365):
        parser.error("--days must be 'auto' or a number between 1 and 365")

    now = datetime.now(TZ)
    data_path = OUT_DIR / "data.json"
    data = load_existing(data_path)
    data.setdefault("days", {})
    count = days_to_sync(args.days, data.get("last_sync"), now.date())
    days = [(now.date() - timedelta(days=i)).isoformat() for i in range(count - 1, -1, -1)]

    try:
        api = connect()
    except GarminConnectAuthenticationError:
        print("Your Garmin login is missing or has expired. Run login.py once to log in again.")
        return 2
    except GarminConnectTooManyRequestsError:
        print("Garmin is rate-limiting requests right now. Please try again in an hour.")
        return 3
    except GarminConnectConnectionError as err:
        print(f"Could not connect to Garmin: {err}")
        return 1

    fetch = Fetcher()

    try:
        devices = {str(d.get("deviceId")): d.get("productDisplayName") or d.get("displayName")
                   for d in fetch("devices", api.get_devices) or [] if isinstance(d, dict)}
        athlete = build_athlete(fetch("cycling FTP", api.get_cycling_ftp), fetch("heart-rate zones", api.get_heart_rate_zones))

        bb_by_date = {e.get("date"): e for e in fetch("body battery", api.get_body_battery, days[0], days[-1]) or [] if isinstance(e, dict)}
        for day in days:
            print(f"Fetching {day} ...")
            raw = {
                "summary": fetch(f"{day} daily summary", api.get_user_summary, day),
                "sleep": fetch(f"{day} sleep", api.get_sleep_data, day),
                "hrv": fetch(f"{day} HRV", api.get_hrv_data, day),
                "stress": fetch(f"{day} stress", api.get_stress_data, day),
                "readiness": fetch(f"{day} training readiness", api.get_training_readiness, day),
                "training_status": fetch(f"{day} training status", api.get_training_status, day),
            }
            data["days"][day] = build_day(day, raw, bb_by_date.get(day) or {}, now)

        print("Fetching workouts ...")
        new_acts = [build_activity(a, devices or data.get("devices", {}))
                    for a in fetch("activities", api.get_activities_by_date, days[0], days[-1]) or [] if isinstance(a, dict)]
    except GarminConnectAuthenticationError:
        print("Garmin rejected the saved login. Run login.py once to log in again.")
        return 2
    except GarminConnectTooManyRequestsError:
        print("Garmin is rate-limiting requests right now. Please try again in an hour.")
        return 3

    activities = {a["id"]: a for a in data.get("activities", []) if a.get("id")}
    activities.update({a["id"]: a for a in new_acts if a.get("id")})
    all_acts = sorted(activities.values(), key=lambda a: a.get("start") or "", reverse=True)
    flag_overlaps(all_acts)

    curve_cutoff = (now.date() - timedelta(days=CURVE_DAYS - 1)).isoformat()
    for day, rec in data["days"].items():
        if day < curve_cutoff:
            rec.pop("curves", None)

    data = {
        "about": "Garmin Connect data synced read-only by sync.py. Newest activities first.",
        "last_sync": now.isoformat(timespec="seconds"),
        "timezone": str(TZ),
        "units": UNITS,
        "athlete": athlete or data.get("athlete", {}),
        "devices": devices or data.get("devices", {}),
        "days": dict(sorted(data["days"].items())),
        "activities": all_acts,
    }
    write_text(data_path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    for day in days:
        workouts = sorted((a for a in all_acts if a.get("date") == day), key=lambda a: a.get("start") or "")
        write_text(OUT_DIR / "wellness" / f"{day}.md", wellness_note(data["days"][day], workouts))
    synced_ids = {a.get("id") for a in new_acts}
    for a in all_acts:
        if a.get("id") in synced_ids or a.get("overlaps_with") in synced_ids:
            write_text(OUT_DIR / "activities" / activity_filename(a), activity_note(a))

    print_summary(data, days, new_acts, fetch.missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
