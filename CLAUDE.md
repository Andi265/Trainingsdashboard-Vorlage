# Trainingsdashboard

Personal training and health data of one athlete, synced read-only from Garmin Connect, plus a personal trainer that plans the
training. `dashboard.json` holds the personal settings: the name used on the pages, the time zone, the fixed links of
the two pages, whether workouts may go into the Garmin calendar (`calendar_upload`) and whether the routines send a
phone notification (`push_notifications`); `python3 settings.py` prints them.
Replies to the user are in German, in simple language.

## Data
- `data/data.json`: the main source. Keys: `last_sync`, `units`, `athlete` (cycling FTP, HR zones), `devices`,
  `days` (one record per date: sleep, hrv, resting_hr, body_battery, stress, steps, energy, training_readiness,
  training_status, and for the last 14 days `curves` with intraday series), `activities` (newest first).
- `data/wellness/YYYY-MM-DD.md`: one plain-English note per day. The sleep, HRV and morning readiness of a date
  belong to the night that ended on that morning.
- `data/activities/*.md`: one note per workout.
- A day with `day_in_progress: true` is today and still incomplete.
- Activities with `overlaps_with` are probably one session recorded on two devices; count their load only once.
- The `data/` folder appears with the first sync.

## Briefing pages and training
- `briefing.py` renders both pages in a fixed HUD design from `data/data.json` plus a small analysis JSON that
  Claude writes (`python3 briefing.py context morning|wrapup` prints the facts first). Do not hand-edit its HTML.
- `workouts.py` turns a workout spec into a ZIP with `.fit` (Garmin) and `.zwo` (Zwift); the morning page offers it
  through the Artifact `downloads` capability.
- `training/methodology.md` (evidence-based rules) and `training/sessions.json` (workout library for cycling, running,
  swimming, strength and brick sessions; cycling power in % FTP).
- Standard library only, so the routines run them without installing anything.

## Personal trainer
- `training/profile.json`: the athlete's settings (sports, goal incl. distance and elevation, time budget per weekday,
  fixed days for long sessions, fixed or dynamic rest days, strength training only after explicit confirmation,
  thresholds, constraints, rest-day thresholds). Until it is set up (`setup_done: false`) the default applies:
  cycling, general fitness, dynamic rest days, no strength.
- `training/season.json`: the season plan in phases (base, build, specific, taper, race, recovery, ...).
- `training/schedule.json`: the rolling preview of the next 7-10 days (no fixed 7-day week); the wrap-up rewrites it
  every evening, the morning briefing only changes today.
- `trainer.py` (`show`, `check`, `write-profile|write-season|write-schedule <file>`, `set-day <date> ...`, `--root`)
  checks every file against the fixed rules before saving; never bypass it. `trainer.recovery_assessment` weighs all
  recovery signals for dynamic rest days (`briefing.py context` returns it as `recovery`).
- Settings are changed only in chat through the project skill `.claude/skills/trainer-einstellungen/` ("Training
  einrichten", "Ziel ändern", "Ruhetage ändern", "Krafttraining an/aus", "Einstellungen anzeigen"): one question per
  message, summary, confirmation, then write, check and save (locally on main; in a cloud session on the own
  `claude/...` branch, which the results workflow copies to main).

## How it is updated
There is no fixed sync schedule. Each routine asks for a fresh sync at its start: `briefing.py wait-sync --request`
pushes an empty commit whose message starts with `[data-sync]` to the routine's own `claude/...` branch;
`.github/workflows/data-sync.yml` runs on it, reads Garmin Connect (read-only) with `sync.py --days auto`
(every day since the last sync, at least 3, at most 30), commits to main and deletes the request branch. The routine
waits until that sync is on main (usually 2-4 min, at most 8). The sync can also be started by hand in GitHub Actions.
The Garmin login token is stored encrypted in `vault/`; its key is the repository secret `VAULT_KEY`.

## Garmin calendar upload (the one write exception, only with the user's consent)
- Only if the user agreed during setup (`calendar_upload: true` in `dashboard.json`). Otherwise `briefing.py` writes no
  workout file and `calendar_upload.py` sends nothing.
- `briefing.py morning --schedule` writes `scheduled/<date>.json` for cycling and strength sessions (running, swimming
  and brick sessions are not uploaded yet); the morning routine pushes it to its own `claude/...` branch.
  `.github/workflows/routine-results.yml` copies it onto main, runs `calendar_upload.py` and deletes the branch.
- `calendar_upload.py` may only create a workout and schedule it (POST /workout-service/workout and
  /workout-service/schedule/<id>); every other write is blocked. Workouts are named "[HUD] <title>". It never deletes:
  the user cleans up old "[HUD]" workouts.

## Journal (shared memory of both routines)
- `journal.md` is one continuous feed: "Stand", "Offene Punkte", then the "Verlauf" with one entry per routine run
  (templates at the top). Both routines read it completely first and append one entry at the end; old entries are
  never rewritten.
- Cloud routines can only push to their own `claude/...` branch. They push `journal.md`, `training/schedule.json`
  (the wrap-up also `training/season.json`, the morning routine its `scheduled/<date>.json`) there;
  `.github/workflows/routine-results.yml` copies only the files the branch changed (journal, scheduled/, the three
  training files) onto main and deletes the branch, so the next routine reads the latest state from main.
- If `push_notifications` is on, both routines end with a `PushNotification` call (`<routine_summary>` tags, link +
  key values); that is what sends the phone notification.

## Rules
- Apart from the workout upload above, never write anything to Garmin Connect. `sync.py` blocks every non-GET
  request; keep it that way.
- Never print, decrypt or commit the Garmin token or the vault key. Never ask for the Garmin password in chat; it is
  only typed into the terminal running `login.py`.
- Routines commit only `journal.md`, `training/schedule.json`, in the morning `scheduled/<date>.json` and in the
  evening, if the season plan needs extending, `training/season.json`. Only the settings dialog changes
  `training/profile.json`; only the setup changes `dashboard.json`.

## Prompts
`prompts/morning-health-briefing.md` and `prompts/daily-wrap-up.md` (the wrap-up also rewrites the preview). The days
and times of the routines are chosen by the user during setup; each routine first requests a fresh sync via
`briefing.py wait-sync --request`, so manual runs get current data too. Each publishes to one fixed, pinned artifact
that is replaced daily; the links are in `dashboard.json` (`links.morning_briefing` with the `downloads` capability,
`links.daily_wrapup`).
