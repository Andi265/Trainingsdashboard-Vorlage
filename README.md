# Trainingsdashboard-Vorlage

Vorlage für ein persönliches Trainingsdashboard mit Trainer, das Claude für dich einrichtet und betreibt. Es liest
deine Daten aus Garmin Connect, nur lesend.

- **Datenabruf:** Schlaf, HRV, Ruhepuls, Body Battery, Stress, Trainingsbereitschaft, Trainings. Jede Routine fordert
  beim Start selbst einen frischen Abruf an (GitHub Actions); verpasste Tage werden nachgeholt.
- **Morning Health Briefing** und **Daily Wrap-Up** als Claude-Routinen, jeweils auf einer festen, angepinnten Seite im
  HUD-Design, auf Wunsch mit Push-Nachricht aufs Handy.
- **Persönlicher Trainer:** Sportarten (Rad, Laufen, Schwimmen, Kraft, Triathlon, Duathlon), Ziel (Wettkampf mit
  Distanz und Höhenmetern, Disziplin oder allgemeine Fitness), Saisonplan in Phasen, rollierende Vorschau über 7–10
  Tage, dynamische Ruhetage aus einer Abwägung aller Erholungssignale, Krafttraining nur nach Zustimmung.
- **Workouts:** Bibliothek mit Rad-, Lauf-, Schwimm-, Kraft- und Koppeleinheiten; Rad-Workouts als `.fit`/`.zwo` zum
  Herunterladen; nur mit deiner Zustimmung Rad- und Krafteinheiten automatisch im Kalender von Garmin Connect.
- **Journal:** gemeinsames Gedächtnis beider Routinen.

## Einrichtung

1. Öffne die Claude-App, wechsle in den **Code**-Tab und starte eine neue Sitzung in einem neuen, leeren Ordner
   (z. B. `Dokumente/Trainingsdashboard`).
2. Kopiere den gesamten Inhalt von [`EINRICHTUNG.md`](EINRICHTUNG.md) in diese Sitzung und schicke ihn ab.
3. Claude führt dich Schritt für Schritt durch alles, mit einer Frage pro Nachricht. Du musst keine Dateien
   anfassen. Dein Garmin-Passwort tippst du nur in ein Terminalfenster, nie in den Chat.

Daraus entsteht dein eigenes, privates Repository. Persönliche Werte (Name, Zeitzone, Links der Seiten, Kalender
ja/nein, Push-Nachrichten ja/nein) stehen danach in `dashboard.json`, die Trainingseinstellungen in
`training/profile.json`.

## Was hier nicht drin ist

Diese Vorlage enthält keine personenbezogenen Daten: keine Trainings- oder Gesundheitsdaten, kein Anmeldetoken, keinen
Journal-Verlauf, kein Trainerprofil, keine Links oder Routinen eines anderen Nutzers. Alles Persönliche entsteht erst
bei deiner Einrichtung in deinem eigenen, privaten Repository.

## Technik

Python (nur Standardbibliothek für Seiten und Trainer; die Bibliotheken `garminconnect` und `cryptography` nur für den
Datenabruf), GitHub Actions, Claude-Code-Routinen. Tests: `python -m unittest discover -s tests`.

## Hinweis

Dies ist kein offizielles Produkt von Garmin und steht in keiner Verbindung zu Garmin. Garmin und Garmin Connect sind
Marken von Garmin Ltd. oder ihren Tochtergesellschaften; sie werden hier nur genannt, um zu beschreiben, mit welchem
Dienst das Dashboard zusammenarbeitet.
