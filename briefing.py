"""Render the Morning Health Briefing and the Daily Wrap-Up as HUD-style pages.

  python briefing.py wait-sync --request                   ask GitHub for a fresh Garmin sync and wait for it (max. 8 min)
  python briefing.py wait-sync                             only wait (max. 8 min) until the Garmin data is fresh
  python briefing.py context morning|wrapup                facts for Claude's analysis (JSON)
  python briefing.py morning --analysis a.json --out page.html
  python briefing.py wrapup  --analysis a.json --out page.html
  --date YYYY-MM-DD renders another day (for tests).

Claude writes only the judgement (status, texts, workout) into the analysis JSON; every number
and chart comes from data/data.json. Standard library only, so the cloud routines can run it as is.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import trainer
import settings
import workouts

ROOT = Path(__file__).resolve().parent
TZ = settings.timezone()
WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WD_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
FOCUS_DE = {"vo2max": "VO2max", "anaerobic": "Anaerob", "base": "Grundlage", "recovery": "Entlastung",
            "build": "Aufbau", "specific": "Spezifisch", "taper": "Tapering", "race": "Wettkampf",
            "threshold": "Schwelle", "climbing": "Berg", "tempo": "Tempo"}
FOCUS_COLOR = {"vo2max": "var(--vo2)", "anaerobic": "var(--hot)", "base": "var(--arc-deep)", "recovery": "var(--ink-3)",
               "build": "var(--arc)", "specific": "var(--gold)", "taper": "var(--violet)", "race": "var(--ok)",
               "threshold": "var(--gold)", "climbing": "var(--vo2)", "tempo": "var(--gold)"}
SPORT_DE = {"cycling": "Rad", "running": "Lauf", "swimming": "Schwimmen", "strength": "Kraft", "brick": "Koppel",
            "rest": "Ruhe"}
KIND_DE = {"rest": "Ruhetag", "rest_expected": "Ruhetag voraussichtlich", "easy": "Locker", "normal": "Normal",
           "key": "Schlüsseleinheit", "long": "Lange Einheit", "strength": "Krafteinheit"}
KIND_COLOR = {"rest": "var(--ink-3)", "rest_expected": "var(--ink-3)", "easy": "var(--arc-deep)", "normal": "var(--arc)",
              "key": "var(--vo2)", "long": "var(--gold)", "strength": "var(--violet)"}
DECISION = {"rest_now": ("bad", "Sofort Ruhetag"), "rest": ("bad", "Ruhetag"), "easy": ("warn", "Lockerer Tag"),
            "train": ("good", "Training nach Plan")}
CALENDAR_SPORTS = ("cycling", "strength")  # what calendar_upload.py can put into the Garmin calendar
SETUP_HINT = "Training noch nicht eingerichtet – schreib im Projekt ‚Training einrichten‘"
SYNC_MARKER = "[data-sync]"  # commit message start that makes .github/workflows/data-sync.yml run
BENEFIT_DE = {"aerobic base": "Grundlage", "tempo": "Tempo", "lactate threshold": "Schwelle", "vo2max": "VO2max",
              "anaerobic capacity": "Anaerob", "speed": "Sprint", "sprint": "Sprint", "recovery": "Erholung"}
STATE = {"good": "var(--ok)", "warn": "var(--warn)", "bad": "var(--bad)", "neutral": "var(--arc)"}
STATUS = {"green": ("good", "Grün"), "yellow": ("warn", "Gelb"), "red": ("bad", "Rot")}
STAGE_COLOR = {"deep": "var(--arc-deep)", "light": "var(--arc)", "rem": "var(--violet)", "awake": "var(--gold)"}
STAGE_DE = {"awake": "Wach", "rem": "REM", "light": "Leicht", "deep": "Tief"}
TYPE_DE = {"road_biking": "Rennrad", "mountain_biking": "Mountainbike", "cyclocross": "Cyclocross",
           "gravel_cycling": "Gravel", "virtual_ride": "Zwift", "indoor_cycling": "Indoor-Rad", "cycling": "Rad",
           "running": "Laufen", "walking": "Gehen", "hiking": "Wandern", "strength_training": "Kraft"}

esc = html.escape


# ------------------------------------------------------------------- formatting


def de(v, digits: int = 0) -> str:
    if v is None:
        return "–"
    return f"{v:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def greeting(words: str, name: str) -> str:
    return f"{words}, {name}" if name else words


def dur(minutes) -> str:
    if minutes is None:
        return "–"
    m = round(minutes)
    return f"{m // 60}:{m % 60:02d} h" if m >= 60 else f"{m} min"


def mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds >= 60 else f"{seconds} s"


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def hm(text: str | None) -> tuple[int, int] | None:
    try:
        h, m = str(text)[:5].split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return None


def zone_color(pct: float) -> str:
    if pct < 56:
        return "var(--ink-3)"
    if pct < 76:
        return "var(--arc-deep)"
    if pct < 88:
        return "var(--arc)"
    if pct < 106:
        return "var(--gold)"
    if pct < 121:
        return "var(--vo2)"
    return "var(--hot)"


# ------------------------------------------------------------------------ facts


class Ctx:
    def __init__(self, day: date | None, root: Path = ROOT) -> None:
        self.root = root
        self.settings = settings.load(root)
        self.data = json.loads((root / "data" / "data.json").read_text(encoding="utf-8"))
        self.profile = trainer.load_profile(root)
        self.season = trainer.load_season(root)
        self.schedule = trainer.load_schedule(root)
        self.sessions = trainer.load_sessions(root)
        self.now = datetime.now(TZ)
        self.day = day or self.now.date()
        self.days = self.data.get("days", {})
        self.acts = self.data.get("activities", [])
        athlete = self.data.get("athlete", {})
        self.ftp = athlete.get("cycling_ftp_w") or 250
        zones = athlete.get("heart_rate_zones") or []
        self.hr_zones = next((z for z in zones if z.get("sport") == "CYCLING"), zones[0] if zones else None)
        self.last_sync = self.data.get("last_sync")

    def rec(self, d: date) -> dict:
        return self.days.get(d.isoformat(), {})

    @staticmethod
    def counted(acts: list[dict]) -> list[dict]:
        """Drop the second copy of a ride recorded on two devices."""
        seen, out = set(), []
        for a in sorted(acts, key=lambda a: a.get("start") or ""):
            if a.get("overlaps_with") in seen:
                continue
            seen.add(a.get("id"))
            out.append(a)
        return out

    def acts_between(self, d0: date, d1: date) -> list[dict]:
        return self.counted([a for a in self.acts if d0.isoformat() <= (a.get("date") or "") <= d1.isoformat()])

    def acts_on(self, d: date) -> list[dict]:
        return self.acts_between(d, d)

    def load_on(self, d: date) -> float:
        return sum(a.get("training_load") or 0 for a in self.acts_on(d))

    hard = staticmethod(trainer.is_hard)

    def sync_age_h(self) -> float | None:
        try:
            return round((self.now - datetime.fromisoformat(self.last_sync)).total_seconds() / 3600, 1)
        except (TypeError, ValueError):
            return None

    def phase(self, d: date) -> dict | None:
        return trainer.season_phase(self.season, d)

    def plan_from(self, d: date) -> list[dict]:
        """The rolling schedule from day d on."""
        return sorted((x for x in self.schedule.get("days") or [] if (x.get("date") or "") >= d.isoformat()),
                      key=lambda x: x["date"])

    def plan_on(self, d: date) -> dict | None:
        return next((x for x in self.plan_from(d) if x["date"] == d.isoformat()), None)

    def recovery(self, d: date) -> dict:
        rules = {**trainer.default_profile()["rest_rules"], **(self.profile.get("rest_rules") or {})}
        return trainer.recovery_assessment(self.data, d, rules)

    def trend(self, d: date, path: tuple, n: int = 14) -> list:
        out = []
        for i in range(n - 1, -1, -1):
            v = self.rec(d - timedelta(days=i))
            for key in path:
                v = v.get(key) if isinstance(v, dict) else None
            out.append(v)
        return out

    def intensity_split(self, d0: date, d1: date) -> dict | None:
        zones = [0.0] * 5
        for a in self.acts_between(d0, d1):
            for i, m in enumerate((a.get("hr_zones_min") or [])[:5]):
                zones[i] += m or 0
        total = sum(zones)
        if not total:
            return None
        return {"low": round(100 * (zones[0] + zones[1]) / total), "mid": round(100 * zones[2] / total),
                "high": round(100 * (zones[3] + zones[4]) / total), "minutes": round(total)}

    def last_hard(self, before: datetime) -> dict | None:
        for a in sorted(self.acts, key=lambda a: a.get("start") or "", reverse=True):
            try:
                start = datetime.fromisoformat(a["start"]).replace(tzinfo=TZ)
            except (KeyError, ValueError):
                continue
            if start < before and self.hard(a):
                return {"date": a.get("date"), "name": a.get("name"), "benefit": a.get("primary_benefit"),
                        "load": a.get("training_load"), "hours_ago": round((before - start).total_seconds() / 3600)}
        return None

    def usual_wake(self, d: date) -> str | None:
        minutes = []
        for i in range(7):
            end = (self.rec(d - timedelta(days=i)).get("sleep") or {}).get("end")
            t = hm((end or "")[11:16])
            if t:
                minutes.append(t[0] * 60 + t[1])
        if not minutes:
            return None
        m = round(statistics.median(minutes))
        return f"{m // 60:02d}:{m % 60:02d}"

    def draft_status(self, d: date) -> tuple[str, list[str]]:
        r = self.rec(d)
        bad, warn = [], []
        hrv, sleep = r.get("hrv") or {}, r.get("sleep") or {}
        v, lo = hrv.get("last_night_avg"), hrv.get("baseline_low")
        if v and lo and v < lo:
            bad.append(f"HRV {v} ms unter dem Bereich ab {lo} ms")
        if (hrv.get("status") or "") in ("low", "poor"):
            bad.append(f"HRV-Status {hrv['status']}")
        elif hrv.get("status") == "unbalanced":
            warn.append("HRV-Status unausgeglichen")
        ready = ((r.get("training_readiness") or {}).get("morning") or {})
        score = ready.get("score")
        if score is not None:
            (bad if score < 50 else warn if score < 70 else []).append(f"Bereitschaft {score}")
        rhr = r.get("resting_hr") or {}
        if rhr.get("today") and rhr.get("avg_7d"):
            delta = rhr["today"] - rhr["avg_7d"]
            if delta >= 5:
                bad.append(f"Ruhepuls +{delta}")
            elif delta >= 3:
                warn.append(f"Ruhepuls +{delta}")
        if sleep:
            if (sleep.get("score") or 100) < 60 or (sleep.get("total_min") or 999) < 360:
                bad.append("zu wenig oder schlechter Schlaf")
            elif (sleep.get("score") or 100) < 75:
                warn.append(f"Schlaf-Score {sleep.get('score')}")
        rec_h = ready.get("recovery_time_h")
        if rec_h is not None and rec_h > 24:
            bad.append(f"Erholungszeit {rec_h:.0f} h")
        elif rec_h is not None and rec_h >= 12:
            warn.append(f"Erholungszeit {rec_h:.0f} h")
        ratio = (r.get("training_status") or {}).get("load_ratio")
        if ratio and ratio > 1.5:
            bad.append(f"Belastungsverhältnis {ratio}")
        elif ratio and ratio > 1.3:
            warn.append(f"Belastungsverhältnis {ratio}")
        return ("red" if bad else "yellow" if warn else "green"), bad + warn


def wait_for_sync(max_age_min: int, timeout_min: int) -> int:
    """Wait until data/data.json is fresh, pulling main once a minute. 0 = fresh, 1 = still stale."""
    deadline = time.monotonic() + timeout_min * 60
    while True:
        try:
            last = datetime.fromisoformat(json.loads((ROOT / "data" / "data.json").read_text(encoding="utf-8"))["last_sync"])
            age = (datetime.now(TZ) - last).total_seconds() / 60
        except (OSError, ValueError, KeyError, TypeError):
            age = float("inf")
        if age <= max_age_min:
            print(f"Garmin data is fresh ({age:.0f} min old).")
            return 0
        if time.monotonic() >= deadline:
            print(f"Garmin data is still {age:.0f} min old after waiting; continue with it and say so.")
            return 1
        print(f"Garmin data is {age:.0f} min old; waiting for the next sync ...", flush=True)
        time.sleep(60)
        subprocess.run(["git", "pull", "-q", "--ff-only", "origin", "main"], cwd=ROOT, check=False)


def request_sync(run=subprocess.run) -> bool:
    """Ask GitHub for a fresh Garmin sync: push an empty commit marked SYNC_MARKER to this session's own claude/...
    branch. data-sync.yml runs on it and deletes the branch afterwards. The commit is built with commit-tree and
    never added to the local branch, so the routine's own commits later go up as usual."""
    def git(*args):
        return run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    branch = git("branch", "--show-current").stdout.strip()
    if not branch.startswith("claude/"):
        print(f"Not on a claude/ branch ({branch or 'none'}); a sync can only be requested from a cloud routine.")
        return False
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    commit = git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", f"{SYNC_MARKER} Abruf angefordert {stamp}")
    sha = commit.stdout.strip()
    if commit.returncode or not sha:
        return False
    return git("push", "-q", "--force", "origin", f"{sha}:refs/heads/{branch}").returncode == 0


def remote_last_sync() -> datetime | None:
    """last_sync of data/data.json on origin/main, fetched fresh."""
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, check=False)
    shown = subprocess.run(["git", "show", "origin/main:data/data.json"], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8")
    try:
        return datetime.fromisoformat(json.loads(shown.stdout)["last_sync"])
    except (ValueError, KeyError, TypeError):
        return None


def wait_for_requested_sync(requested: datetime, timeout_min: int, last_sync, sleep=time.sleep,
                            clock=time.monotonic) -> int:
    """Wait until the sync asked for at `requested` is on main. 0 = arrived, 1 = not within the timeout."""
    deadline = clock() + timeout_min * 60
    while True:
        last = last_sync()
        if last is not None and last >= requested - timedelta(seconds=60):  # 60 s for clock differences
            print(f"Fresh Garmin data from {last:%H:%M}.")
            return 0
        if clock() + 20 > deadline:
            print("The requested Garmin sync did not arrive in time; continue with the data that is there and say so.")
            return 1
        sleep(20)


def week_hard(ctx: Ctx, d: date, include_today: bool) -> list[dict]:
    """Hard sessions in the calendar week (Mon-Sun) of d."""
    monday = d - timedelta(days=d.weekday())
    end = d if include_today else d - timedelta(days=1)
    if end < monday:
        return []
    return [{"date": a.get("date"), "name": a.get("name"), "benefit": a.get("primary_benefit"),
             "load": a.get("training_load")} for a in ctx.acts_between(monday, end) if ctx.hard(a)]


def compact_profile(p: dict) -> dict:
    """What the routines need from the trainer profile every day."""
    return {"sports": p.get("sports"), "multisport": p.get("multisport"), "goal": p.get("goal"),
            "secondary_events": p.get("secondary_events") or [], "availability": p.get("availability"),
            "strength_enabled": bool((p.get("strength") or {}).get("enabled")), "thresholds": p.get("thresholds")}


def context(ctx: Ctx, kind: str) -> dict:
    d = ctx.day
    r = ctx.rec(d)
    status, reasons = ctx.draft_status(d)
    today_plan = ctx.plan_on(d)
    out = {
        "date": d.isoformat(), "weekday": WD_LONG[d.weekday()], "last_sync": ctx.last_sync,
        "sync_age_h": ctx.sync_age_h(), "sleep_synced": bool(r.get("sleep")),
        "setup_done": bool(ctx.profile.get("setup_done")), "profile": compact_profile(ctx.profile),
        "season_phase": ctx.phase(d), "countdown": trainer.countdown(ctx.profile, d),
        "schedule": ctx.plan_from(d), "schedule_cycle": ctx.schedule.get("cycle"), "today_plan": today_plan,
        "schedule_stale": today_plan is None, "recovery": ctx.recovery(d),
        "hard_sessions_this_week": week_hard(ctx, d, include_today=kind == "wrapup"),
        "last_hard_session": ctx.last_hard(ctx.now if kind == "wrapup" else datetime.combine(d, datetime.min.time(), TZ)),
        "intensity_7d_pct": ctx.intensity_split(d - timedelta(days=6), d),
        "load_by_day_14d": {(d - timedelta(days=i)).isoformat(): ctx.load_on(d - timedelta(days=i)) for i in range(13, -1, -1)},
        "athlete": {"ftp_w": ctx.ftp, "hr_zones_cycling": ctx.hr_zones},
        "today": {k: r.get(k) for k in ("sleep", "hrv", "resting_hr", "body_battery", "stress", "steps", "energy",
                                        "training_readiness", "training_status", "day_in_progress", "updated")},
        "trend_14d": {"hrv": ctx.trend(d, ("hrv", "last_night_avg")), "resting_hr": ctx.trend(d, ("resting_hr", "today")),
                      "sleep_score": ctx.trend(d, ("sleep", "score")),
                      "readiness": ctx.trend(d, ("training_readiness", "morning", "score"))},
    }
    if kind == "morning":
        out["draft_status"] = {"status": status, "reasons": reasons}
        out["session_library"] = {k: {"sport": v.get("sport", "cycling"), "focus": v.get("focus"), "name": v.get("name")}
                                  for k, v in ctx.sessions.items()}
    else:
        out["activities_today"] = ctx.acts_on(d)
        out["usual_wake_time"] = ctx.usual_wake(d)
        out["tomorrow_plan"] = ctx.plan_on(d + timedelta(days=1))
    return out


# ------------------------------------------------------------------------- SVG


def ring_svg(value, vmax: float, center: str, label: str, state: str, size: int = 300, sub: str = "") -> str:
    color = STATE.get(state, state)
    c = size / 2
    r = size * 0.37
    circ = 2 * math.pi * r
    frac = clamp((value or 0) / vmax) if value is not None else 0
    ticks = []
    for i in range(60):
        ang = math.radians(i * 6 - 90)
        r1, r2 = size * 0.44, size * (0.475 if i % 5 == 0 else 0.46)
        on = i / 60 < frac
        ticks.append(f'<line x1="{c + r1 * math.cos(ang):.1f}" y1="{c + r1 * math.sin(ang):.1f}" '
                     f'x2="{c + r2 * math.cos(ang):.1f}" y2="{c + r2 * math.sin(ang):.1f}" '
                     f'stroke="{color if on else "var(--line-hi)"}" stroke-width="{2 if i % 5 == 0 else 1}" '
                     f'opacity="{1 if on else .5}"/>')
    big = size * 0.2
    return (f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{esc(label)} {esc(center)}">'
            f'{"".join(ticks)}'
            f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" stroke="var(--line)" stroke-width="{size * 0.035:.1f}"/>'
            f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{size * 0.035:.1f}" '
            f'stroke-dasharray="{circ * frac:.1f} {circ:.1f}" transform="rotate(-90 {c} {c})" '
            f'style="filter:drop-shadow(0 0 6px {color})"/>'
            f'<circle class="spin" cx="{c}" cy="{c}" r="{size * 0.3:.1f}" fill="none" stroke="var(--arc)" '
            f'stroke-opacity=".35" stroke-dasharray="2 7"/>'
            f'<circle cx="{c}" cy="{c}" r="{size * 0.26:.1f}" fill="rgba(95,217,255,.05)" stroke="var(--line)"/>'
            f'<text x="{c}" y="{c + big * 0.32:.1f}" text-anchor="middle" '
            f'style="font:600 {big:.0f}px var(--f-display);fill:var(--ink)">{esc(center)}</text>'
            f'<text x="{c}" y="{c + big * 0.95:.1f}" text-anchor="middle" '
            f'style="font:{max(11, size * 0.042):.0f}px var(--f-mono);letter-spacing:.15em;fill:var(--ink-2)">{esc(label.upper())}</text>'
            + (f'<text x="{c}" y="{c - big * 0.7:.1f}" text-anchor="middle" '
               f'style="font:{max(11, size * 0.04):.0f}px var(--f-mono);letter-spacing:.12em;fill:{color}">{esc(sub.upper())}</text>' if sub else "")
            + '</svg>')


def spark(values: list, w: int = 200, h: int = 46, color: str = "var(--arc)", band: list | None = None) -> str:
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(pts) < 2:
        return ""
    allv = [v for _, v in pts] + [x for b in (band or []) if b for x in b if x is not None]
    lo, hi = min(allv), max(allv)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    n = len(values) - 1

    def x(i): return 4 + i * (w - 8) / n
    def y(v): return h - 4 - (v - lo) * (h - 8) / (hi - lo)

    out = [f'<svg viewBox="0 0 {w} {h}" aria-hidden="true">']
    if band and any(band):
        top = [(i, b[1]) for i, b in enumerate(band) if b and None not in b]
        bot = [(i, b[0]) for i, b in enumerate(band) if b and None not in b]
        if len(top) > 1:
            poly = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in top + bot[::-1])
            out.append(f'<polygon points="{poly}" fill="var(--ok)" fill-opacity=".12"/>')
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
    out.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" '
               f'stroke-linecap="round" style="filter:drop-shadow(0 0 3px {color})"/>')
    li, lv = pts[-1]
    out.append(f'<circle cx="{x(li):.1f}" cy="{y(lv):.1f}" r="3.2" fill="{color}" stroke="var(--void)" stroke-width="1.5"/></svg>')
    return "".join(out)


def time_chart(series: list[tuple[float, float]], x_max: float, y_lo: float, y_hi: float, color: str,
               xticks: list[tuple[float, str]], w: int = 640, h: int = 120, area: bool = False,
               unit: str = "", windows: list[tuple[float, float, str]] | None = None) -> str:
    if len(series) < 2:
        return '<p class="empty">Keine Daten.</p>'
    left, right, top, bottom = 34, 8, 8, 20
    pw, ph = w - left - right, h - top - bottom

    def x(v): return left + clamp(v / x_max) * pw
    def y(v): return top + ph - clamp((v - y_lo) / ((y_hi - y_lo) or 1)) * ph

    out = [f'<svg viewBox="0 0 {w} {h}" aria-hidden="true">']
    for frac in (0, .5, 1):
        val = y_lo + frac * (y_hi - y_lo)
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y(val):.1f}" y2="{y(val):.1f}" stroke="var(--line)" stroke-width="1"/>'
                   f'<text x="{left - 6}" y="{y(val) + 4:.1f}" text-anchor="end">{de(val)}</text>')
    for x0, x1, name in windows or []:
        out.append(f'<rect x="{x(x0):.1f}" y="{top}" width="{max(2, x(x1) - x(x0)):.1f}" height="{ph}" fill="var(--gold)" fill-opacity=".14" '
                   f'stroke="var(--gold)" stroke-opacity=".5"/><text x="{x(x0) + 4:.1f}" y="{top + 12}" style="fill:var(--gold)">{esc(name)}</text>')
    for xv, text in xticks:
        out.append(f'<text x="{x(xv):.1f}" y="{h - 4}" text-anchor="middle">{esc(text)}</text>')
    pts = sorted(series)
    line = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in pts)
    if area:
        out.append(f'<polygon points="{x(pts[0][0]):.1f},{top + ph} {line} {x(pts[-1][0]):.1f},{top + ph}" fill="{color}" fill-opacity=".14"/>')
    out.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" '
               f'style="filter:drop-shadow(0 0 4px {color})"/>')
    out.append("</svg>")
    return "".join(out)


def hour_ticks(start: datetime, minutes_total: float, every_h: int = 1) -> list[tuple[float, str]]:
    first = (start + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    ticks, t = [], first
    while (t - start).total_seconds() / 60 <= minutes_total:
        if t.hour % every_h == 0:
            ticks.append(((t - start).total_seconds() / 60, f"{t.hour:02d}"))
        t += timedelta(hours=1)
    return ticks


def place(text: str, start: datetime, end: datetime) -> datetime | None:
    """Turn an 'HH:MM' from a curve into a datetime inside the night window."""
    t = hm(text)
    if not t:
        return None
    for base in (start.date(), end.date()):
        dt = datetime(base.year, base.month, base.day, t[0], t[1])
        if start - timedelta(minutes=45) <= dt <= end + timedelta(minutes=45):
            return dt
    return None


def hypnogram(segments: list, start: datetime, end: datetime) -> str:
    total = (end - start).total_seconds() / 60
    if total <= 0 or not segments:
        return '<p class="empty">Keine Schlafphasen.</p>'
    w, h, left = 640, 150, 54
    lanes = {"awake": 10, "rem": 40, "light": 70, "deep": 100}
    pw = w - left - 8

    def x(m): return left + clamp(m / total) * pw

    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Schlafphasen der Nacht">']
    for stage, yy in lanes.items():
        out.append(f'<text x="0" y="{yy + 15}">{STAGE_DE[stage].upper()}</text>'
                   f'<line x1="{left}" x2="{w - 8}" y1="{yy + 11}" y2="{yy + 11}" stroke="var(--line)" stroke-dasharray="2 4"/>')
    path = []
    for seg in segments:
        s, e = place(seg[0], start, end), place(seg[1], start, end)
        if not s or not e:
            continue
        if e < s:
            e += timedelta(days=1)
        m0, m1 = (s - start).total_seconds() / 60, (e - start).total_seconds() / 60
        yy = lanes.get(seg[2], 70)
        out.append(f'<rect x="{x(m0):.1f}" y="{yy}" width="{max(1.5, x(m1) - x(m0)):.1f}" height="22" '
                   f'fill="{STAGE_COLOR.get(seg[2], "var(--arc)")}" fill-opacity=".85"/>')
        path.append(f"{x(m0):.1f},{yy + 11} {x(m1):.1f},{yy + 11}")
    out.append(f'<polyline points="{" ".join(path)}" fill="none" stroke="var(--arc-hi)" stroke-opacity=".35" stroke-width="1"/>')
    for xv, text in hour_ticks(start, total):
        out.append(f'<text x="{x(xv):.1f}" y="{h - 4}" text-anchor="middle">{text}</text>')
    out.append("</svg>")
    return "".join(out)


def bars_svg(items: list[tuple[str, float, str]], w: int = 640, h: int = 170, unit: str = "") -> str:
    if not items:
        return '<p class="empty">Keine Daten.</p>'
    left, bottom, top = 8, 22, 18
    top_v = max([v for _, v, _ in items] + [1]) * 1.1
    slot = (w - left * 2) / len(items)
    bw = min(26, slot * 0.6)
    out = [f'<svg viewBox="0 0 {w} {h}" aria-hidden="true">',
           f'<line x1="{left}" x2="{w - left}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--line-hi)"/>']
    for i, (lab, v, color) in enumerate(items):
        cx = left + slot * (i + .5)
        bh = (h - bottom - top) * (v / top_v)
        if v:
            out.append(f'<rect x="{cx - bw / 2:.1f}" y="{h - bottom - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}" '
                       f'style="filter:drop-shadow(0 0 4px {color})"/>'
                       f'<text x="{cx:.1f}" y="{h - bottom - bh - 5:.1f}" text-anchor="middle" style="fill:var(--ink-2)">{de(v)}</text>')
        out.append(f'<text x="{cx:.1f}" y="{h - 6}" text-anchor="middle">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def ratio_gauge(ratio) -> str:
    w, h, c, r = 240, 140, 120, 96

    def pt(v, rad):
        ang = math.pi * (1 - clamp(v / 2.0))
        return c + rad * math.cos(ang), 120 - rad * math.sin(ang)

    def arc(v0, v1, color, width, opacity=1.0):
        (x0, y0), (x1, y1) = pt(v0, r), pt(v1, r)
        return (f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-opacity="{opacity}"/>')

    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Belastungsverhältnis {de(ratio, 2)}">',
           arc(0, 2, "var(--line)", 12), arc(0.8, 1.3, "var(--ok)", 12, .35), arc(1.3, 1.5, "var(--warn)", 12, .3),
           arc(1.5, 2, "var(--bad)", 12, .25)]
    for v in (0, 0.8, 1.3, 2.0):
        xx, yy = pt(v, r + 18)
        out.append(f'<text x="{xx:.1f}" y="{yy + 4:.1f}" text-anchor="middle">{de(v, 1)}</text>')
    if ratio is not None:
        xx, yy = pt(ratio, r - 2)
        color = "var(--ok)" if 0.8 <= ratio <= 1.3 else "var(--warn)" if ratio <= 1.5 else "var(--bad)"
        out.append(f'<line x1="{c}" y1="120" x2="{xx:.1f}" y2="{yy:.1f}" stroke="{color}" stroke-width="3" '
                   f'style="filter:drop-shadow(0 0 5px {color})"/><circle cx="{c}" cy="120" r="6" fill="{color}"/>'
                   f'<text x="{c}" y="104" text-anchor="middle" style="font:600 22px var(--f-display);fill:var(--ink)">{de(ratio, 2)}</text>')
    out.append("</svg>")
    return "".join(out)


def focus_rows(focus: dict | None) -> str:
    if not focus:
        return '<p class="empty">Keine Lastverteilung von Garmin.</p>'
    rows = []
    for key, name, color in (("low_aerobic", "Aerob niedrig", "var(--arc-deep)"), ("high_aerobic", "Aerob hoch", "var(--gold)"),
                             ("anaerobic", "Anaerob", "var(--hot)")):
        v = focus.get(key) or 0
        lo, hi = (focus.get(f"{key}_target") or [None, None])[:2]
        top = max(v, hi or 0) * 1.15 or 1
        state = "–" if lo is None else "unter Ziel" if v < lo else "über Ziel" if v > hi else "im Ziel"
        scolor = "var(--warn)" if state == "unter Ziel" else "var(--arc)" if state == "über Ziel" else "var(--ok)"
        band = (f'<span style="position:absolute;left:{100 * lo / top:.1f}%;width:{100 * (hi - lo) / top:.1f}%;top:-3px;bottom:-3px;'
                f'border:1px dashed var(--ok);background:rgba(67,240,180,.08)"></span>') if lo is not None else ""
        rows.append(f'<div style="display:grid;gap:6px"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px">'
                    f'<span>{name}</span><span class="mono" style="color:{scolor}">{de(v)} · {state}'
                    f'{f" ({de(lo)}–{de(hi)})" if lo is not None else ""}</span></div>'
                    f'<div style="position:relative;height:10px;background:rgba(95,217,255,.07)">{band}'
                    f'<span style="position:absolute;left:0;top:0;bottom:0;width:{100 * v / top:.1f}%;background:{color};'
                    f'box-shadow:0 0 8px {color}"></span></div></div>')
    fb = focus.get("feedback")
    return ('<div style="display:grid;gap:14px">' + "".join(rows) + "</div>"
            + (f'<p class="ev"><b>Garmin</b>{esc(fb)}</p>' if fb else ""))


def num(v) -> str:
    return de(v, 0 if float(v).is_integer() else 1)


def season_strip(season: dict, d: date) -> str:
    phases = []
    for p in season.get("phases") or []:
        try:
            phases.append((p, date.fromisoformat(p["start"]), date.fromisoformat(p["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not phases:
        return '<p class="empty">Noch kein Saisonplan.</p>'
    first, last = phases[0][1], phases[-1][2]
    total = (last - first).days + 1
    w, h = 460, 62
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Saisonplan {first:%d.%m.%Y} bis {last:%d.%m.%Y}">']
    for p, start, end in phases:
        x0, bw = (start - first).days / total * w, ((end - start).days + 1) / total * w
        focus = p.get("focus")
        out.append(f'<rect x="{x0 + 1:.1f}" y="10" width="{max(1, bw - 2):.1f}" height="16" '
                   f'fill="{FOCUS_COLOR.get(focus, "var(--arc)")}" fill-opacity=".75"><title>{esc(p.get("name") or "")} '
                   f'{start:%d.%m.}–{end:%d.%m.}</title></rect>')
        if bw > 46:
            out.append(f'<text x="{x0 + 4:.1f}" y="42">{esc(FOCUS_DE.get(focus, focus or "").upper())}</text>')
    out.append(f'<text x="0" y="58">{first:%d.%m.}</text><text x="{w}" y="58" text-anchor="end">{last:%d.%m.%y}</text>')
    if d <= last:
        xm = 2 if d < first else ((d - first).days + 0.5) / total * w
        marker = "HEUTE" if d >= first else "START {:%d.%m.}".format(first)
        out.append(f'<path d="M{xm - 6:.1f},2 L{xm + 6:.1f},2 L{xm:.1f},10 Z" fill="var(--arc-hi)"/>'
                   f'<line x1="{xm:.1f}" x2="{xm:.1f}" y1="10" y2="30" stroke="var(--arc-hi)" stroke-width="2"/>'
                   f'<text x="{min(max(xm, 80), w - 80):.1f}" y="58" text-anchor="middle" style="fill:var(--arc-hi)">{marker}</text>')
    out.append("</svg>")
    return "".join(out)


def countdown_html(cd: dict | None) -> str:
    if not cd:
        return ""
    dist = cd.get("distance_km")
    if isinstance(dist, dict):
        dist_text = " · ".join(f"{SPORT_DE.get(k, k)} {num(v)} km" for k, v in dist.items() if v is not None)
    else:
        dist_text = f"{num(dist)} km" if dist is not None else ""
    parts = [x for x in (dist_text, f"{num(cd['elevation_m'])} Hm" if cd.get("elevation_m") is not None else "") if x]
    days = cd["days"]
    when = date.fromisoformat(cd["date"])
    return (f'<div class="kv"><div><span>Countdown</span><b style="font-size:30px;color:var(--gold)">'
            f'{"heute" if days == 0 else f"{days} Tag" + ("e" if days != 1 else "")}</b></div>'
            f'<div><span>Ziel · {when:%d.%m.%Y}</span><b>{esc(cd.get("name") or "Wettkampf")}</b></div>'
            + (f'<div><span>Strecke</span><b>{esc(" · ".join(parts))}</b></div>' if parts else "") + "</div>")


def phase_chip(phase: dict | None) -> str:
    if not phase:
        return ""
    left = phase["days_left"]
    rest = "letzter Tag" if left == 0 else f"noch {left} Tag" + ("e" if left != 1 else "")
    return (f'<span class="chip" style="color:{FOCUS_COLOR.get(phase.get("focus"), "var(--arc)")}">'
            f'{esc(phase.get("name") or "")} · {rest}</span>')


def preview_strip(ctx: Ctx, days: list[dict], today: date | None, empty: str) -> str:
    """One cell per planned day: rest days, key, long and strength sessions stand out by colour and label."""
    cells = []
    for x in days[:10]:
        try:
            dd = date.fromisoformat(x["date"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = x.get("kind")
        name = (ctx.sessions.get(x.get("session") or "") or {}).get("name") or (
            "Erholung" if x.get("sport") == "rest" else x.get("session") or "–")
        meta = [SPORT_DE.get(x.get("sport"), x.get("sport") or "")]
        if x.get("duration_min"):
            meta.append(dur(x["duration_min"]))
        if x.get("status") in ("done", "changed"):
            meta.append({"done": "erledigt", "changed": "geändert"}[x["status"]])
        cls = "pv" + (" now" if dd == today else "") + (" maybe" if kind == "rest_expected" else "")
        cells.append(f'<div class="{cls}" style="--k:{KIND_COLOR.get(kind, "var(--arc)")}" title="{esc(x.get("reason") or "")}">'
                     f'<span class="pv-d">{WD[dd.weekday()]} {dd:%d.%m.}</span><b>{esc(KIND_DE.get(kind, kind or "–"))}</b>'
                     f'<span>{esc(name)}</span><span class="pv-m">{esc(" · ".join(m for m in meta if m))}</span></div>')
    if not cells:
        return f'<p class="empty">{esc(empty)}</p>'
    return '<div class="preview">' + "".join(cells) + "</div>"


def preview_panel(ctx: Ctx, days: list[dict], today: date | None, width: str, empty: str) -> str:
    last = days[min(len(days), 10) - 1]["date"] if days else None
    legend = "".join(f'<span><i style="background:{KIND_COLOR[k]}"></i>{KIND_DE[k]}</span>'
                     for k in ("key", "long", "strength", "easy", "rest"))
    label = (ctx.schedule.get("cycle") or {}).get("label")
    return (f'<section class="pnl {width}"><div class="ph"><span>Vorschau</span>'
            f'<span>{"bis " + date.fromisoformat(last).strftime("%d.%m.") if last else "–"}</span></div>'
            f'{preview_strip(ctx, days, today, empty)}' + (f'<div class="legend">{legend}</div>' if days else "")
            + (f'<p class="sub" style="margin:10px 0 0">{esc(label)}</p>' if label and days else "") + "</section>")


def describe_table(spec: dict) -> str:
    """Strength, running, swimming and brick sessions as a plain table (workouts.describe)."""
    heads = ("Übung", "Wdh.", "Last · Pause") if spec.get("sport") == "strength" else ("Abschnitt", "Umfang", "Vorgabe")
    rows = "".join(f'<tr><td class="rep">{esc(rep)}</td><td>{esc(label)}</td><td>{esc(amount)}</td><td>{esc(target)}</td></tr>'
                   for rep, label, amount, target in workouts.describe(spec))
    return ('<div class="tw"><table><thead><tr><th></th>' + "".join(f"<th>{h}</th>" for h in heads)
            + f"</tr></thead><tbody>{rows}</tbody></table></div>")


def recovery_panel(ctx: Ctx, rec: dict) -> str:
    """The rest-day weighing (concept 6.2.1): every signal with its values and the decision."""
    state, word = DECISION.get(rec.get("decision"), ("neutral", "–"))
    signals = rec.get("signals") or []
    rows = "".join(f'<div class="sig{" hit" if s["hit"] else ""}"><i></i><span>{esc(s["label"])}</span>'
                   f'<span class="mono">{esc(s["detail"])}</span></div>' for s in signals)
    limit = (ctx.profile.get("rest_rules") or {}).get("signals_for_rest") or trainer.default_profile()["rest_rules"]["signals_for_rest"]
    alarm = ('<p class="ev"><b>Achtung</b>Ruhepuls deutlich erhöht und HRV unter dem Normalbereich – das kann auf einen '
             'Infekt oder eine Überlastung hindeuten.</p>' if rec.get("alarm") else "")
    return (f'<section class="pnl c5"><div class="ph"><span>Erholung</span><span>{rec.get("hits", 0)} von {len(signals)} '
            f'Signalen</span></div><span class="chip {state}">{word}</span>{alarm}<div class="sigs">{rows}</div>'
            f'<p class="sub" style="margin:12px 0 0">Ruhetag ab {limit} Signalen, 1–{limit - 1} Signale: lockerer Tag.</p></section>')


def intensity_bar(split: dict | None) -> str:
    if not split:
        return '<p class="empty">Keine Pulszonen in den letzten 7 Tagen.</p>'
    parts = [("Zone 1–2", split["low"], "var(--arc-deep)"), ("Zone 3", split["mid"], "var(--gold)"),
             ("Zone 4–5", split["high"], "var(--hot)")]
    segs = "".join(f'<span style="width:{p}%;background:{c}" title="{n} {p} %"></span>' for n, p, c in parts if p)
    legend = "".join(f'<span><i style="background:{c}"></i>{n} {p} %</span>' for n, p, c in parts)
    return (f'<div style="position:relative"><div style="display:flex;height:16px;gap:2px">{segs}</div>'
            f'<span style="position:absolute;left:80%;top:-6px;bottom:-6px;border-left:2px dashed var(--arc-hi)"></span></div>'
            f'<div class="legend">{legend}<span>Ziel: ≥ 75–80 % locker · {dur(split["minutes"])} gesamt</span></div>')


def profile_svg(items: list) -> str:
    flat = workouts.flat_steps(items)
    total = sum(s.seconds for s in flat) or 1
    top_pct = min(260, max(130, max(s.hi for s in flat) + 10))
    w, h, left, bottom = 640, 160, 38, 20
    ph = h - bottom - 6

    def y(p): return 6 + ph - clamp(p / top_pct) * ph

    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Intervallprofil des Workouts">']
    for p in (50, 100, 150, 200):
        if p <= top_pct:
            dash = ' stroke-dasharray="4 4"' if p == 100 else ""
            col = "var(--gold)" if p == 100 else "var(--line)"
            out.append(f'<line x1="{left}" x2="{w}" y1="{y(p):.1f}" y2="{y(p):.1f}" stroke="{col}"{dash}/>'
                       f'<text x="{left - 6}" y="{y(p) + 4:.1f}" text-anchor="end">{p} %</text>')
    t = 0
    for s in flat:
        x0 = left + t / total * (w - left)
        bw = s.seconds / total * (w - left)
        color = zone_color(s.mid)
        out.append(f'<rect x="{x0:.2f}" y="{y(s.mid):.1f}" width="{max(.8, bw - .4):.2f}" height="{6 + ph - y(s.mid):.1f}" '
                   f'fill="{color}" fill-opacity=".85"/>')
        t += s.seconds
    minutes = total / 60
    step = 10 if minutes <= 90 else 30
    for m in range(0, int(minutes) + 1, step):
        out.append(f'<text x="{left + m * 60 / total * (w - left):.1f}" y="{h - 4}" text-anchor="middle">{m}′</text>')
    out.append("</svg>")
    return "".join(out)


def steps_table(items: list, ctx: Ctx) -> str:
    rows = []

    def row(s, prefix=""):
        hr = workouts.hr_range(s, ctx.hr_zones)
        return (f'<tr><td class="rep">{prefix}</td><td><span style="display:inline-block;width:9px;height:9px;'
                f'background:{zone_color(s.mid)};margin-right:8px"></span>{esc(s.label)}</td><td>{mmss(s.seconds)}</td>'
                f'<td>{workouts.watts(s.lo, ctx.ftp)}–{workouts.watts(s.hi, ctx.ftp)} W</td>'
                f'<td>{s.lo}–{s.hi} %</td><td>{f"{hr[0]}–{hr[1]}" if hr else "–"}</td></tr>')

    for item in items:
        if isinstance(item, workouts.Repeat):
            for i, s in enumerate(item.steps):
                rows.append(row(s, f"{item.count}×" if i == 0 else ""))
        else:
            rows.append(row(item))
    return ('<div class="tw"><table><thead><tr><th></th><th>Abschnitt</th><th>Dauer</th><th>Watt</th><th>% FTP</th>'
            '<th>Puls</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def zone_list(minutes: list | None, labels: list[str], colors: list[str]) -> str:
    if not minutes or not any(minutes):
        return ""
    top = max(minutes) or 1
    rows = "".join(
        f'<div style="display:grid;grid-template-columns:34px minmax(0,1fr) 62px;gap:8px;align-items:center;font-size:13px">'
        f'<span class="mono" style="color:var(--ink-2)">{lab}</span><span style="height:9px;background:rgba(95,217,255,.07)">'
        f'<span style="display:block;height:100%;width:{100 * (m or 0) / top:.1f}%;background:{col};box-shadow:0 0 6px {col}"></span></span>'
        f'<span class="mono" style="text-align:right">{dur(m or 0)}</span></div>'
        for lab, m, col in zip(labels, minutes, colors))
    return f'<div style="display:grid;gap:6px">{rows}</div>'


def te_meter(value, label: str) -> str:
    v = value or 0
    word = workouts_word(v)
    color = "var(--ink-3)" if v < 1 else "var(--arc)" if v < 3 else "var(--ok)" if v < 4 else "var(--gold)" if v < 5 else "var(--bad)"
    ticks = "".join(f'<span style="position:absolute;left:{i * 20}%;top:0;bottom:0;border-left:1px solid var(--void)"></span>' for i in range(1, 5))
    return (f'<div style="display:grid;gap:6px"><div style="display:flex;justify-content:space-between;font-size:14px">'
            f'<span>{label}</span><span class="mono" style="color:{color}">{de(value, 1)} · {word}</span></div>'
            f'<div style="position:relative;height:12px;background:rgba(95,217,255,.07)"><span style="position:absolute;left:0;top:0;'
            f'bottom:0;width:{20 * clamp(v, 0, 5):.1f}%;background:{color};box-shadow:0 0 8px {color}"></span>{ticks}</div></div>')


def workouts_word(v: float) -> str:
    return ("kein Effekt" if v < 1 else "gering" if v < 2 else "erhaltend" if v < 3 else "verbessernd" if v < 4
            else "stark verbessernd" if v < 5 else "Überlastung")


# ------------------------------------------------------------------------ page

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Oxanium:wght@500;600'
         '&family=Share+Tech+Mono&display=swap">')

CSS = """
:root{
  /* Layout: one HUD console column (max 1120px). Hero = reactor gauge + status readout, then a 12-column panel grid that stacks on phones. */
  --void:#03070c; --glass:rgba(9,27,42,.62); --grid:rgba(95,217,255,.055);
  --line:rgba(95,217,255,.18); --line-hi:rgba(95,217,255,.5);
  --arc:#5fd9ff; --arc-hi:#c4f3ff; --arc-deep:#2f8bff; --violet:#a493ff;
  --ink:#e2f6ff; --ink-2:#93b8c9; --ink-3:#5f8293;
  --gold:#f6bd47; --vo2:#ff8a3d; --hot:#ff4d5a;
  --ok:#43f0b4; --warn:#ffb648; --bad:#ff5b6b;
  --f-display:"Oxanium","Segoe UI",system-ui,sans-serif;
  --f-body:"Barlow","Segoe UI",system-ui,sans-serif;
  --f-mono:"Share Tech Mono",ui-monospace,"Cascadia Mono",Consolas,monospace;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:400 16px/1.55 var(--f-body);-webkit-font-smoothing:antialiased;background:
  radial-gradient(900px 520px at 78% -8%,rgba(95,217,255,.13),transparent 62%),
  radial-gradient(700px 420px at -10% 30%,rgba(47,139,255,.08),transparent 60%),
  linear-gradient(var(--grid) 1px,transparent 1px) 0 0/28px 28px,
  linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/28px 28px,var(--void)}
.hud{max-width:1120px;margin:0 auto;padding-block:18px 56px;padding-inline:16px;display:grid;gap:16px}
.mono{font-family:var(--f-mono);letter-spacing:.06em}
.top{display:flex;flex-wrap:wrap;gap:8px 20px;justify-content:space-between;align-items:center;font:13px var(--f-mono);
  letter-spacing:.16em;text-transform:uppercase;color:var(--ink-2);border-bottom:1px solid var(--line);padding-bottom:10px}
.top b{color:var(--arc);font-weight:400}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok);margin-right:8px;
  vertical-align:1px;animation:pulse 2.4s ease-in-out infinite}
.dot.stale{background:var(--warn);box-shadow:0 0 8px var(--warn)}
@keyframes pulse{50%{opacity:.35}}
.pnl{position:relative;background:var(--glass);border:1px solid var(--line);padding:18px;min-width:0}
.pnl::before,.pnl::after{content:"";position:absolute;width:16px;height:16px;pointer-events:none}
.pnl::before{top:-1px;left:-1px;border-top:2px solid var(--arc);border-left:2px solid var(--arc)}
.pnl::after{bottom:-1px;right:-1px;border-bottom:2px solid var(--arc);border-right:2px solid var(--arc)}
.ph{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin:0 0 14px;font:13px var(--f-mono);
  letter-spacing:.16em;text-transform:uppercase;color:var(--arc)}
.ph span:last-child{color:var(--ink-3);letter-spacing:.08em}
.hero{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:28px;align-items:center;overflow:hidden}
.scan{position:absolute;left:0;right:0;top:0;height:30%;background:linear-gradient(180deg,transparent,rgba(95,217,255,.07) 50%,transparent);
  animation:scan 8s linear infinite;pointer-events:none}
@keyframes scan{from{transform:translateY(-100%)}to{transform:translateY(340%)}}
.greet{font:13px var(--f-mono);letter-spacing:.2em;text-transform:uppercase;color:var(--ink-2);margin:0}
h1{font:600 clamp(26px,3.6vw,38px)/1.12 var(--f-display);margin:6px 0 12px;text-wrap:balance}
.chip{display:inline-flex;align-items:center;gap:8px;font:13px var(--f-mono);letter-spacing:.14em;text-transform:uppercase;
  padding:6px 12px;border:1px solid currentColor;color:var(--arc)}
.chip.good{color:var(--ok)}.chip.warn{color:var(--warn)}.chip.bad{color:var(--bad)}.chip.gold{color:var(--gold)}
.summary{font-size:17px;max-width:62ch;margin:14px 0 0}
.notes{margin:12px 0 0;padding:0;list-style:none;display:grid;gap:6px}
.notes li{font-size:14px;color:var(--warn);padding-left:18px;position:relative}
.notes li::before{content:"";position:absolute;left:0;top:.5em;width:7px;height:7px;border:1px solid var(--warn);transform:rotate(45deg)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.minis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:18px;max-width:420px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}
.tile{position:relative;background:var(--glass);border:1px solid var(--line);padding:14px 14px 10px;min-width:0;display:grid;gap:2px;align-content:start}
.tile::before{content:"";position:absolute;top:-1px;left:-1px;width:42%;height:2px;background:var(--state,var(--arc));box-shadow:0 0 10px var(--state,var(--arc))}
.tl{font:12px var(--f-mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2)}
.tv{font:600 30px/1.15 var(--f-display);font-variant-numeric:tabular-nums}
.tv small{font:500 14px var(--f-body);color:var(--ink-2);margin-left:4px}
.ts{font-size:13px;color:var(--state,var(--ink-2))}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:16px}
.c4{grid-column:span 4}.c5{grid-column:span 5}.c6{grid-column:span 6}.c7{grid-column:span 7}.c8{grid-column:span 8}.c12{grid-column:span 12}
svg{display:block;width:100%;height:auto}
svg text{font-family:var(--f-mono);font-size:11px;fill:var(--ink-3)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font:12px var(--f-mono);letter-spacing:.05em;color:var(--ink-2);margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px 16px;margin-top:14px}
.kv div{display:grid;min-width:0}
.kv span{font:12px var(--f-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)}
.kv b{font:600 18px var(--f-display);font-variant-numeric:tabular-nums}
.trends{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:18px}
.trend{display:grid;gap:4px;min-width:0}
.trend .tv{font-size:24px}
.sub{font:12px var(--f-mono);letter-spacing:.06em;color:var(--ink-3)}
.mission{border-color:rgba(246,189,71,.4);background:linear-gradient(180deg,rgba(246,189,71,.08),transparent 45%),var(--glass)}
.mission::before,.mission::after{border-color:var(--gold)}
.mission .ph{color:var(--gold)}
h2{font:600 clamp(24px,3vw,32px)/1.15 var(--f-display);margin:0 0 10px;text-wrap:balance}
.mission h2{color:var(--gold)}
.why{font-size:18px;margin:12px 0;max-width:70ch}
.ev{font-size:14px;color:var(--ink-2);margin:8px 0 0;max-width:80ch}
.ev b,.alt b{font:12px var(--f-mono);letter-spacing:.14em;text-transform:uppercase;color:var(--gold);margin-right:8px;font-weight:400}
.alt{font-size:15px;margin:10px 0 0;max-width:80ch}
table{border-collapse:collapse;width:100%;font-size:15px}
.tw{overflow-x:auto;margin-top:14px}
th{font:12px var(--f-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid rgba(95,217,255,.08);font-variant-numeric:tabular-nums;white-space:nowrap}
td.rep{font:600 15px var(--f-display);color:var(--gold)}
.btnrow{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:18px}
.btn{font:600 15px var(--f-display);letter-spacing:.06em;text-transform:uppercase;color:var(--void);background:var(--gold);border:0;
  padding:12px 20px;cursor:pointer;clip-path:polygon(10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%,0 10px)}
.btn:hover{filter:brightness(1.12)}.btn:focus-visible{outline:2px solid var(--arc-hi);outline-offset:3px}
.btn:disabled{opacity:.45;cursor:not-allowed}
details{margin-top:12px;font-size:14px;color:var(--ink-2)}summary{cursor:pointer;color:var(--arc);font-family:var(--f-mono);letter-spacing:.06em}
details ol{margin:8px 0 0;padding-left:20px}
.act{display:grid;gap:16px}
.act-h{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 16px;align-items:baseline}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}
.say{font-size:16px;margin:0;max-width:75ch}
.say b{font:12px var(--f-mono);letter-spacing:.14em;text-transform:uppercase;color:var(--arc);margin-right:8px;font-weight:400}
.foot{font:12px var(--f-mono);letter-spacing:.06em;color:var(--ink-3);display:flex;flex-wrap:wrap;gap:6px 18px;border-top:1px solid var(--line);padding-top:12px}
.empty{color:var(--ink-3);font-size:15px;margin:0}
.preview{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px}
.pv{position:relative;display:grid;gap:2px;align-content:start;min-width:0;padding:10px 10px 8px;border:1px solid var(--line);
  background:rgba(95,217,255,.03);font-size:13px;color:var(--ink-2);overflow-wrap:break-word;hyphens:auto;-webkit-hyphens:auto}
.pv::before{content:"";position:absolute;top:-1px;left:-1px;right:-1px;height:3px;background:var(--k);box-shadow:0 0 8px var(--k)}
.pv.maybe::before{background:repeating-linear-gradient(90deg,var(--k) 0 6px,transparent 6px 10px);box-shadow:none}
.pv.now{border-color:var(--line-hi);background:rgba(95,217,255,.09)}
.pv b{font:600 14px/1.2 var(--f-display);color:var(--k)}
.pv-d{font:12px var(--f-mono);letter-spacing:.08em;color:var(--ink-3)}
.pv.now .pv-d{color:var(--arc-hi)}
.pv-m{font:12px var(--f-mono);color:var(--ink-3)}
.sigs{display:grid;gap:8px;margin-top:14px}
.sig{display:grid;grid-template-columns:12px minmax(0,1fr);gap:0 10px;align-items:center;font-size:14px}
.sig i{width:8px;height:8px;border:1px solid var(--ok);transform:rotate(45deg)}
.sig.hit i{background:var(--bad);border-color:var(--bad);box-shadow:0 0 6px var(--bad)}
.sig.hit span:first-of-type{color:var(--bad)}
.sig .mono{grid-column:2;font-size:12px;color:var(--ink-3)}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 48s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width:820px){.hero{grid-template-columns:1fr}.hero>.reactor{max-width:250px;margin:0 auto;width:100%}
  .c4,.c5,.c6,.c7,.c8{grid-column:span 12}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""

DOWNLOAD_JS = """
<script>
(() => {
  const btn = document.getElementById('dl'), msg = document.getElementById('dl-msg');
  if (!btn) return;
  const ready = (window.claude && typeof window.claude.use === 'function')
    ? window.claude.use('downloads').catch(() => null) : Promise.resolve(null);
  ready.then(api => { if (!api) { btn.disabled = true; msg.textContent = 'Download ist in dieser Ansicht nicht verfügbar – öffne die Seite in claude.ai.'; } });
  btn.addEventListener('click', async () => {
    const api = await ready;
    if (!api) return;
    const raw = atob(btn.dataset.zip), bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    msg.textContent = '';
    try {
      await api.save({filename: btn.dataset.name, data: new Blob([bytes])});
      msg.textContent = 'Gespeichert: ' + btn.dataset.name;
    } catch (e) {
      const code = e && e.code;
      msg.textContent = code === 'declined' ? 'Download abgebrochen.' : code === 'rate_limited'
        ? 'Bitte kurz warten und erneut tippen.' : 'Speichern war nicht möglich (' + (code || 'Fehler') + ').';
    }
  });
})();
</script>
"""


def page(title: str, body: str, script: str = "") -> str:
    return f"<title>{esc(title)}</title>\n{FONTS}\n<style>{CSS}</style>\n<main class=\"hud\" lang=\"de\">\n{body}\n</main>\n{script}"


def tile(label: str, value: str, unit: str, sub: str, state: str = "neutral", extra: str = "") -> str:
    return (f'<div class="tile" style="--state:{STATE[state]}"><span class="tl">{esc(label)}</span>'
            f'<span class="tv">{esc(value)}<small>{esc(unit)}</small></span><span class="ts">{esc(sub)}</span>{extra}</div>')


def topbar(kind: str, ctx: Ctx) -> str:
    d = ctx.day
    age = ctx.sync_age_h()
    stale = age is None or age > 3
    stand = datetime.fromisoformat(ctx.last_sync).strftime("%d.%m. %H:%M") if ctx.last_sync else "–"
    return (f'<header class="top"><span><b>◢ {esc(kind)}</b></span><span>{WD[d.weekday()]} {d:%d.%m.%Y}</span>'
            f'<span><i class="dot{" stale" if stale else ""}"></i>Datenstand {stand}</span></header>')


def notes_html(notes) -> str:
    notes = [n for n in (notes or []) if n]
    return ('<ul class="notes">' + "".join(f"<li>{esc(n)}</li>" for n in notes) + "</ul>") if notes else ""


def foot(ctx: Ctx) -> str:
    return ('<footer class="foot"><span>Quelle: Garmin Connect, nur lesend</span><span>Methodik: training/methodology.md</span>'
            f'<span>FTP {ctx.ftp} W</span><span>Keine medizinische Beratung</span></footer>')


def workout_spec(ctx: Ctx, a: dict) -> dict | None:
    """The workout spec from the analysis: a full spec or a library id. None on a rest day."""
    spec = (a.get("workout") or {}).get("spec")
    if isinstance(spec, str):
        spec = ctx.sessions.get(spec, {}).get("spec")
    return spec if isinstance(spec, dict) and (spec.get("steps") or spec.get("exercises") or spec.get("parts")) else None


def write_schedule(ctx: Ctx, a: dict) -> Path | None:
    """Leave the day's workout in scheduled/ for the Garmin calendar upload (GitHub workflow).
    Only when the user has agreed to it (calendar_upload in dashboard.json)."""
    spec = workout_spec(ctx, a)
    sport = (spec or {}).get("sport", "cycling")
    if not ctx.settings.get("calendar_upload") or not spec or sport not in CALENDAR_SPORTS:
        return None
    target = ctx.root / "scheduled" / f"{ctx.day.isoformat()}.json"
    try:
        if json.loads(target.read_text(encoding="utf-8")).get("upload"):
            return None  # already uploaded today
    except (OSError, ValueError):
        pass
    w = a.get("workout") or {}
    job = {"date": ctx.day.isoformat(), "sport": sport, "title": w.get("title") or spec.get("name"),
           "description": f'{w.get("why") or ""} (Morning Briefing)'.strip(), "ftp": ctx.ftp, "spec": spec}
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(job, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return target


def morning(ctx: Ctx, a: dict, scheduled: bool = False) -> str:
    d = ctx.day
    r = ctx.rec(d)
    sl, hrv, rhr = r.get("sleep") or {}, r.get("hrv") or {}, r.get("resting_hr") or {}
    bb, ts = r.get("body_battery") or {}, r.get("training_status") or {}
    ready = (r.get("training_readiness") or {}).get("morning") or {}
    phase = ctx.phase(d)
    plan = ctx.plan_on(d)
    notes = list(a.get("notes") or []) + ([] if ctx.profile.get("setup_done") else [SETUP_HINT])
    if not plan:
        notes.append("Vorschau veraltet: für heute steht kein Tag im Plan. Das Training ist nach Tagesform gewählt; "
                     "der Daily Wrap-Up schreibt die Vorschau heute Abend fort.")
    status = a.get("status") if a.get("status") in STATUS else ctx.draft_status(d)[0]
    state, status_word = STATUS[status]

    # hero
    reactor = ring_svg(ready.get("score"), 100, de(ready.get("score")) if ready.get("score") is not None else "–",
                       "Bereitschaft", state, sub=(ready.get("level") or ""))
    minis = []
    for value, vmax, center, label, st in (
        (sl.get("score"), 100, de(sl.get("score")), "Schlaf", "good" if (sl.get("score") or 0) >= 80 else "warn" if (sl.get("score") or 0) >= 60 else "bad"),
        (bb.get("at_wake"), 100, de(bb.get("at_wake")), "Batterie", "good" if (bb.get("at_wake") or 0) >= 70 else "warn" if (bb.get("at_wake") or 0) >= 40 else "bad"),
        (hrv.get("last_night_avg"), (hrv.get("baseline_high") or 100) * 1.25, de(hrv.get("last_night_avg")), "HRV ms", hrv_state(hrv)),
    ):
        minis.append(f'<div>{ring_svg(value, vmax, center, label, st, size=120)}</div>')
    hero = (f'<section class="pnl hero"><div class="scan"></div><div class="reactor">{reactor}</div><div>'
            f'<p class="greet">{esc(greeting("Guten Morgen", ctx.settings["name"]))}</p><h1>{esc(a.get("headline") or "Systemcheck abgeschlossen")}</h1>'
            f'<div class="chips" style="margin-top:0"><span class="chip {state}">Status {status_word} · '
            f'{esc(a.get("status_text") or "")}</span>{phase_chip(phase)}</div>'
            f'<p class="summary">{esc(a.get("summary") or "")}</p>{notes_html(notes)}'
            f'<div class="minis">{"".join(minis)}</div></div></section>')

    # tiles
    rhr_delta = (rhr.get("today") - rhr.get("avg_7d")) if rhr.get("today") and rhr.get("avg_7d") else None
    rec_h = ready.get("recovery_time_h")
    tiles = "".join([
        tile("Schlaf", dur(sl.get("total_min")).replace(" h", ""), "h" if (sl.get("total_min") or 0) >= 60 else "",
             f'Bedarf {dur(sl.get("need_min"))} · Score {de(sl.get("score"))}' if sl else "noch nicht synchronisiert",
             "good" if (sl.get("score") or 0) >= 80 else "warn" if (sl.get("score") or 0) >= 60 else "bad" if sl else "neutral",
             spark(ctx.trend(d, ("sleep", "score")), color="var(--violet)")),
        tile("HRV", de(hrv.get("last_night_avg")), "ms",
             f'Normal {de(hrv.get("baseline_low"))}–{de(hrv.get("baseline_high"))} · Ø7 {de(hrv.get("weekly_avg"))}' if hrv else "keine Daten",
             hrv_state(hrv), spark(ctx.trend(d, ("hrv", "last_night_avg")), band=hrv_band(ctx, d))),
        tile("Ruhepuls", de(rhr.get("today")), "bpm",
             f'{"+" if (rhr_delta or 0) > 0 else ""}{de(rhr_delta)} zum Ø7 ({de(rhr.get("avg_7d"))})' if rhr_delta is not None else "–",
             "neutral" if rhr_delta is None else "good" if rhr_delta <= 1 else "warn" if rhr_delta < 5 else "bad",
             spark(ctx.trend(d, ("resting_hr", "today")), color="var(--hot)")),
        tile("Body Battery", de(bb.get("at_wake")), "beim Aufwachen",
             f'+{de(sl.get("body_battery_gain"))} über Nacht' if sl.get("body_battery_gain") is not None else "–",
             "good" if (bb.get("at_wake") or 0) >= 70 else "warn" if (bb.get("at_wake") or 0) >= 40 else "bad"),
        tile("Bereitschaft", de(ready.get("score")), "/ 100", (ready.get("level") or "–") + (f' · {ready["feedback"]}' if ready.get("feedback") else ""),
             "good" if (ready.get("score") or 0) >= 70 else "warn" if (ready.get("score") or 0) >= 50 else "bad" if ready else "neutral",
             spark(ctx.trend(d, ("training_readiness", "morning", "score")), color="var(--ok)")),
        tile("Erholungszeit", de(rec_h), "h", "noch nötig laut Garmin",
             "neutral" if rec_h is None else "good" if rec_h < 12 else "warn" if rec_h <= 24 else "bad"),
    ])

    # sleep + night curves
    night = ""
    if sl.get("start") and sl.get("end"):
        start, end = datetime.fromisoformat(sl["start"]), datetime.fromisoformat(sl["end"])
        total = (end - start).total_seconds() / 60
        curves_today = r.get("curves") or {}
        stages = curves_today.get("sleep_stages") or []
        phase_total = sum(sl.get(k) or 0 for k in ("deep_min", "light_min", "rem_min", "awake_min")) or 1
        phases = "".join(f'<span style="width:{100 * (sl.get(k) or 0) / phase_total:.1f}%;background:{STAGE_COLOR[s]}"></span>'
                         for k, s in (("deep_min", "deep"), ("light_min", "light"), ("rem_min", "rem"), ("awake_min", "awake")))
        legend = "".join(f'<span><i style="background:{STAGE_COLOR[s]}"></i>{STAGE_DE[s]} {dur(sl.get(k))} · '
                         f'{round(100 * (sl.get(k) or 0) / phase_total)} %</span>'
                         for k, s in (("deep_min", "deep"), ("light_min", "light"), ("rem_min", "rem"), ("awake_min", "awake")))
        ticks = hour_ticks(start, total)

        def night_series(name):
            """Sleep curves are stored on the wake-up day but may start the evening before."""
            pts = []
            for t, v in curves_today.get(name) or []:
                dt = place(t, start, end)
                if dt:
                    pts.append(((dt - start).total_seconds() / 60, v))
            return sorted(pts)

        def calendar_series(name):
            """Calendar-day curves: join yesterday's evening and today's morning."""
            pts = []
            for dd in (d - timedelta(days=1), d):
                for t, v in (ctx.rec(dd).get("curves") or {}).get(name) or []:
                    tt = hm(t)
                    if not tt:
                        continue
                    dt = datetime(dd.year, dd.month, dd.day, tt[0], tt[1])
                    if start - timedelta(minutes=5) <= dt <= end + timedelta(minutes=5):
                        pts.append(((dt - start).total_seconds() / 60, v))
            return sorted(pts)

        hr_pts, hrv_pts = night_series("sleep_hr"), night_series("hrv_overnight")
        bb_pts = calendar_series("body_battery")

        def bounds(pts, pad):
            vals = [v for _, v in pts] or [0, 1]
            return min(vals) - pad, max(vals) + pad

        night = (
            f'<section class="pnl c7"><div class="ph"><span>Schlafarchitektur</span><span>{sl["start"][11:16]} → {sl["end"][11:16]} · '
            f'{dur(sl.get("total_min"))}</span></div>{hypnogram(stages, start, end)}'
            f'<div style="display:flex;height:12px;gap:2px;margin-top:14px">{phases}</div><div class="legend">{legend}</div>'
            f'<div class="kv"><div><span>Score</span><b>{de(sl.get("score"))} · {esc(sl.get("quality") or "–")}</b></div>'
            f'<div><span>Ø Puls</span><b>{de(sl.get("avg_hr"))} bpm</b></div><div><span>Atmung</span><b>{de(sl.get("avg_respiration"), 1)}/min</b></div>'
            f'<div><span>SpO2 Ø</span><b>{de(sl.get("avg_spo2"))} %</b></div><div><span>Schlafstress</span><b>{de(sl.get("avg_sleep_stress"))}</b></div>'
            f'<div><span>Wachphasen</span><b>{de(sl.get("awake_count"))}×</b></div></div></section>'
            f'<section class="pnl c5"><div class="ph"><span>Nachtkurven</span><span>Puls · HRV · Batterie</span></div>'
            f'<p class="sub">HERZFREQUENZ (BPM)</p>{time_chart(hr_pts, total, *bounds(hr_pts, 3), "var(--hot)", ticks, h=100)}'
            f'<p class="sub" style="margin-top:10px">HRV (MS)</p>{time_chart(hrv_pts, total, *bounds(hrv_pts, 5), "var(--arc)", ticks, h=100)}'
            f'<p class="sub" style="margin-top:10px">BODY BATTERY</p>{time_chart(bb_pts, total, 0, 100, "var(--ok)", ticks, h=100, area=True)}'
            f'</section>')
    else:
        night = ('<section class="pnl c12"><div class="ph"><span>Schlafarchitektur</span><span>–</span></div>'
                 '<p class="empty">Die letzte Nacht ist noch nicht bei Garmin angekommen. Synchronisiere die Uhr mit der Garmin-App.</p></section>')

    # trends
    days14 = [d - timedelta(days=i) for i in range(13, -1, -1)]
    trend_items = [("HRV", ("hrv", "last_night_avg"), "ms", "var(--arc)", hrv_band(ctx, d)),
                   ("Ruhepuls", ("resting_hr", "today"), "bpm", "var(--hot)", None),
                   ("Schlaf-Score", ("sleep", "score"), "", "var(--violet)", None),
                   ("Bereitschaft", ("training_readiness", "morning", "score"), "", "var(--ok)", None)]
    trends = []
    for name, path, unit, color, band in trend_items:
        vals = ctx.trend(d, path)
        real = [v for v in vals if v is not None]
        rng = f"{de(min(real))}–{de(max(real))}" if real else "–"
        trends.append(f'<div class="trend"><span class="tl">{name}</span><span class="tv">{de(vals[-1])}<small>{unit}</small></span>'
                      f'{spark(vals, w=240, h=56, color=color, band=band)}<span class="sub">14 Tage · Spanne {rng}</span></div>')
    trend_html = (f'<section class="pnl c12"><div class="ph"><span>Trends</span><span>{days14[0]:%d.%m.} – {d:%d.%m.}'
                  f'{" · grünes Band = HRV-Normalbereich" if any(hrv_band(ctx, d)) else ""}</span></div>'
                  f'<div class="trends">{"".join(trends)}</div></section>')

    # load + season
    load_items = []
    for dd in days14:
        acts = ctx.acts_on(dd)
        load = ctx.load_on(dd)
        main = max(acts, key=lambda x: x.get("training_load") or 0)["primary_benefit"] if acts else None
        load_items.append((f"{WD[dd.weekday()][0]}{dd.day}", load, benefit_color(main)))
    legend = "".join(f'<span><i style="background:{c}"></i>{n}</span>' for n, c in
                     (("Grundlage", "var(--arc-deep)"), ("Tempo/Schwelle", "var(--gold)"), ("VO2max", "var(--vo2)"), ("Anaerob/Sprint", "var(--hot)")))
    load_html = (f'<section class="pnl c7"><div class="ph"><span>Trainingslast</span><span>14 Tage · Status {esc(ts.get("status") or "–")}</span></div>'
                 f'{bars_svg(load_items)}<div class="legend">{legend}</div>'
                 f'<div class="kv"><div><span>Akut</span><b>{de(ts.get("acute_load"))}</b></div><div><span>Chronisch</span><b>{de(ts.get("chronic_load"))}</b></div>'
                 f'<div><span>7-Tage-Last</span><b>{de(ts.get("weekly_load"))}</b></div><div><span>VO2max Rad</span><b>{de(ts.get("vo2max_cycling"), 1)}</b></div></div>'
                 f'<p class="sub" style="margin:18px 0 10px">4-WOCHEN-LASTVERTEILUNG</p>{focus_rows(ts.get("load_focus_4_weeks"))}</section>')
    if phase:
        phase_meta = "Tag {} · bis {:%d.%m.}".format(phase["day_in_phase"], date.fromisoformat(phase["end"]))
        phase_head = (f'<h2 style="color:{FOCUS_COLOR.get(phase.get("focus"), "var(--arc)")}">{esc(phase["name"])}</h2>'
                      f'<p class="ev" style="margin-top:0">Schwerpunkt {esc(FOCUS_DE.get(phase.get("focus"), phase.get("focus") or "–"))}'
                      + (f', danach {esc(phase["next_name"])}' if phase.get("next_name") else "") + ".</p>")
    else:
        phase_meta = "–"
        phase_head = '<p class="empty">Für heute steht kein Saisonabschnitt im Plan; der Daily Wrap-Up verlängert ihn.</p>'
    season_html = (f'<section class="pnl c5"><div class="ph"><span>Saison</span><span>{phase_meta}</span></div>{phase_head}'
                   f'{countdown_html(trainer.countdown(ctx.profile, d))}'
                   f'<div style="margin-top:14px">{season_strip(ctx.season, d)}</div>'
                   f'<p class="sub" style="margin:18px 0 6px">BELASTUNGSVERHÄLTNIS AKUT ÷ CHRONISCH</p>'
                   f'<div style="max-width:300px">{ratio_gauge(ts.get("load_ratio"))}</div>'
                   f'<p class="sub" style="margin:14px 0 8px">INTENSITÄT LETZTE 7 TAGE (PULSZONEN)</p>{intensity_bar(ctx.intensity_split(d - timedelta(days=7), d - timedelta(days=1)))}'
                   f'</section>')

    # recovery + preview
    recovery_html = recovery_panel(ctx, ctx.recovery(d))
    preview_html = preview_panel(ctx, ctx.plan_from(d), d, "c7",
                                 "Vorschau veraltet – der Daily Wrap-Up schreibt sie heute Abend fort.")

    # mission
    w = a.get("workout") or {}
    spec = workout_spec(ctx, a)
    sport = (spec or {}).get("sport", "cycling")
    title = w.get("title") or (spec or {}).get("name") or ""
    evidence = (f'<p class="ev"><b>Evidenz</b>{esc(w.get("science") or "")}</p>'
                + (f'<p class="alt"><b>Alternative</b>{esc(w["alternative"])}</p>' if w.get("alternative") else ""))
    calendar = (f'<p class="ev"><b>Garmin-Kalender</b>Wird automatisch als „[HUD] {esc(title)}“ für heute eingetragen. '
                f'Edge oder fēnix synchronisieren, dann unter Training › Kalender starten.</p>' if scheduled else "")
    download = bool(spec) and sport == "cycling"
    if download:
        filename, blob, items = workouts.build_bundle(spec, ctx.ftp, ctx.hr_zones, d.isoformat())
        minutes = workouts.total_seconds(items) / 60
        zip_attr = f'data-zip="{base64.b64encode(blob).decode()}" data-name="{esc(filename)}"'
        mission_body = (
            f'<div class="chips" style="margin-top:0"><span class="chip gold">{dur(minutes)}</span>'
            f'<span class="chip gold">≈ {workouts.estimated_tss(items)} TSS</span>'
            f'<span class="chip gold">Fokus {esc(w.get("focus") or "–")}</span><span class="chip">FTP {ctx.ftp} W</span></div>'
            f'<p class="why">{esc(w.get("why") or "")}</p>{profile_svg(items)}{steps_table(items, ctx)}{evidence}'
            f'<div class="btnrow"><button class="btn" id="dl" type="button" {zip_attr}>Workout laden · .zip</button>'
            f'<span class="mono" id="dl-msg" role="status" style="color:var(--ink-2);font-size:13px"></span></div>{calendar}'
            f'<details><summary>So kommt das Workout auf deinen Edge, deine fēnix oder in Zwift</summary><ol>'
            f'<li>ZIP öffnen. Darin: <span class="mono">.fit</span> für Garmin, <span class="mono">.zwo</span> für Zwift.</li>'
            f'<li>Garmin: Gerät per USB an den PC, die .fit-Datei nach <span class="mono">Garmin\\NewFiles</span> kopieren, trennen. '
            f'Das Workout steht dann unter Training › Workouts.</li>'
            f'<li>Zwift: die .zwo-Datei nach <span class="mono">Dokumente\\Zwift\\Workouts\\&lt;deine Zwift-Nummer&gt;</span> kopieren.</li></ol></details>')
    elif spec:
        spec_id = w.get("spec") if isinstance(w.get("spec"), str) else None
        minutes = plan.get("duration_min") if plan and plan.get("session") == spec_id else w.get("duration_min")
        try:
            minutes = float(minutes) if minutes else None
        except (TypeError, ValueError):
            minutes = None  # e.g. "etwa eine Stunde" from the analysis: leave the chip out
        chips = [SPORT_DE.get(sport, sport)] + ([dur(minutes)] if minutes else [])
        if sport == "strength":
            chips.append(f'{len(spec.get("exercises") or [])} Übungen')
            device = calendar or ('<p class="ev"><b>Garmin</b>Krafteinheiten kommen über den Garmin-Kalender auf die fēnix; '
                                  'eine Datei zum Herunterladen folgt später.</p>')
        else:
            device = ('<p class="ev"><b>Garmin</b>Lauf-, Schwimm- und Koppel-Workouts kommen in einer späteren Ausbaustufe als '
                      'Datei und in den Garmin-Kalender. Bis dahin die Abschnitte aus der Tabelle übernehmen.</p>')
        mission_body = (f'<div class="chips" style="margin-top:0">'
                        + "".join(f'<span class="chip gold">{esc(c)}</span>' for c in chips + [f'Fokus {w.get("focus") or "–"}'])
                        + f'</div><p class="why">{esc(w.get("why") or "")}</p>{describe_table(spec)}{evidence}{device}')
    else:
        mission_body = (f'<p class="why">{esc(w.get("why") or "Heute ist Ruhetag.")}</p>'
                        + (f'<p class="alt"><b>Alternative</b>{esc(w["alternative"])}</p>' if w.get("alternative") else ""))
    mission = (f'<section class="pnl mission c12"><div class="ph"><span>Mission · Trainingsvorschlag</span>'
               f'<span>{esc(phase["name"]) if phase else ""}</span></div><h2>{esc(title or "Ruhetag")}</h2>{mission_body}</section>')

    body = (topbar("Morning Briefing", ctx) + hero + f'<section class="tiles">{tiles}</section>'
            + f'<div class="grid">{night}{trend_html}{recovery_html}{preview_html}{mission}{load_html}{season_html}</div>'
            + foot(ctx))
    return page("Morning Briefing", body, DOWNLOAD_JS if download else "")


def hrv_state(hrv: dict) -> str:
    v, lo, hi = hrv.get("last_night_avg"), hrv.get("baseline_low"), hrv.get("baseline_high")
    if not v:
        return "neutral"
    if (hrv.get("status") or "") in ("low", "poor") or (lo and v < lo):
        return "bad"
    if hrv.get("status") == "unbalanced":
        return "warn"
    return "good"


def hrv_band(ctx: Ctx, d: date) -> list:
    lows, highs = ctx.trend(d, ("hrv", "baseline_low")), ctx.trend(d, ("hrv", "baseline_high"))
    return [[lo, hi] if lo and hi else None for lo, hi in zip(lows, highs)]


def benefit_color(benefit: str | None) -> str:
    if benefit in ("vo2max",):
        return "var(--vo2)"
    if benefit in ("anaerobic capacity", "speed", "sprint"):
        return "var(--hot)"
    if benefit in ("tempo", "lactate threshold"):
        return "var(--gold)"
    return "var(--arc-deep)"


def wrapup(ctx: Ctx, a: dict) -> str:
    d = ctx.day
    r = ctx.rec(d)
    bb, st, steps = r.get("body_battery") or {}, r.get("stress") or {}, r.get("steps") or {}
    energy, ts = r.get("energy") or {}, r.get("training_status") or {}
    tr = r.get("training_readiness") or {}
    latest, morning_tr = tr.get("latest") or {}, tr.get("morning") or {}
    acts = ctx.acts_on(d)
    phase = ctx.phase(d)
    load_today = ctx.load_on(d)

    step_pct = 100 * (steps.get("total") or 0) / (steps.get("goal") or 1) if steps.get("goal") else None
    stress_avg = st.get("avg")
    rings = [
        ring_svg(bb.get("latest"), 100, de(bb.get("latest")), "Batterie", "good" if (bb.get("latest") or 0) >= 50 else "warn" if (bb.get("latest") or 0) >= 25 else "bad", size=120),
        ring_svg(stress_avg, 100, de(stress_avg), "Stress Ø", "neutral" if stress_avg is None else "good" if stress_avg <= 25 else "warn" if stress_avg <= 50 else "bad", size=120),
        ring_svg(load_today, max(150, load_today), de(load_today), "Load", "neutral", size=120),
    ]
    main_te = max(acts, key=lambda x: x.get("training_load") or 0) if acts else {}
    hero = (f'<section class="pnl hero"><div class="scan"></div><div class="reactor">'
            f'{ring_svg(step_pct, 100, de(steps.get("total")), "Schritte", "good" if (step_pct or 0) >= 100 else "neutral", sub=f"{de(step_pct)} % vom Ziel" if step_pct is not None else "")}'
            f'</div><div><p class="greet">{esc(greeting("Guten Abend", ctx.settings["name"]))}</p><h1>{esc(a.get("headline") or "Tagesbilanz")}</h1>'
            + phase_chip(phase) + f'<p class="summary">{esc(a.get("summary") or "")}</p>{notes_html(a.get("notes"))}'
            f'<div class="minis">{"".join(f"<div>{x}</div>" for x in rings)}</div></div></section>')

    tiles = "".join([
        tile("Schritte", de(steps.get("total")), "", f'Ziel {de(steps.get("goal"))} · Etagen {de(steps.get("floors"))}',
             "good" if (step_pct or 0) >= 100 else "neutral"),
        tile("Stress Ø", de(stress_avg), "/ 100", f'Spitze {de(st.get("max"))} · hoch {dur(st.get("high_min"))}',
             "neutral" if stress_avg is None else "good" if stress_avg <= 25 else "warn" if stress_avg <= 50 else "bad"),
        tile("Body Battery", de(bb.get("latest")), "jetzt", f'Tief {de(bb.get("lowest"))} · +{de(bb.get("charged"))} / −{de(bb.get("drained"))}',
             "good" if (bb.get("latest") or 0) >= 50 else "warn" if (bb.get("latest") or 0) >= 25 else "bad"),
        tile("Training Load", de(load_today), "heute", f'{len(acts)} Einheit{"en" if len(acts) != 1 else ""} · 7 Tage {de(ts.get("weekly_load"))}', "neutral"),
        tile("Trainingseffekt", f'{de(main_te.get("aerobic_te"), 1)} / {de(main_te.get("anaerobic_te"), 1)}' if main_te else "–", "",
             "aerob / anaerob (Haupteinheit)", "good" if (main_te.get("aerobic_te") or 0) >= 3 else "neutral"),
        tile("Erholungszeit", de(latest.get("recovery_time_h")), "h",
             f'Bereitschaft {de(morning_tr.get("score"))} → {de(latest.get("score"))}' if latest else "–",
             "neutral" if latest.get("recovery_time_h") is None else "good" if latest["recovery_time_h"] < 12 else "warn" if latest["recovery_time_h"] <= 24 else "bad"),
    ])

    # day timeline
    curves = r.get("curves") or {}
    bb_pts = [(h * 60 + m, v) for t, v in curves.get("body_battery") or [] if (hmv := hm(t)) for h, m in [hmv]]
    windows = []
    for act in acts:
        t = hm((act.get("start") or "")[11:16])
        if t:
            s = t[0] * 60 + t[1]
            windows.append((s, s + (act.get("duration_min") or 0), TYPE_DE.get(act.get("type"), "Training")))
    ticks = [(h * 60, f"{h:02d}") for h in range(0, 25, 3)]
    stress = curves.get("stress_hourly") or []
    stress_bars = []
    for t, v in stress:
        tt = hm(t)
        if tt and v is not None:
            stress_bars.append((tt[0], v))
    sw, sh, left = 640, 80, 34
    sbar = [f'<svg viewBox="0 0 {sw} {sh}" aria-hidden="true">']
    for hh, v in stress_bars:
        x0 = left + hh / 24 * (sw - left - 8)
        bh = (sh - 22) * v / 100
        col = "var(--ok)" if v <= 25 else "var(--arc)" if v <= 50 else "var(--warn)" if v <= 75 else "var(--bad)"
        sbar.append(f'<rect x="{x0 + 2:.1f}" y="{sh - 20 - bh:.1f}" width="{(sw - left - 8) / 24 - 4:.1f}" height="{bh:.1f}" fill="{col}"/>')
    for xv, text in ticks:
        sbar.append(f'<text x="{left + xv / 1440 * (sw - left - 8):.1f}" y="{sh - 4}" text-anchor="middle">{text}</text>')
    sbar.append("</svg>")
    split = [("Ruhe", st.get("rest_min"), "var(--ok)"), ("Niedrig", st.get("low_min"), "var(--arc)"),
             ("Mittel", st.get("medium_min"), "var(--warn)"), ("Hoch", st.get("high_min"), "var(--bad)")]
    split_total = sum(m or 0 for _, m, _ in split) or 1
    split_html = ('<div style="display:flex;height:12px;gap:2px;margin-top:12px">'
                  + "".join(f'<span style="width:{100 * (m or 0) / split_total:.1f}%;background:{c}"></span>' for _, m, c in split if m)
                  + '</div><div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{n} {dur(m)}</span>' for n, m, c in split if m is not None) + "</div>")
    timeline = (f'<section class="pnl c12"><div class="ph"><span>Tagesverlauf</span><span>Body Battery · Trainings · Stress</span></div>'
                f'<p class="sub">BODY BATTERY</p>{time_chart(bb_pts, 1440, 0, 100, "var(--ok)", ticks, h=170, area=True, windows=windows)}'
                f'<p class="sub" style="margin-top:12px">STRESS PRO STUNDE</p>{"".join(sbar) if stress_bars else "<p class=empty>Keine Stressdaten.</p>"}'
                f'{split_html}</section>')

    # workouts
    texts = {str(k): v for k, v in (a.get("activities") or {}).items()}
    cards = []
    hr_labels, hr_colors = ["Z1", "Z2", "Z3", "Z4", "Z5"], ["var(--ink-3)", "var(--arc-deep)", "var(--arc)", "var(--gold)", "var(--hot)"]
    pw_labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    pw_colors = ["var(--ink-3)", "var(--arc-deep)", "var(--arc)", "var(--gold)", "var(--vo2)", "var(--hot)", "var(--violet)"]
    for act in acts:
        t = texts.get(str(act.get("id"))) or {}
        kv = [("Dauer", dur(act.get("duration_min"))), ("Distanz", f'{de(act.get("distance_km"), 1)} km'),
              ("Ø Tempo", f'{de(act.get("avg_speed_kmh"), 1)} km/h'), ("Höhenmeter", f'{de(act.get("elevation_gain_m"))} m'),
              ("Puls Ø / max", f'{de(act.get("avg_hr"))} / {de(act.get("max_hr"))}'),
              ("Watt Ø / NP", f'{de(act.get("avg_power"))} / {de(act.get("norm_power"))}' if act.get("avg_power") else "–"),
              ("IF · TSS", f'{de(act.get("intensity_factor"), 2)} · {de(act.get("tss"))}' if act.get("tss") else "–"),
              ("Load", de(act.get("training_load"))), ("Kalorien", f'{de(act.get("calories"))} kcal')]
        zones = zone_list(act.get("hr_zones_min"), hr_labels, hr_colors)
        pzones = zone_list(act.get("power_zones_min"), pw_labels, pw_colors)
        cards.append(
            f'<section class="pnl c12 act"><div class="act-h"><h2>{esc(TYPE_DE.get(act.get("type"), act.get("type") or "Training"))} · '
            f'{(act.get("start") or "")[11:16]}</h2><span class="sub">{esc(act.get("name") or "")}'
            f'{" · " + esc(act["device"]) if act.get("device") else ""}</span></div>'
            f'<div class="kv" style="margin-top:0">' + "".join(f"<div><span>{k}</span><b>{esc(v)}</b></div>" for k, v in kv) + "</div>"
            f'<div class="cols"><div style="display:grid;gap:14px">{te_meter(act.get("aerobic_te"), "Aerober Effekt")}'
            f'{te_meter(act.get("anaerobic_te"), "Anaerober Effekt")}<p class="sub">HAUPTNUTZEN: '
            f'{esc((BENEFIT_DE.get(act.get("primary_benefit")) or act.get("primary_benefit") or "–").upper())}</p></div>'
            + (f'<div><p class="sub" style="margin:0 0 8px">PULSZONEN</p>{zones}</div>' if zones else "")
            + (f'<div><p class="sub" style="margin:0 0 8px">LEISTUNGSZONEN</p>{pzones}</div>' if pzones else "") + "</div>"
            + (f'<p class="say"><b>Einordnung</b>{esc(t["assessment"])}</p>' if t.get("assessment") else "")
            + (f'<p class="say"><b>Effekt</b>{esc(t["effect"])}</p>' if t.get("effect") else "") + "</section>")
    if not cards:
        cards.append('<section class="pnl c12"><div class="ph"><span>Trainings</span><span>heute</span></div>'
                     '<p class="empty">Heute kein Training aufgezeichnet – Ruhetag.</p></section>')

    # week + outlook
    week_days = [d - timedelta(days=i) for i in range(6, -1, -1)]
    week_items = []
    for dd in week_days:
        day_acts = ctx.acts_on(dd)
        main = max(day_acts, key=lambda x: x.get("training_load") or 0)["primary_benefit"] if day_acts else None
        week_items.append((f"{WD[dd.weekday()]} {dd.day}", ctx.load_on(dd), benefit_color(main)))
    week = (f'<section class="pnl c7"><div class="ph"><span>Woche</span><span>7 Tage · Status {esc(ts.get("status") or "–")}</span></div>'
            f'{bars_svg(week_items)}<p class="say" style="margin-top:10px">{esc(a.get("week") or "")}</p>'
            f'<p class="sub" style="margin:18px 0 10px">4-WOCHEN-LASTVERTEILUNG</p>{focus_rows(ts.get("load_focus_4_weeks"))}</section>')
    tomorrow = ctx.plan_on(d + timedelta(days=1))
    if tomorrow:
        name = (ctx.sessions.get(tomorrow.get("session") or "") or {}).get("name")
        tomorrow_text = " · ".join(x for x in (KIND_DE.get(tomorrow.get("kind"), tomorrow.get("kind") or ""), name,
                                                dur(tomorrow["duration_min"]) if tomorrow.get("duration_min") else "") if x)
    bedtime = a.get("bedtime")
    outlook = (f'<section class="pnl c5"><div class="ph"><span>Ausblick</span><span>morgen</span></div>'
               f'<p class="summary" style="margin-top:0">{esc(a.get("outlook") or "")}</p>'
               + (f'<div class="kv"><div><span>Ins Bett um</span><b style="font-size:30px;color:var(--arc)">{esc(bedtime)}</b></div>'
                  f'<div><span>Schlafbedarf</span><b>{dur((r.get("sleep") or {}).get("need_min"))}</b></div></div>' if bedtime else "")
               + (f'<p class="ev"><b>Morgen</b>{esc(tomorrow_text)}</p>' if tomorrow else "")
               + f'<p class="sub" style="margin:18px 0 6px">BELASTUNGSVERHÄLTNIS</p><div style="max-width:300px">{ratio_gauge(ts.get("load_ratio"))}</div></section>')
    preview = preview_panel(ctx, ctx.plan_from(d + timedelta(days=1)), None, "c12",
                            "Vorschau veraltet – für die nächsten Tage steht noch nichts im Plan.")

    body = (topbar("Daily Wrap-Up", ctx) + hero + f'<section class="tiles">{tiles}</section>'
            + f'<div class="grid">{timeline}{"".join(cards)}{week}{outlook}{preview}</div>' + foot(ctx))
    return page("Daily Wrap-Up", body)


# ------------------------------------------------------------------------- main


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["wait-sync", "context", "morning", "wrapup"])
    parser.add_argument("kind", nargs="?", choices=["morning", "wrapup"], help="for 'context'")
    parser.add_argument("--analysis", help="analysis JSON written by Claude")
    parser.add_argument("--out", help="output HTML file")
    parser.add_argument("--date", help="YYYY-MM-DD, default today in the time zone of dashboard.json")
    parser.add_argument("--schedule", action="store_true",
                        help="morning: also write scheduled/<date>.json for the Garmin calendar upload")
    parser.add_argument("--request", action="store_true",
                        help="wait-sync: first ask GitHub for a fresh Garmin sync (cloud routines on a claude/ branch)")
    parser.add_argument("--max-age-min", type=int, default=30, help="wait-sync: data counts as fresh up to this age")
    parser.add_argument("--timeout-min", type=int, default=8, help="wait-sync: give up after this many minutes")
    args = parser.parse_args()
    if args.command == "wait-sync":
        if not args.request:
            return wait_for_sync(args.max_age_min, args.timeout_min)
        requested = datetime.now(TZ)
        if not request_sync():
            print("Could not request a Garmin sync; continuing with the data that is there.")
            subprocess.run(["git", "pull", "-q", "--ff-only", "origin", "main"], cwd=ROOT, check=False)
            return wait_for_sync(args.max_age_min, 0)
        print("Garmin sync requested; waiting for it ...", flush=True)
        code = wait_for_requested_sync(requested, args.timeout_min, remote_last_sync)
        subprocess.run(["git", "merge", "-q", "--ff-only", "origin/main"], cwd=ROOT, check=False)
        return code
    ctx = Ctx(date.fromisoformat(args.date) if args.date else None)

    if args.command == "context":
        print(json.dumps(context(ctx, args.kind or "morning"), ensure_ascii=False, indent=1, default=str))
        return 0
    if not args.analysis or not args.out:
        parser.error("--analysis and --out are required")
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    if args.command == "morning":
        scheduled = write_schedule(ctx, analysis) if args.schedule else None
        html_text = morning(ctx, analysis, scheduled=scheduled is not None)
        if scheduled:
            print(f"Workout for the Garmin calendar: {scheduled.relative_to(ctx.root).as_posix()}")
    else:
        html_text = wrapup(ctx, analysis)
    Path(args.out).write_text(html_text, encoding="utf-8")
    print(f"Wrote {args.out} ({len(html_text) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
