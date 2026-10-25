# Workouts for the Garmin calendar

Only used if the user agreed to the Garmin calendar upload (`calendar_upload: true` in `dashboard.json`).
The Morning Briefing then writes one file per day here (`YYYY-MM-DD.json`) for a cycling or strength session.
The GitHub workflow `routine-results.yml` uploads it to Garmin Connect as "[HUD] <title>", puts it into the calendar
for that day and records the result under `upload` in the file.
