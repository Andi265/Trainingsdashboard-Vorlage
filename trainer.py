"""Personal trainer: profile, season plan, rolling schedule, rule checks and the rest-day assessment.

The single place for all training settings and rules. briefing.py, the routines and the settings
skill use these functions and the small command line below. Claude makes the coaching decisions;
this module checks them against the fixed rules before anything is saved.

Standard library only, so the cloud routines can run it as is.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SPORTS = ("cycling", "running", "swimming", "strength")
MULTISPORT = {"triathlon": ("swimming", "cycling", "running"), "duathlon": ("running", "cycling")}
GOAL_TYPES = ("event", "discipline", "fitness")
PRIORITIES = ("A", "B", "C")
DAY_SPORTS = SPORTS + ("brick", "rest")
DAY_KINDS = ("rest", "rest_expected", "easy", "normal", "key", "long", "strength")
DAY_STATUS = ("planned", "done", "changed")
DAY_FIELDS = ("status", "kind", "sport", "session", "duration_min", "reason")
PHASE_FOCI = ("base", "build", "specific", "taper", "race", "recovery", "vo2max", "anaerobic", "threshold",
              "climbing", "tempo")
STRENGTH_PHASES = ("off", "adaptation", "max", "maintenance")
TAPER_DAYS = {"A": (7, 14), "B": (2, 3), "C": (2, 3)}


def default_profile() -> dict:
    """The profile that applies until the athlete has set up their training."""
    return {
        "version": 1, "updated": "2026-10-25", "setup_done": False,
        "sports": ["cycling"], "multisport": None,
        "goal": {"type": "fitness", "fitness": {"focus": ["vo2max", "anaerobic", "base"]}},
        "secondary_events": [],
        "availability": {
            "hours": {"mon": 1.5, "tue": 1.5, "wed": 1.5, "thu": 1.5, "fri": 1.5, "sat": 3.5, "sun": 3.5},
            "long_days": [],
            "rest_days": {"mode": "dynamic", "days": [], "min_per_cycle": 1},
        },
        "strength": {"enabled": False, "confirmed_at": None, "location": None, "equipment": [],
                     "experience": None, "per_cycle": 0},
        "thresholds": {"cycling_ftp_w": {"source": "garmin"}, "running_threshold_pace": None, "running_lthr": None,
                       "swim_css_per_100m": None, "max_hr": {"source": "garmin"}},
        "constraints": {"injuries": "", "indoor_zwift": True, "power_meter_bikes": [], "pool_length_m": 25,
                        "age": None},
        "rest_rules": {"readiness_low": 50, "recovery_time_h": 24, "load_ratio": 1.3, "sleep_score": 70,
                       "rhr_delta": 3, "rhr_alarm": 5, "days_in_row": 6, "signals_for_rest": 3},
    }


def _load(root: Path, name: str, empty: dict) -> dict:
    try:
        return json.loads((root / "training" / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty


def load_profile(root: Path = ROOT) -> dict:
    return _load(root, "profile.json", default_profile())


def load_season(root: Path = ROOT) -> dict:
    return _load(root, "season.json", {"phases": []})


def load_schedule(root: Path = ROOT) -> dict:
    return _load(root, "schedule.json", {"days": []})


def load_sessions(root: Path = ROOT) -> dict:
    """The workout library: session id -> spec entry (without `sport` it counts as cycling)."""
    return _load(root, "sessions.json", {"sessions": {}}).get("sessions", {})


def _iso(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _amount_errors(label: str, node: dict) -> list[str]:
    """Distance and elevation must be numbers; for triathlon/duathlon the distance is one number per sport."""
    errors = []
    distance = node.get("distance_km")
    values = distance.values() if isinstance(distance, dict) else [distance]
    if any(v is not None and _num(v) is None for v in values):
        errors.append(f"{label} muss die Distanz eine Zahl in km sein (bei Triathlon/Duathlon je Sportart).")
    if node.get("elevation_m") is not None and _num(node["elevation_m"]) is None:
        errors.append(f"{label} müssen die Höhenmeter eine Zahl sein.")
    return errors


def validate_profile(p: dict) -> list[str]:
    """Check the profile; returns German error messages, an empty list means valid."""
    errors = []
    sports = p.get("sports") or []
    for sport in sports:
        if sport not in SPORTS:
            errors.append(f"Unbekannte Sportart „{sport}“ (erlaubt: {', '.join(SPORTS)}).")
    if not sports:
        errors.append("Es ist keine Sportart gewählt.")
    multi = p.get("multisport")
    if multi is not None:
        if multi not in MULTISPORT:
            errors.append(f"Unbekannter Mehrkampf „{multi}“ (erlaubt: triathlon, duathlon).")
        else:
            missing = [s for s in MULTISPORT[multi] if s not in sports]
            if missing:
                errors.append(f"Für {multi} fehlen die Sportarten: {', '.join(missing)}.")

    goal = p.get("goal") or {}
    kind = goal.get("type")
    if kind not in GOAL_TYPES:
        errors.append(f"Unbekannte Zielart „{kind}“ (erlaubt: event, discipline, fitness).")
    elif kind == "event":
        event = goal.get("event") or {}
        if not event.get("name"):
            errors.append("Beim Wettkampfziel fehlt der Name.")
        if not _iso(event.get("date")):
            errors.append("Beim Wettkampfziel fehlt ein gültiges Datum (JJJJ-MM-TT).")
        if event.get("priority", "A") not in PRIORITIES:
            errors.append("Die Priorität des Wettkampfs muss A, B oder C sein.")
        errors += _amount_errors("Beim Wettkampfziel", event)
    elif kind == "discipline":
        discipline = goal.get("discipline") or {}
        if not discipline.get("sport") or not discipline.get("focus"):
            errors.append("Beim Disziplinziel fehlen Sportart oder Schwerpunkt.")
        errors += _amount_errors("Beim Disziplinziel", discipline)
    for event in p.get("secondary_events") or []:
        errors += _amount_errors(f"Beim Wettkampf „{event.get('name', '?')}“", event)

    availability = p.get("availability") or {}
    hours = availability.get("hours") or {}
    for day in hours:
        if day not in WEEKDAYS:
            errors.append(f"Unbekannter Wochentag „{day}“ im Zeitbudget.")
    for long_day in availability.get("long_days") or []:
        if long_day.get("day") not in WEEKDAYS:
            errors.append(f"Unbekannter Wochentag „{long_day.get('day')}“ bei den langen Einheiten.")
        if long_day.get("sport") not in SPORTS:
            errors.append(f"Unbekannte Sportart „{long_day.get('sport')}“ bei den langen Einheiten.")
    rest = availability.get("rest_days") or {}
    if rest.get("mode") not in ("fixed", "dynamic"):
        errors.append("Ruhetage müssen „fixed“ oder „dynamic“ sein.")
    elif rest.get("mode") == "fixed":
        if not rest.get("days"):
            errors.append("Bei festen Ruhetagen fehlen die Tage.")
        for day in rest.get("days") or []:
            if day not in WEEKDAYS:
                errors.append(f"Unbekannter Ruhetag „{day}“.")

    strength = p.get("strength") or {}
    if strength.get("enabled") and not strength.get("confirmed_at"):
        errors.append("Krafttraining ist eingeschaltet, aber nicht bestätigt (confirmed_at fehlt).")
    return errors


def season_phase(season: dict, day: date) -> dict | None:
    """The phase that contains `day`, plus day_in_phase, days_left and next_name."""
    phases = season.get("phases") or []
    for i, phase in enumerate(phases):
        start, end = _iso(phase.get("start")), _iso(phase.get("end"))
        if start and end and start <= day <= end:
            following = phases[i + 1]["name"] if i + 1 < len(phases) else None
            return {**phase, "day_in_phase": (day - start).days + 1, "days_left": (end - day).days,
                    "next_name": following}
    return None


def check_season(season: dict, profile: dict) -> list[str]:
    """Check the season plan against the fixed rules; German error messages."""
    errors = []
    created = _iso(season.get("created"))
    phases = sorted(season.get("phases") or [], key=lambda ph: ph.get("start") or "")
    if not phases:
        return ["Der Saisonplan hat keine Phasen."]
    strength_on = bool((profile.get("strength") or {}).get("enabled"))
    previous_end = None
    for ph in phases:
        name = ph.get("name") or "?"
        start, end = _iso(ph.get("start")), _iso(ph.get("end"))
        if not ph.get("name"):
            errors.append(f"Die Phase ab {ph.get('start') or '?'} hat keinen Namen (Dashboard und Journal brauchen ihn).")
        if not start or not end or end < start:
            errors.append(f"Phase „{name}“ hat kein gültiges Start- und Enddatum.")
            continue
        if ph.get("focus") not in PHASE_FOCI:
            errors.append(f"Phase „{name}“ hat einen unbekannten Schwerpunkt „{ph.get('focus')}“.")
        if ph.get("strength_phase", "off") not in STRENGTH_PHASES:
            errors.append(f"Phase „{name}“ hat eine unbekannte Kraftphase „{ph.get('strength_phase')}“.")
        elif not strength_on and ph.get("strength_phase", "off") != "off":
            errors.append(f"Phase „{name}“ plant Krafttraining, das im Profil nicht eingeschaltet ist.")
        if created and end < created:
            errors.append(f"Phase „{name}“ liegt vollständig vor dem Erstellungsdatum {created.isoformat()}.")
        if previous_end is not None:
            if start <= previous_end:
                errors.append(f"Phase „{name}“ und die Phase davor überschneiden sich.")
            elif start > previous_end + timedelta(days=1):
                errors.append(f"Lücke im Saisonplan vor Phase „{name}“.")
        previous_end = end

    goal = profile.get("goal") or {}
    event = goal.get("event") or {}
    race_day = _iso(event.get("date"))
    if goal.get("type") == "event" and race_day:
        tapers = [ph for ph in phases if ph.get("focus") == "taper" and _iso(ph.get("end")) == race_day - timedelta(days=1)]
        if not tapers:
            errors.append("Vor dem Wettkampf fehlt eine Tapering-Phase, die am Vortag endet.")
        else:
            taper = tapers[0]
            length = (_iso(taper["end"]) - _iso(taper["start"])).days + 1
            low, high = TAPER_DAYS.get(event.get("priority", "A"), TAPER_DAYS["A"])
            if not low <= length <= high:
                errors.append(f"Das Tapering dauert {length} Tage, erwartet sind {low}–{high} Tage.")
        if not any(ph.get("focus") == "race" and _iso(ph.get("start")) and _iso(ph.get("end"))
                   and _iso(ph["start"]) <= race_day <= _iso(ph["end"]) for ph in phases):
            errors.append("Keine Wettkampf-Phase enthält das Wettkampfdatum.")
    return errors


def check_schedule(schedule: dict, profile: dict, sessions: dict) -> list[str]:
    """Check the rolling schedule against the fixed rules; German error messages."""
    errors = []
    availability = profile.get("availability") or {}
    hours = availability.get("hours") or {}
    long_days = availability.get("long_days") or []
    rest = availability.get("rest_days") or {}
    fixed_rest = set(rest.get("days") or []) if rest.get("mode") == "fixed" else set()
    sports = set(profile.get("sports") or [])
    strength = profile.get("strength") or {}
    strength_ok = bool(strength.get("enabled") and strength.get("confirmed_at"))

    days = schedule.get("days") or []
    seen = set()
    by_date = {}
    for entry in days:
        when = _iso(entry.get("date"))
        label = entry.get("date") or "?"
        if not when:
            errors.append(f"Ungültiges Datum „{label}“ in der Vorschau.")
            continue
        if label in seen:
            errors.append(f"{label}: mehr als eine Einheit an einem Tag.")
            continue
        seen.add(label)
        by_date[when] = entry
        sport, kind = entry.get("sport"), entry.get("kind")
        weekday = WEEKDAYS[when.weekday()]
        if sport not in DAY_SPORTS:
            errors.append(f"{label}: unbekannte Sportart „{sport}“.")
            continue
        if kind not in DAY_KINDS:
            errors.append(f"{label}: unbekannte Art „{kind}“.")
        if entry.get("status", "planned") not in DAY_STATUS:
            errors.append(f"{label}: unbekannter Status „{entry.get('status')}“.")
        if sport == "rest":
            if kind not in ("rest", "rest_expected"):
                errors.append(f"{label}: ein Ruhetag braucht die Art „rest“ oder „rest_expected“.")
            continue
        if kind in ("rest", "rest_expected"):
            errors.append(f"{label}: Art „{kind}“ passt nicht zu einer Trainingseinheit.")
        if weekday in fixed_rest:
            errors.append(f"{label}: {weekday} ist ein fester Ruhetag.")
        if sport == "brick":
            if not profile.get("multisport"):
                errors.append(f"{label}: Koppeltraining ist nur bei Triathlon oder Duathlon vorgesehen.")
        elif sport == "strength":
            if "strength" not in sports or not strength_ok:
                errors.append(f"{label}: Krafttraining ist im Profil nicht eingeschaltet und bestätigt.")
        elif sport not in sports:
            errors.append(f"{label}: Sportart „{sport}“ ist im Profil nicht gewählt.")
        session = entry.get("session")
        if session not in sessions:
            errors.append(f"{label}: Einheit „{session}“ gibt es in der Bibliothek nicht.")
        elif (sessions[session] or {}).get("sport", "cycling") != sport:
            errors.append(f"{label}: Einheit „{session}“ gehört nicht zur Sportart „{sport}“.")
        budget = _num(hours.get(weekday))
        minutes = _num(entry.get("duration_min")) or 0
        if budget is not None and minutes > budget * 60:
            errors.append(f"{label}: {minutes:.0f} min sind mehr als die verfügbaren {budget * 60:.0f} min.")
        if kind == "long" and long_days and not any(ld.get("day") == weekday and ld.get("sport") == sport
                                                    for ld in long_days):
            errors.append(f"{label}: lange Einheiten nur an den festgelegten Tagen ({', '.join(ld['day'] for ld in long_days)}).")

    for when, entry in by_date.items():
        following = by_date.get(when + timedelta(days=1))
        if not following:
            continue
        if entry.get("kind") == "key" and following.get("kind") == "key" and entry.get("sport") == following.get("sport"):
            errors.append(f"{when.isoformat()}: zwei Schlüsseleinheiten in Folge in derselben Sportart.")
        if entry.get("sport") == "strength" and following.get("kind") in ("key", "long"):
            errors.append(f"{when.isoformat()}: Krafttraining direkt vor einer Schlüssel- oder langen Einheit.")

    if len(by_date) >= 7:
        rests = sum(1 for e in by_date.values() if e.get("kind") in ("rest", "rest_expected"))
        needed = int(rest.get("min_per_cycle", 1) or 0)
        if rests < needed:
            errors.append(f"Die Vorschau hat {rests} Ruhetage, nötig sind mindestens {needed}.")
    return errors


def set_day(schedule: dict, day: str, **changes) -> dict:
    """A copy of the schedule with one day changed. Unknown fields or dates raise KeyError."""
    unknown = set(changes) - set(DAY_FIELDS)
    if unknown:
        raise KeyError(f"Unbekannte Felder: {', '.join(sorted(unknown))}")
    result = json.loads(json.dumps(schedule))
    for entry in result.get("days") or []:
        if entry.get("date") == day:
            entry.update(changes)
            if entry.get("sport") == "rest":
                entry.update(session=None, duration_min=0)
            return result
    raise KeyError(f"Der Tag {day} steht nicht in der Vorschau.")


def countdown(profile: dict, day: date) -> dict | None:
    """Days until the goal event, with its distance and elevation."""
    goal = profile.get("goal") or {}
    event = goal.get("event") or {}
    when = _iso(event.get("date"))
    if goal.get("type") != "event" or not when or when < day:
        return None
    return {"name": event.get("name"), "date": when.isoformat(), "days": (when - day).days,
            "distance_km": event.get("distance_km"), "elevation_m": event.get("elevation_m")}


HARD_BENEFITS = {"vo2max", "anaerobic capacity", "lactate threshold", "speed", "sprint"}


def is_hard(activity: dict) -> bool:
    """A key (hard) session by Garmin's training effect."""
    return ((activity.get("primary_benefit") or "") in HARD_BENEFITS or (activity.get("anaerobic_te") or 0) >= 2.0
            or (activity.get("aerobic_te") or 0) >= 4.0)


def _dig(node, *keys):
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _num(value) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _fmt(value) -> str:
    if value is None:
        return "–"
    return f"{value:.1f}".replace(".", ",").replace(",0", "") if isinstance(value, float) else str(value)


def recovery_assessment(data: dict, day: date, rules: dict) -> dict:
    """Weigh all recovery signals of the last nights (concept 6.2.1). Missing values never count as a signal.

    decision: rest_now (resting HR clearly up AND HRV below normal), rest (enough signals), easy (1 or 2), train.
    """
    days = data.get("days") or {}
    activities = data.get("activities") or []

    def record(offset: int) -> dict:
        return days.get((day - timedelta(days=offset)).isoformat()) or {}

    def trained(offset: int) -> list[dict]:
        when = (day - timedelta(days=offset)).isoformat()
        return [a for a in activities if a.get("date") == when]

    today, yesterday = record(0), record(1)
    yesterday_easy = not any(is_hard(a) for a in trained(1))
    signals = []

    def add(key: str, label: str, hit: bool, detail: str) -> None:
        signals.append({"key": key, "label": label, "hit": bool(hit), "detail": detail})

    low = rules["readiness_low"]
    r0 = _num(_dig(today, "training_readiness", "morning", "score"))
    r1 = _num(_dig(yesterday, "training_readiness", "morning", "score"))
    add("readiness", "Trainingsbereitschaft",
        r0 is not None and r0 < low and ((r1 is not None and r1 < low) or yesterday_easy),
        f"heute {_fmt(r0)}, gestern {_fmt(r1)} (Grenze {low})")

    rt = _num(_dig(today, "training_readiness", "morning", "recovery_time_h"))
    add("recovery_time", "Erholungszeit",
        yesterday_easy and rt is not None and rt > rules["recovery_time_h"],
        f"{_fmt(rt)} h, gestern {'locker' if yesterday_easy else 'hart'} (Grenze {rules['recovery_time_h']} h)")

    q0 = _num(_dig(today, "training_status", "load_ratio"))
    q1 = _num(_dig(yesterday, "training_status", "load_ratio"))
    add("load_ratio", "Belastungsverhältnis",
        q0 is not None and q1 is not None and q0 > rules["load_ratio"] and q0 > q1,
        f"heute {_fmt(q0)}, gestern {_fmt(q1)} (Grenze {_fmt(float(rules['load_ratio']))})")

    hrv = [_num(_dig(record(n), "hrv", "last_night_avg")) for n in (0, 1, 2)]
    hrv_low = _num(_dig(today, "hrv", "baseline_low"))
    present = [v for v in hrv if v is not None]
    below = len(present) >= 2 and hrv_low is not None and sum(present) / len(present) < hrv_low
    falling = None not in hrv and hrv[2] > hrv[1] > hrv[0] and (hrv[2] - hrv[0]) / hrv[2] >= 0.10
    add("hrv", "HRV der letzten Nächte", below or falling,
        f"{' / '.join(_fmt(v) for v in reversed(hrv))} ms, Normalbereich ab {_fmt(hrv_low)}")

    sleep = [_num(_dig(record(n), "sleep", "score")) for n in (0, 1, 2)]
    scores = [v for v in sleep if v is not None]
    add("sleep", "Schlaf-Scores",
        len(scores) >= 2 and sum(scores) / len(scores) < rules["sleep_score"],
        f"{' / '.join(_fmt(v) for v in reversed(sleep))} (Grenze Schnitt {rules['sleep_score']})")

    rhr0, avg0 = _num(_dig(today, "resting_hr", "today")), _num(_dig(today, "resting_hr", "avg_7d"))
    rhr1 = _num(_dig(yesterday, "resting_hr", "today"))
    avg1 = _num(_dig(yesterday, "resting_hr", "avg_7d")) or avg0
    delta = rules["rhr_delta"]
    add("resting_hr", "Ruhepuls-Entwicklung",
        None not in (rhr0, avg0, rhr1, avg1) and rhr0 >= avg0 + delta and rhr1 >= avg1 + delta,
        f"heute {_fmt(rhr0)}, gestern {_fmt(rhr1)}, Schnitt {_fmt(avg0)} (Grenze +{delta})")

    in_row = 0
    while in_row < 60 and trained(in_row + 1):
        in_row += 1
    add("days_in_row", "Trainingstage in Folge", in_row >= rules["days_in_row"],
        f"{in_row} Tage (Grenze {rules['days_in_row']})")

    hits = sum(s["hit"] for s in signals)
    alarm = (None not in (rhr0, avg0) and rhr0 >= avg0 + rules["rhr_alarm"]
             and hrv[0] is not None and hrv_low is not None and hrv[0] < hrv_low)
    if alarm:
        decision = "rest_now"
    elif hits >= rules["signals_for_rest"]:
        decision = "rest"
    elif hits:
        decision = "easy"
    else:
        decision = "train"
    return {"date": day.isoformat(), "decision": decision, "alarm": bool(alarm), "hits": hits, "signals": signals}


# --------------------------------------------------------------------------- command line

SPORT_DE = {"cycling": "Radfahren", "running": "Laufen", "swimming": "Schwimmen", "strength": "Krafttraining",
            "brick": "Koppeltraining", "rest": "Ruhetag"}
WEEKDAY_DE = {"mon": "Mo", "tue": "Di", "wed": "Mi", "thu": "Do", "fri": "Fr", "sat": "Sa", "sun": "So"}
FOCUS_DE = {"vo2max": "VO2max", "anaerobic": "anaerob", "base": "Grundlage", "gran_fondo": "Gran Fondo",
            "time_trial": "Zeitfahren", "climbing": "Bergfahren", "trail": "Trail"}


def _de(value, unit: str = "") -> str:
    if value is None:
        return "–"
    text = f"{value:g}".replace(".", ",")
    return f"{text} {unit}".strip()


def _threshold(value, unit: str = "") -> str:
    if isinstance(value, dict) and value.get("source") == "garmin":
        return "von Garmin"
    if isinstance(value, (int, float)):
        return _de(value, unit)
    return value or "–"


def _describe_goal(goal: dict) -> str:
    if goal.get("type") == "event":
        e = goal.get("event") or {}
        parts = [f"Wettkampf „{e.get('name', '–')}“ am {e.get('date', '–')}"]
        distance = e.get("distance_km")
        if isinstance(distance, dict):
            parts.append(", ".join(f"{SPORT_DE.get(k, k)} {v} km" for k, v in distance.items()))
        elif distance is not None:
            parts.append(f"{_de(distance)} km")
        if e.get("elevation_m") is not None:
            parts.append(f"{_de(e['elevation_m'])} Hm")
        climb = e.get("longest_climb")
        if climb:
            parts.append(f"längster Anstieg {_de(climb.get('km'), 'km')} / {_de(climb.get('elevation_m'), 'Hm')}")
        parts.append(f"Priorität {e.get('priority', 'A')}")
        if e.get("target_time"):
            parts.append(f"Zielzeit {e['target_time']}")
        return "Ziel: " + " · ".join(parts)
    if goal.get("type") == "discipline":
        d = goal.get("discipline") or {}
        extra = [x for x in (f"{_de(d['distance_km'])} km" if d.get("distance_km") else "",
                             f"{_de(d['elevation_m'])} Hm" if d.get("elevation_m") else "") if x]
        text = (f"Ziel: Disziplin {SPORT_DE.get(d.get('sport'), d.get('sport'))} – "
                f"{FOCUS_DE.get(d.get('focus'), d.get('focus'))}")
        return text + (f" ({' · '.join(extra)})" if extra else "")
    focus = ", ".join(FOCUS_DE.get(f, f) for f in (goal.get("fitness") or {}).get("focus") or [])
    return f"Ziel: allgemeine Fitness ({focus})"


def describe_profile(p: dict) -> str:
    """The settings in plain German, for the settings dialog."""
    lines = [f"Trainerprofil ({'eingerichtet' if p.get('setup_done') else 'noch nicht eingerichtet'}, "
             f"Stand {p.get('updated', '–')})"]
    multi = p.get("multisport")
    lines.append("Sportarten: " + ", ".join(SPORT_DE.get(s, s) for s in p.get("sports") or [])
                 + (f" (Mehrkampf: {multi.capitalize()})" if multi else ""))
    lines.append(_describe_goal(p.get("goal") or {}))
    for e in p.get("secondary_events") or []:
        lines.append(f"Weiterer Wettkampf: „{e.get('name', '–')}“ am {e.get('date', '–')} "
                     f"(Priorität {e.get('priority', 'B')})")
    availability = p.get("availability") or {}
    hours = availability.get("hours") or {}
    lines.append("Zeitbudget: " + " · ".join(f"{WEEKDAY_DE[d]} {_de(hours.get(d), 'h')}" for d in WEEKDAYS))
    long_days = availability.get("long_days") or []
    lines.append("Lange Einheiten: " + (" · ".join(
        f"{WEEKDAY_DE.get(ld.get('day'), ld.get('day'))} {SPORT_DE.get(ld.get('sport'), ld.get('sport'))} "
        f"bis {_de(ld.get('max_h'), 'h')}" for ld in long_days) or "keine festen Tage"))
    rest = availability.get("rest_days") or {}
    if rest.get("mode") == "fixed":
        lines.append("Ruhetage: fest an " + ", ".join(WEEKDAY_DE.get(d, d) for d in rest.get("days") or []))
    else:
        lines.append(f"Ruhetage: dynamisch (mindestens {rest.get('min_per_cycle', 1)} pro Trainingsabschnitt)")
    strength = p.get("strength") or {}
    if strength.get("enabled"):
        lines.append(f"Krafttraining: an ({strength.get('location') or '–'}, {strength.get('experience') or '–'}, "
                     f"{strength.get('per_cycle', 0)}× pro Abschnitt, bestätigt am {strength.get('confirmed_at')})")
    else:
        lines.append("Krafttraining: aus")
    t = p.get("thresholds") or {}
    lines.append(f"Leistungswerte: FTP {_threshold(t.get('cycling_ftp_w'), 'W')} · Laufschwelle "
                 f"{_threshold(t.get('running_threshold_pace'))} · Schwimm-CSS "
                 f"{_threshold(t.get('swim_css_per_100m'))} · Max-Puls {_threshold(t.get('max_hr'), 'bpm')}")
    c = p.get("constraints") or {}
    lines.append(f"Einschränkungen und Vorlieben: {c.get('injuries') or 'keine'} · "
                 f"Zwift {'ja' if c.get('indoor_zwift') else 'nein'} · Bahnlänge {c.get('pool_length_m', '–')} m")
    r = p.get("rest_rules") or {}
    lines.append(f"Ruhetag-Grenzwerte: Bereitschaft < {r.get('readiness_low')} · Erholungszeit > "
                 f"{r.get('recovery_time_h')} h · Belastungsverhältnis > {_de(r.get('load_ratio'))} · Schlaf-Score < "
                 f"{r.get('sleep_score')} · Ruhepuls +{r.get('rhr_delta')} · {r.get('days_in_row')} Tage in Folge · "
                 f"Ruhetag ab {r.get('signals_for_rest')} Signalen")
    return "\n".join(lines)


def _save(root: Path, name: str, data: dict) -> None:
    path = root / "training" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _report(errors: list[str]) -> int:
    if errors:
        print("Nicht gespeichert, die Prüfung hat Fehler gefunden:")
        for error in errors:
            print(f"- {error}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Trainer: Einstellungen, Pläne und Regelprüfung.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository-Ordner (für Tests)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="Einstellungen im Klartext")
    sub.add_parser("check", help="Profil, Saisonplan und Vorschau prüfen")
    for name in ("write-profile", "write-season", "write-schedule"):
        sub.add_parser(name, help="prüfen und speichern").add_argument("file", type=Path)
    day = sub.add_parser("set-day", help="einen Tag der Vorschau ändern")
    day.add_argument("date")
    day.add_argument("--status", choices=DAY_STATUS)
    day.add_argument("--kind", choices=DAY_KINDS)
    day.add_argument("--sport", choices=DAY_SPORTS)
    day.add_argument("--session")
    day.add_argument("--duration", type=int)
    day.add_argument("--reason")
    args = parser.parse_args(argv)
    root = args.root

    if args.command == "show":
        print(describe_profile(load_profile(root)))
        return 0
    if args.command == "check":
        profile = load_profile(root)
        errors = ([f"Profil: {e}" for e in validate_profile(profile)]
                  + [f"Saisonplan: {e}" for e in check_season(load_season(root), profile)]
                  + [f"Vorschau: {e}" for e in check_schedule(load_schedule(root), profile, load_sessions(root))])
        if errors:
            print("Die Prüfung hat Fehler gefunden:")
            for error in errors:
                print(f"- {error}")
            return 1
        print("Alles in Ordnung: Profil, Saisonplan und Vorschau erfüllen die Regeln.")
        return 0
    if args.command == "set-day":
        changes = {k: v for k, v in (("status", args.status), ("kind", args.kind), ("sport", args.sport),
                                     ("session", args.session), ("duration_min", args.duration),
                                     ("reason", args.reason)) if v is not None}
        try:
            schedule = set_day(load_schedule(root), args.date, **changes)
        except KeyError as err:
            print(f"Nicht gespeichert: {err.args[0]}")
            return 1
        if _report(check_schedule(schedule, load_profile(root), load_sessions(root))):
            return 1
        _save(root, "schedule.json", schedule)
        print(f"{args.date} in der Vorschau geändert.")
        return 0

    try:
        data = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"Nicht gespeichert: Datei nicht lesbar ({err}).")
        return 1
    if args.command == "write-profile":
        if _report(validate_profile(data)):
            return 1
        _save(root, "profile.json", data)
    elif args.command == "write-season":
        if _report(check_season(data, load_profile(root))):
            return 1
        _save(root, "season.json", data)
    else:
        if _report(check_schedule(data, load_profile(root), load_sessions(root))):
            return 1
        _save(root, "schedule.json", data)
    print("Geprüft und gespeichert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
