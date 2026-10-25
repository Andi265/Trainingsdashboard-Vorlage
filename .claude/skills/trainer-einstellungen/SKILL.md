---
name: trainer-einstellungen
description: Persönlichen Trainer einrichten oder ändern und die Einstellungen anzeigen. Auslöser sind Sätze wie „Training einrichten“, „Ziel ändern“, „Wettkampf eintragen“, „Ruhetage ändern“, „lange Tage ändern“, „Zeitbudget ändern“, „Krafttraining an“, „Krafttraining aus“, „Einstellungen anzeigen“ oder „Trainingsplan neu erstellen“. Schreibt training/profile.json, training/season.json und training/schedule.json.
---

# Trainer-Einstellungen

Der Nutzer richtet hier seinen persönlichen Trainer ein oder ändert ihn. Sein Name steht in `dashboard.json`
(`name`). Er muss kein Programmierer sein: Sprich Deutsch, in einfacher Sprache, per Du. Er fasst keine Dateien an;
du erledigst alles.

Befehle: `python3 trainer.py …` (unter Windows `py -3.13 trainer.py …`). Alles liegt im Repository-Ordner.

## Dialogregeln

- **Eine Frage pro Nachricht.** Nie mehrere Fragen bündeln.
- Bei jeder Frage den **aktuellen Wert zeigen**: „Bisher: …. Soll das so bleiben?“
- Bei einer Änderung **nur die betroffenen Abschnitte** durchgehen (Tabelle unten).
- Am Ende eine **Zusammenfassung zum Bestätigen**. Erst nach einem klaren Ja werden Dateien geschrieben.
- **Krafttraining** wird nur eingeschaltet nach einem ausdrücklichen Ja auf eine eigene Frage:
  „Möchtest du, dass ich Krafttraining in deinen Plan einbaue? Ja oder nein?“ Dann `strength.enabled: true` und
  `strength.confirmed_at` = heutiges Datum. Ohne dieses Ja bleibt es aus.
- Fachbegriffe kurz erklären (z. B. „FTP = die Leistung, die du etwa eine Stunde halten kannst“).

## Ablauf

1. `git pull` (damit du den neuesten Stand von `main` hast), dann `python3 trainer.py show` und das Ergebnis lesen.
   Außerdem lesen: `training/methodology.md`, die IDs in `training/sessions.json`, aus `data/data.json` den Block
   `athlete` (FTP, Pulszonen) und die letzten 7 Tage (für die erste Vorschau).
2. **„Einstellungen anzeigen“:** die Ausgabe von `show` in einfachen Worten wiedergeben, dazu die aktuelle
   Saisonphase und die nächsten Tage der Vorschau. Nichts ändern. Fertig.
3. Fragen stellen (Reihenfolge unten), eine pro Nachricht.
4. Zusammenfassung zeigen und bestätigen lassen.
5. Profil als JSON in eine Datei außerhalb des Repositorys schreiben (Temp-Ordner), dann
   `python3 trainer.py write-profile <datei>`. Meldet das Skript Fehler, korrigieren und erneut schreiben; die Prüfung
   nie umgehen.
6. Wenn sich Ziel, Sportarten, Krafttraining oder Wettkämpfe geändert haben (oder beim ersten Einrichten):
   Saisonplan **ab heute neu** nach `training/methodology.md` Abschnitt 5, 8, 12 und 13 erstellen →
   `python3 trainer.py write-season <datei>`.
7. Vorschau für die nächsten 7–10 Tage ab heute nach Abschnitt 6 und 7 erstellen (bisherige Tage mit Status `done`
   übernehmen) → `python3 trainer.py write-schedule <datei>`.
8. `python3 trainer.py check` muss „Alles in Ordnung“ melden.
9. Kurzüberblick zeigen: die neuen Einstellungen in 3–5 Zeilen, die Saisonphasen (Name, Zeitraum) und die
   Vorschau als kleine Liste (Tag, Einheit, Dauer, Ruhetag voraussichtlich).
10. Speichern (unten) und dem Nutzer sagen, ab wann es gilt: Das nächste Morning Briefing nutzt die neuen Einstellungen.

## Fragen beim ersten Einrichten

1. **Sportarten:** Radfahren, Laufen, Schwimmen, Krafttraining (nur über Frage 8), oder Triathlon/Duathlon
   (`multisport`; die Teilsportarten werden automatisch gesetzt: Triathlon = Schwimmen, Rad, Laufen; Duathlon =
   Laufen, Rad).
2. **Art des Ziels:** ein Wettkampf, eine Disziplin verbessern oder allgemeine Fitness.
3. **Details zum Ziel** (je Angabe eine eigene Frage):
   - Wettkampf: Name, Datum, Distanz, **Höhenmeter**, längster Anstieg (Länge und Höhenmeter, falls bekannt),
     Priorität (A = Saisonhöhepunkt, B = wichtig, C = Trainingswettkampf), Zielzeit (optional).
   - Disziplin: Sportart und Schwerpunkt (Rad: Gran Fondo, Zeitfahren, Bergfahren; Lauf: 5 km, 10 km, Halbmarathon,
     Marathon, Trail), typische Distanz und **Höhenmeter** der Zielstrecken.
   - Fitness: welche Fähigkeiten (VO2max, anaerob, Grundlage).
4. **Weitere Wettkämpfe** (optional): dieselben Angaben, Priorität B oder C.
5. **Zeitbudget je Wochentag** in Stunden (Mo–So).
6. **Lange Einheiten:** an welchen Tagen, welche Sportart und wie lange höchstens. Der Nutzer legt die Tage fest;
   nie selbst bestimmen.
7. **Ruhetage:** feste Tage oder dynamisch (der Trainer schlägt sie nach Erholung vor). Erkläre „dynamisch“ kurz:
   Nach einer harten Einheit kommt meist ein lockerer Tag; ein Ruhetag kommt, wenn mehrere Erholungswerte über Tage
   auf Ermüdung zeigen. Mindestzahl Ruhetage pro Trainingsabschnitt (Standard 1).
8. **Krafttraining gewünscht?** Eigene Bestätigungsfrage (siehe Dialogregeln). Bei Ja nacheinander: Ort (Studio,
   zu Hause, nur Körpergewicht), Ausrüstung, Erfahrung (keine, etwas, viel), wie oft pro Abschnitt
   höchstens (1–3; der Trainer plant je nach Phase: Gewöhnung 2×, Maximalkraft in Grundlagenphasen bis 3×, Erhalt in
   harten Blöcken 1–2×, Entlastung 1×, und nie am Tag vor einer Schlüssel- oder langen Einheit).
9. **Leistungswerte:** Garmin-Werte zeigen (FTP, Max-Puls) und bestätigen lassen. Fehlende Werte für gewählte
   Sportarten erfragen (Laufschwelle als Pace pro km oder Puls, Schwimm-CSS pro 100 m) oder einen Test vorschlagen
   (siehe Methodik Abschnitt 9 und 10).
10. **Einschränkungen und Vorlieben:** Verletzungen, Indoor/Zwift ja/nein, Räder mit Powermeter, Bahnlänge im
    Schwimmbad, Alter (optional).
11. **Zusammenfassung** → Bestätigung → Saisonplan und Vorschau erstellen und kurz zeigen.

## Welche Fragen bei einer Änderung

| Der Nutzer sagt … | Fragen | danach neu |
|---|---|---|
| „Ziel ändern“, „Wettkampf eintragen“ | 2, 3, 4 | Saisonplan und Vorschau |
| „Sportarten ändern“ | 1, dann 9 für neue Sportarten | Saisonplan und Vorschau |
| „Zeitbudget ändern“ | 5 | Vorschau |
| „lange Tage ändern“ | 6 | Vorschau |
| „Ruhetage ändern“ | 7 | Vorschau |
| „Krafttraining an“ / „aus“ | 8 | Saisonplan (Kraftphasen) und Vorschau |
| „Leistungswerte ändern“ | 9 | nichts (gilt ab dem nächsten Workout) |
| „Einschränkungen ändern“ | 10 | Vorschau |

Danach immer Zusammenfassung → Bestätigung → schreiben → prüfen → speichern.

## Format `training/profile.json`

Alle Felder bleiben erhalten; nur Geändertes ersetzen. `updated` und `setup_done: true` setzen.

```json
{
 "version": 1, "updated": "2026-10-25", "setup_done": true,
 "sports": ["cycling"], "multisport": null,
 "goal": {"type": "event",
          "event": {"name": "Ötztaler Radmarathon", "date": "2027-08-29", "sport": "cycling",
                    "distance_km": 227, "elevation_m": 5500,
                    "longest_climb": {"km": 28.7, "elevation_m": 1750},
                    "priority": "A", "target_time": "10:30", "notes": ""}},
 "secondary_events": [{"name": "…", "date": "2027-06-06", "sport": "cycling", "distance_km": 160,
                       "elevation_m": 3000, "priority": "B"}],
 "availability": {"hours": {"mon": 1.5, "tue": 1.5, "wed": 1.5, "thu": 1.5, "fri": 1.5, "sat": 4, "sun": 3},
                  "long_days": [{"day": "sat", "sport": "cycling", "max_h": 4}],
                  "rest_days": {"mode": "dynamic", "days": [], "min_per_cycle": 1}},
 "strength": {"enabled": false, "confirmed_at": null, "location": null, "equipment": [], "experience": null,
              "per_cycle": 0},
 "thresholds": {"cycling_ftp_w": {"source": "garmin"}, "running_threshold_pace": null, "running_lthr": null,
                "swim_css_per_100m": null, "max_hr": {"source": "garmin"}},
 "constraints": {"injuries": "", "indoor_zwift": true, "power_meter_bikes": [], "pool_length_m": 25, "age": null},
 "rest_rules": {"readiness_low": 50, "recovery_time_h": 24, "load_ratio": 1.3, "sleep_score": 70,
                "rhr_delta": 3, "rhr_alarm": 5, "days_in_row": 6, "signals_for_rest": 3}
}
```

- Sportarten: `cycling`, `running`, `swimming`, `strength` (`strength` nur mit bestätigtem Krafttraining).
- Wochentage: `mon` … `sun`. Datum immer `JJJJ-MM-TT`.
- Ziel `discipline`: `{"sport": "cycling", "focus": "climbing", "distance_km": 120, "elevation_m": 2500}`; Schwerpunkte
  Rad `gran_fondo`, `time_trial`, `climbing`; Lauf `5k`, `10k`, `half`, `marathon`, `trail`.
- Ziel `fitness`: `{"focus": ["vo2max", "anaerobic", "base"]}`.
- Triathlon: `"multisport": "triathlon"`, `distance_km` als Objekt, z. B. `{"swimming": 1.5, "cycling": 40, "running": 10}`.
- Eigene Leistungswerte als Zahl oder Text, z. B. `"running_threshold_pace": "4:45"` (min/km),
  `"swim_css_per_100m": "1:50"`; Garmin-Werte bleiben `{"source": "garmin"}`.
- `rest_rules` nur ändern, wenn der Nutzer es ausdrücklich will oder nach Wochen Daten zeigen, dass ein Grenzwert nicht
  zu ihm passt (dann im Journal vermerken).

## Format `training/season.json`

```json
{"created": "2026-10-25", "about": "Saisonplan für …",
 "phases": [{"name": "Grundlage 1", "focus": "base", "start": "2026-10-26", "end": "2026-11-22",
             "key_sessions": ["base_long", "base_sst_3x15"], "key_per_cycle": [2, 2, 3, 2],
             "strength_phase": "off", "intensity_target": {"low": 85, "mid": 10, "high": 5},
             "notes": "Worauf es in der Phase ankommt; welche Einheiten an den anderen Tagen."}]}
```

- `focus`: `base`, `build`, `specific`, `taper`, `race`, `recovery`, `vo2max`, `anaerobic`, `threshold`, `climbing`,
  `tempo`. `strength_phase`: `off`, `adaptation`, `max`, `maintenance`.
- Phasen lückenlos von heute bis mindestens 3 Wochen nach dem Wettkampf (bei Fitness- und Disziplinzielen
  mindestens 12 Wochen voraus). Wettkampfziel: Tapering-Phase (A: 7–14 Tage, B/C: 2–3 Tage) endet am Vortag; eine
  `race`-Phase enthält den Wettkampftag; danach `recovery`.
- `key_sessions` nur IDs aus `training/sessions.json`, passend zu Sportart und Ziel.

## Format `training/schedule.json`

```json
{"created": "2026-10-25",
 "cycle": {"start": "2026-10-26", "end": "2026-11-03", "label": "Abschnitt 9 Tage: …"},
 "days": [{"date": "2026-10-26", "sport": "cycling", "session": "base_z2_60", "kind": "easy",
           "duration_min": 60, "reason": "Ein kurzer Satz, warum.", "status": "planned"},
          {"date": "2026-10-29", "sport": "rest", "session": null, "kind": "rest_expected",
           "duration_min": 0, "reason": "…", "status": "planned"}]}
```

- `sport`: Sportart, `brick` (Koppeltraining) oder `rest`. `kind`: `rest`, `rest_expected`, `easy`, `normal`, `key`,
  `long`, `strength`. `status`: `planned`, `done`, `changed`.
- Feste Ruhetage als `rest`, dynamische als `rest_expected`.

## Speichern

- **Lokale Sitzung (Desktop-App):** auf `main` committen und pushen:
  `git add training/profile.json training/season.json training/schedule.json`,
  `git commit -m "trainer: Einstellungen geändert (…)"`, `git push`.
- **Cloud-Sitzung (claude.ai/code, z. B. vom Handy):** auf den eigenen `claude/…`-Zweig committen und
  `git push -u origin HEAD`. Der Workflow „Routine results“ übernimmt die drei Dateien nach `main` und löscht den
  Zweig. Kurz warten und mit `git fetch origin main` und `git show origin/main:training/profile.json` prüfen, dass
  die Änderung angekommen ist.
- Nur diese drei Dateien committen. Nie etwas nach Garmin Connect schreiben; nie Token oder Schlüssel ausgeben.
