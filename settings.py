"""Personal settings of this dashboard, kept in dashboard.json: the name used on the pages, the time zone, the
fixed links of the two pages, whether workouts may be put into the Garmin calendar (the only write to Garmin, off
until the user agrees) and whether the routines send a phone notification. Filled in during setup.
Standard library only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"name": "", "timezone": "Europe/Berlin", "links": {"morning_briefing": "", "daily_wrapup": ""},
            "calendar_upload": False, "push_notifications": True}


def load(root: Path = ROOT) -> dict:
    """dashboard.json merged over the defaults; a missing or broken file gives the defaults."""
    result = copy.deepcopy(DEFAULTS)
    try:
        stored = json.loads((root / "dashboard.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def timezone(root: Path = ROOT) -> ZoneInfo:
    return ZoneInfo(load(root).get("timezone") or DEFAULTS["timezone"])


if __name__ == "__main__":
    print(json.dumps(load(), ensure_ascii=False, indent=1))
