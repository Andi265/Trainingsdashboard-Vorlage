"""Turn a workout spec into files for Garmin (.fit) and Zwift (.zwo), bundled as one ZIP.

Spec (JSON), power targets in % of FTP:
{
  "name": "VO2max 5x4",
  "steps": [
    {"kind": "warmup", "min": 15, "pct": [55, 75]},
    {"repeat": 5, "steps": [
      {"kind": "interval", "min": 4, "pct": [106, 115], "label": "VO2max"},
      {"kind": "recovery", "min": 3, "pct": [45, 55]}
    ]},
    {"kind": "cooldown", "min": 10, "pct": [45, 60]}
  ]
}
kind: warmup | interval | steady | recovery | cooldown. Durations: "min" and/or "sec".
A repeat may hold another repeat (e.g. 3 sets of 13 x 30/15) and a "between" step for the rest
between sets; such outer loops are written out step by step because devices only handle one
repeat level.

Standard library only. Usage for a quick test:
  python workouts.py spec.json --ftp 250 --out folder
"""

from __future__ import annotations

import io
import json
import random
import re
import struct
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

KIND_NAMES = {"warmup": "Einfahren", "interval": "Intervall", "steady": "Gleichmäßig",
              "recovery": "Locker", "cooldown": "Ausfahren"}


@dataclass
class Step:
    kind: str
    seconds: int
    lo: int  # % FTP
    hi: int
    label: str

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2


@dataclass
class Repeat:
    count: int
    steps: list[Step]


def make_step(raw: dict) -> Step:
    seconds = round(float(raw.get("min", 0)) * 60 + float(raw.get("sec", 0)))
    lo, hi = (raw.get("pct") or [50, 60])[:2]
    kind = raw.get("kind", "steady")
    if kind not in KIND_NAMES:
        kind = "steady"
    if seconds <= 0:
        raise ValueError(f"Step without duration: {raw}")
    return Step(kind, seconds, int(lo), int(hi), str(raw.get("label") or KIND_NAMES[kind]))


def normalize(raw_steps: list[dict]) -> list[Step | Repeat]:
    out: list[Step | Repeat] = []
    for raw in raw_steps:
        if "repeat" not in raw:
            out.append(make_step(raw))
            continue
        count = max(1, int(raw["repeat"]))
        inner = normalize(raw.get("steps") or [])
        between = make_step(raw["between"]) if raw.get("between") else None
        if between or any(isinstance(s, Repeat) for s in inner):
            for i in range(count):
                out.extend(inner)
                if between and i < count - 1:
                    out.append(between)
        else:
            out.append(Repeat(count, [s for s in inner if isinstance(s, Step)]))
    return out


def flat_steps(items: list[Step | Repeat]) -> list[Step]:
    """Every step in the order it is ridden."""
    out: list[Step] = []
    for item in items:
        out.extend(item.steps * item.count if isinstance(item, Repeat) else [item])
    return out


def total_seconds(items: list[Step | Repeat]) -> int:
    return sum(s.seconds for s in flat_steps(items))


def estimated_tss(items: list[Step | Repeat]) -> int:
    return round(sum(s.seconds / 3600 * (s.mid / 100) ** 2 * 100 for s in flat_steps(items)))


def duration_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} min" if not rest else f"{minutes}:{rest:02d} min"


def describe(spec: dict) -> list[tuple[str, str, str, str]]:
    """Text rows (repeat, section, amount, target) for any sport, e.g. ("4×", "Kniebeuge", "5 Wdh.", "RPE 8 · Pause 3:00")."""
    sport = spec.get("sport", "cycling")
    if sport == "brick":
        prefix = {"cycling": "Rad: ", "running": "Lauf: ", "swimming": "Schwimmen: "}
        return [(rep, prefix.get(part.get("sport", "cycling"), "") + label, amount, target)
                for part in spec.get("parts") or [] for rep, label, amount, target in describe(part)]
    if sport == "strength":
        rows = []
        for e in spec.get("exercises") or []:
            rest = e.get("rest_sec")
            target = " · ".join(x for x in (e.get("load") or "", f"Pause {mmss_text(rest)}" if rest else "") if x)
            rows.append((f"{e['sets']}×", e.get("label") or e["name"], f"{e['reps']} Wdh.", target))
        return rows
    if sport == "cycling":
        rows = []
        for item in normalize(spec.get("steps") or []):
            steps = item.steps if isinstance(item, Repeat) else [item]
            for i, s in enumerate(steps):
                marker = f"{item.count}×" if isinstance(item, Repeat) and i == 0 else ""
                rows.append((marker, s.label, duration_text(s.seconds), f"{s.lo}–{s.hi} % FTP"))
        return rows

    def row(step: dict, marker: str) -> tuple[str, str, str, str]:
        if "m" in step:
            amount = f"{step['m']} m"
        elif "km" in step:
            amount = f"{step['km']} km"
        else:
            amount = duration_text(round(float(step.get("min", 0)) * 60 + float(step.get("sec", 0))))
        target = step.get("target") or ""
        if step.get("rest_sec"):
            target = " · ".join(x for x in (target, f"Pause {mmss_text(step['rest_sec'])}") if x)
        return marker, step.get("label") or KIND_NAMES.get(step.get("kind"), "Abschnitt"), amount, target

    rows = []
    for step in spec.get("steps") or []:
        if "repeat" in step:
            rows += [row(inner, f"{step['repeat']}×" if i == 0 else "") for i, inner in enumerate(step.get("steps") or [])]
        else:
            rows.append(row(step, ""))
    return rows


def mmss_text(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def watts(pct: float, ftp: int) -> int:
    return int(round(pct * ftp / 100 / 5) * 5)


def hr_range(step: Step, zones: dict | None) -> tuple[int, int] | None:
    """Map the step's power intensity to the matching Garmin heart-rate zone."""
    if not zones:
        return None
    floors = [zones.get(f"zone{i}Floor") for i in range(1, 6)]
    top = zones.get("maxHeartRateUsed")
    if None in floors or not top:
        return None
    zone = 1 if step.mid < 56 else 2 if step.mid < 76 else 3 if step.mid < 91 else 4 if step.mid < 106 else 5
    upper = floors[zone] - 1 if zone < 5 else top
    return floors[zone - 1], upper


# --------------------------------------------------------------------------- FIT

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)
ENUM, UINT16, UINT32, UINT32Z, STRING = 0x00, 0x84, 0x86, 0x8C, 0x07
INTENSITY = {"warmup": 2, "cooldown": 3, "recovery": 4, "interval": 0, "steady": 0}


def fit_crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def fit_value(base: int, size: int, value) -> bytes:
    if base == STRING:
        raw = (value or "").encode("utf-8")[: size - 1].decode("utf-8", "ignore").encode("utf-8")
        return raw + b"\0" * (size - len(raw))
    fmt, invalid = {ENUM: ("<B", 0xFF), UINT16: ("<H", 0xFFFF), UINT32: ("<I", 0xFFFFFFFF), UINT32Z: ("<I", 0)}[base]
    return struct.pack(fmt, invalid if value is None else value)


class FitWriter:
    def __init__(self) -> None:
        self.body = bytearray()

    def message(self, local: int, global_num: int, fields: list[tuple[int, int, int]], rows: list[list]) -> None:
        self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields))
        for num, base, size in fields:
            self.body += struct.pack("<BBB", num, size, base)
        for row in rows:
            self.body.append(local)
            for (num, base, size), value in zip(fields, row):
                self.body += fit_value(base, size, value)

    def finish(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", fit_crc(header))
        content = header + bytes(self.body)
        return content + struct.pack("<H", fit_crc(content))


def to_fit(name: str, items: list[Step | Repeat], ftp: int, zones: dict | None) -> bytes:
    rows: list[list] = []

    def add(step: Step) -> None:
        hr = hr_range(step, zones)
        note = f"{watts(step.lo, ftp)}-{watts(step.hi, ftp)} W" + (f", Puls {hr[0]}-{hr[1]}" if hr else "")
        rows.append([len(rows), step.label, 0, step.seconds * 1000, 4, 0,
                     watts(step.lo, ftp) + 1000, watts(step.hi, ftp) + 1000, INTENSITY[step.kind], note])

    for item in items:
        if isinstance(item, Repeat):
            first = len(rows)
            for step in item.steps:
                add(step)
            rows.append([len(rows), "", 6, first, None, item.count, None, None, None, ""])
        else:
            add(item)

    created = int((datetime.now(timezone.utc) - FIT_EPOCH).total_seconds())
    fit = FitWriter()
    fit.message(0, 0, [(0, ENUM, 1), (1, UINT16, 2), (2, UINT16, 2), (3, UINT32Z, 4), (4, UINT32, 4)],
                [[5, 255, 0, random.randint(1, 2**31), created]])
    fit.message(1, 26, [(4, ENUM, 1), (6, UINT16, 2), (8, STRING, 32)], [[2, len(rows), name]])
    fit.message(2, 27, [(254, UINT16, 2), (0, STRING, 24), (1, ENUM, 1), (2, UINT32, 4), (3, ENUM, 1),
                        (4, UINT32, 4), (5, UINT32, 4), (6, UINT32, 4), (7, ENUM, 1), (8, STRING, 48)], rows)
    return fit.finish()


# --------------------------------------------------------------------------- ZWO


def to_zwo(name: str, description: str, items: list[Step | Repeat]) -> str:
    lines = []
    for item in items:
        if isinstance(item, Repeat) and len(item.steps) == 2:
            on, off = item.steps
            lines.append(f'<IntervalsT Repeat="{item.count}" OnDuration="{on.seconds}" OffDuration="{off.seconds}" '
                         f'OnPower="{on.mid / 100:.2f}" OffPower="{off.mid / 100:.2f}"/>')
            continue
        for step in flat_steps([item]):
            if step.kind == "warmup":
                lines.append(f'<Warmup Duration="{step.seconds}" PowerLow="{step.lo / 100:.2f}" PowerHigh="{step.hi / 100:.2f}"/>')
            elif step.kind == "cooldown":
                lines.append(f'<Cooldown Duration="{step.seconds}" PowerLow="{step.hi / 100:.2f}" PowerHigh="{step.lo / 100:.2f}"/>')
            else:
                lines.append(f'<SteadyState Duration="{step.seconds}" Power="{step.mid / 100:.2f}"/>')
    body = "\n    ".join(lines)
    return (f"<workout_file>\n  <author>Trainingsdashboard</author>\n  <name>{escape(name)}</name>\n"
            f"  <description>{escape(description)}</description>\n  <sportType>bike</sportType>\n"
            f"  <workout>\n    {body}\n  </workout>\n</workout_file>\n")


# --------------------------------------------------------------------------- bundle

README = """So kommt das Workout auf dein Gerät

Garmin-Radcomputer (Edge) oder -Uhr:
1. Gerät per USB-Kabel mit dem PC verbinden.
2. Die .fit-Datei in den Ordner  Garmin\\NewFiles  auf dem Gerät kopieren.
3. Gerät trennen. Das Workout steht dann unter  Training > Workouts.

Zwift:
1. Die .zwo-Datei in den Ordner  Dokumente\\Zwift\\Workouts\\<deine Zwift-Nummer>  kopieren.
2. In Zwift unter  Workouts > Custom Workouts  auswählen.

Die Wattwerte sind aus deiner FTP von {ftp} W berechnet.
"""


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:40] or "Workout"


def build_bundle(spec: dict, ftp: int, zones: dict | None, day: str) -> tuple[str, bytes, list[Step | Repeat]]:
    """Return (zip filename, zip bytes, normalized steps)."""
    name = str(spec.get("name") or "Workout")[:31]
    items = normalize(spec.get("steps") or [])
    if not items:
        raise ValueError("Workout spec has no steps")
    base = f"{day}_{slug(name)}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}.fit", to_fit(name, items, ftp, zones))
        zf.writestr(f"{base}.zwo", to_zwo(name, str(spec.get("description") or ""), items))
        zf.writestr("ANLEITUNG.txt", README.format(ftp=ftp))
    return f"{base}.zip", buffer.getvalue(), items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build workout files from a spec.")
    parser.add_argument("spec")
    parser.add_argument("--ftp", type=int, required=True)
    parser.add_argument("--out", default=".")
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    filename, data, items = build_bundle(spec, args.ftp, None, datetime.now().strftime("%Y-%m-%d"))
    target = Path(args.out) / filename
    target.write_bytes(data)
    print(f"{target} ({len(data)} bytes, {total_seconds(items) // 60} min, ~{estimated_tss(items)} TSS)")
    sys.exit(0)
