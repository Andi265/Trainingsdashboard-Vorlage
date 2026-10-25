"""Small builders for test data in the shape of data/data.json."""

from __future__ import annotations


def make_day(readiness=None, recovery_h=None, ratio=None, hrv=None, hrv_low=None, hrv_high=None,
             sleep=None, rhr=None, rhr_avg=None) -> dict:
    """One `data["days"]` record; arguments left as None are simply missing, like on a day without sync."""
    day: dict = {}
    if readiness is not None or recovery_h is not None:
        morning = {}
        if readiness is not None:
            morning["score"] = readiness
        if recovery_h is not None:
            morning["recovery_time_h"] = recovery_h
        day["training_readiness"] = {"morning": morning, "latest": dict(morning)}
    if ratio is not None:
        day["training_status"] = {"load_ratio": ratio}
    if hrv is not None or hrv_low is not None:
        hrv_rec = {}
        if hrv is not None:
            hrv_rec["last_night_avg"] = hrv
        if hrv_low is not None:
            hrv_rec["baseline_low"] = hrv_low
        if hrv_high is not None:
            hrv_rec["baseline_high"] = hrv_high
        day["hrv"] = hrv_rec
    if sleep is not None:
        day["sleep"] = {"score": sleep, "total_min": 450}
    if rhr is not None or rhr_avg is not None:
        rhr_rec = {}
        if rhr is not None:
            rhr_rec["today"] = rhr
        if rhr_avg is not None:
            rhr_rec["avg_7d"] = rhr_avg
        day["resting_hr"] = rhr_rec
    return day


def make_activity(date: str, te_aer: float = 2.0, te_ana: float = 0.0, benefit: str = "aerobic base",
                  load: float = 60, sport: str = "cycling", ident: int | None = None) -> dict:
    """One `data["activities"]` record."""
    return {"id": ident or int(date.replace("-", "")), "date": date, "start": f"{date}T17:00", "sport": sport,
            "type": "road_biking" if sport == "cycling" else sport, "aerobic_te": te_aer, "anaerobic_te": te_ana,
            "primary_benefit": benefit, "training_load": load, "duration_min": 60}
