# Einrichtungs-Prompt: Trainingsdashboard

> **So benutzt du diesen Text:** Öffne die Claude-App, wechsle in den **Code**-Tab und starte eine neue Sitzung in
> einem neuen, leeren Ordner (z. B. `Dokumente/Trainingsdashboard`). Kopiere alles ab der Linie unten in diese
> Sitzung und schicke es ab. Claude erledigt den Rest und fragt dich, wenn es etwas von dir braucht.

---

Richte für mich ein persönliches **Trainingsdashboard** ein. Es liest meine Daten aus Garmin Connect (nur lesend),
zeigt jeden Morgen ein **Morning Health Briefing** und jeden Abend einen **Daily Wrap-Up** als feste, angepinnte
Seiten und plant mein Training wie ein persönlicher Trainer.

**Die Vorlage liegt hier:** https://github.com/Andi265/Trainingsdashboard-Vorlage (öffentlich, Vorlage-Repository).
Daraus legst du mein eigenes, **privates** Repository an. Lies nach dem Anlegen zuerst `README.md` und `CLAUDE.md` in
meinem Repository. Dort steht, wie alles zusammenspielt.

## Regeln für dich

- Sprich Deutsch, in einfacher Sprache, per Du. Ich bin kein Programmierer und fasse keine Dateien an: Du führst alle
  Befehle aus und erklärst kurz, was passiert.
- **Eine Frage pro Nachricht.** Zeig bei Einstellungen den vorgeschlagenen Wert und frag, ob er passt.
- **Passwörter nie im Chat.** Mein Garmin-Passwort tippe ich nur in ein Terminalfenster (`login.py`), GitHub melde ich
  im Browser an. Gib Tokens oder Schlüssel nie aus und committe sie nie unverschlüsselt.
- **Nur lesend auf Garmin Connect.** Die einzige Ausnahme ist das Eintragen von Workouts in meinen Kalender, und nur
  wenn ich dem ausdrücklich zustimme (eigene Frage, siehe unten).
- Bevor du etwas mit Außenwirkung tust (Repository anlegen, Seiten veröffentlichen, Routinen anlegen), sag in einem
  Satz, was passiert. Prüfe nach jedem Schritt, ob er geklappt hat, und sag es mir kurz.
- Klappt etwas nicht, such die Ursache, statt es zu umgehen.

## Skills

Nutze diese Skills; sie gehören zur Arbeitsweise dieses Dashboards:

| Skill | Wofür |
|---|---|
| `artifact-design` | vor dem ersten Veröffentlichen der beiden Seiten laden (gehört zum Artifact-Tool) |
| `artifact-capabilities` | bevor die Morning-Seite die Fähigkeit `downloads` bekommt (Download-Knopf für Workouts) |
| `schedule` | um die Routinen anzulegen, zu prüfen und einmal testweise zu starten |
| `trainer-einstellungen` | Projekt-Skill im Repository: „Training einrichten“, „Ziel ändern“, „Ruhetage ändern“, „Krafttraining an/aus“, „Einstellungen anzeigen“ |
| `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:executing-plans`, `superpowers:test-driven-development` | für spätere Änderungen und Erweiterungen am Dashboard: erst klären, was ich will, dann einen Plan schreiben, den ich freigebe, dann umsetzen, jeden Schritt testgetrieben |

Die `superpowers`-Skills kommen aus dem Plugin **superpowers** im offiziellen Plugin-Marktplatz
(`claude-plugins-official`). Ist es nicht aktiv, hilf mir beim Installieren (Plugin-Verwaltung der Claude-App oder im
Terminal `claude plugin install superpowers@claude-plugins-official`) und sag mir, wenn danach eine neue Sitzung nötig
ist. Für die Einrichtung selbst brauchst du es noch nicht.

## Schritt 1: Voraussetzungen prüfen

Frag kurz nach (eine Frage pro Nachricht, nur was du nicht selbst prüfen kannst):
- ein **Garmin-Connect-Konto**, mit dem meine Uhr bzw. mein Radcomputer synchronisiert
- ein **GitHub-Konto** (kostenlos reicht)
- ein **Claude-Abo mit Claude Code und Routinen** (Routinen laufen in der Cloud auf claude.ai/code)

Prüf auf dem PC selbst: `git`, die GitHub-CLI `gh` und **Python ab 3.10** (empfohlen 3.13). Fehlt etwas, schlag die
Installation vor und führe sie nach meinem Ja aus (Windows: `winget`, Mac: `brew`). Melde mich bei GitHub mit
`gh auth login --web` an (ich bestätige im Browser).

## Schritt 2: Meine Einstellungen (je eine Frage)

1. **Name** für die Anrede auf den Seiten
2. **Zeitzone** (schlag die des PCs vor, als IANA-Name, z. B. `Europe/Berlin`)
3. **Morning Health Briefing:** an welchen Tagen und um wie viel Uhr? Werktage und Wochenende dürfen verschiedene Zeiten
   haben. Erkläre: Die Routine holt sich beim Start selbst frische Daten; meine Uhr sollte vorher mit der Garmin-App
   synchronisiert sein.
4. **Daily Wrap-Up:** an welchen Tagen und um wie viel Uhr?
5. **Push-Nachrichten** aufs Handy, wenn eine Routine fertig ist: ja oder nein?
6. **Workouts automatisch in den Kalender von Garmin Connect eintragen:** ja oder nein? Eigene Frage, mit Erklärung:
   Das ist die einzige Stelle, an der etwas zu Garmin geschrieben wird. Es werden nur neue Workouts mit dem Namen
   „[HUD] …“ angelegt und für den Tag eingetragen (Rad und Kraft), nie etwas geändert oder gelöscht; alte „[HUD]“-Workouts
   räume ich selbst auf. Ohne mein ausdrückliches Ja bleibt es aus.
7. **Name meines privaten Repositorys** (Vorschlag: `trainingsdashboard`)
8. **Modell für die Routinen** (schlag das aktuelle Standardmodell vor)

Danach: Zusammenfassung zeigen, mein Ja abwarten.

## Schritt 3: Mein Repository aus der Vorlage

- `gh repo create <mein-github-name>/<repo-name> --private --template Andi265/Trainingsdashboard-Vorlage --clone`, dann
  im geklonten Ordner weiterarbeiten.
- `dashboard.json` ausfüllen: `name`, `timezone`, `calendar_upload` (nur bei meinem Ja `true`), `push_notifications`.
  Die `links` folgen in Schritt 6.
- Lokal die Abhängigkeiten installieren: `python -m pip install -r requirements.txt`.
- Tests laufen lassen: `python -m unittest discover -s tests` (alles grün, ein Test wird übersprungen, solange es noch
  keinen Saisonplan gibt).
- Committen und auf `main` pushen.

## Schritt 4: Garmin-Anmeldung und Tresor

- Starte `python login.py` in einem **Terminalfenster, in das ich selbst tippe** (in der Claude-App ein Terminal-Tab).
  Ich gebe dort E-Mail, Passwort und ggf. den Zwei-Faktor-Code ein. Das Passwort wird nicht gespeichert, nur ein
  Anmeldetoken auf diesem PC.
- Dann `python token_vault.py upload`: erzeugt einen neuen Schlüssel, speichert ihn als GitHub-Geheimnis `VAULT_KEY`
  und legt das verschlüsselte Token in `vault/tokens.enc` ab. Committen und pushen (nur `vault/`).

## Schritt 5: Erster Datenabruf

- `gh workflow run data-sync.yml -f days=28` (holt die letzten 4 Wochen), mit `gh run watch` auf das Ende warten.
- `git pull`, dann prüfen: `data/data.json` existiert, `last_sync` ist aktuell, es gibt Tage und Trainings.
- Schlägt der Lauf mit einem Rechteproblem beim Pushen fehl, die Schreibrechte der Abläufe einschalten:
  `gh api -X PUT repos/<repo>/actions/permissions/workflow -f default_workflow_permissions=write` und erneut starten.

## Schritt 6: Die zwei festen Seiten

- Eine kleine Start-Analyse im Format aus `prompts/morning-health-briefing.md` schreiben (Überschrift z. B.
  „Dashboard eingerichtet“, kein Workout) und `python briefing.py morning --analysis <datei> --out morning.html`
  ausführen; ebenso `python briefing.py wrapup` im Format aus `prompts/daily-wrap-up.md`.
- Skills `artifact-design` und `artifact-capabilities` laden. Dann veröffentlichen:
  - Morning Briefing mit `capabilities: {"downloads": true}` und `icon: "heart"`
  - Daily Wrap-Up mit `icon: "chart"`
- **Beide Seiten anpinnen** (das wünsche ich mir).
- Beide Links in `dashboard.json` unter `links.morning_briefing` und `links.daily_wrapup` eintragen, committen, pushen.
- Die Routinen ersetzen diese Seiten künftig jeden Tag unter denselben Links.

## Schritt 7: Die Routinen

Mit dem Skill `schedule` anlegen, je Zeitplan eine Routine (z. B. getrennt für Werktage und Wochenende):
- **Zeitplan** in meiner Zeitzone: `CRON_TZ=<zeitzone> <minute> <stunde> * * <tage>`, z. B.
  `CRON_TZ=Europe/Berlin 15 7 * * 1-5`
- **Quelle:** mein privates Repository; **Modell:** aus Schritt 2
- **Erlaubte Werkzeuge:** Bash, Read, Write, Edit, Glob, Grep, Skill, ToolSearch, Artifact und (bei Push-Nachrichten)
  PushNotification; Push-Benachrichtigung der Routine passend zu meiner Antwort
- **Nachricht Morning Briefing:** „Erstelle mein Morning Health Briefing. Lies dazu prompts/morning-health-briefing.md
  in diesem Repository und befolge die Anweisungen vollständig und Schritt für Schritt. Antworte auf Deutsch.“
- **Nachricht Daily Wrap-Up:** „Erstelle meinen Daily Wrap-Up. Lies dazu prompts/daily-wrap-up.md in diesem
  Repository und befolge die Anweisungen vollständig und Schritt für Schritt. Antworte auf Deutsch.“
- Bei Push-Nachrichten an beide Nachrichten anhängen: „Rufe als letzten Schritt immer PushNotification auf, mit Link
  und den wichtigsten Werten in <routine_summary>-Tags.“

Die Routinen brauchen Zugriff auf mein Repository (Claude-GitHub-App). Fehlt er, zeig mir, wo ich ihn freigebe.

## Schritt 8: Testlauf

- Die Morning-Briefing-Routine einmal von Hand starten (Skill `schedule`) und ihr Protokoll prüfen:
  - `wait-sync --request` meldet frische Daten
  - die Seite ist unter dem festen Link aktualisiert
  - der GitHub-Ablauf „Routine results“ war erfolgreich und `journal.md` auf `main` hat einen neuen Eintrag
- Frag mich, ob die Push-Nachricht angekommen ist (falls eingeschaltet). Bei Problemen: Ursache suchen und beheben.

## Schritt 9: Training einrichten

Starte den Projekt-Skill `trainer-einstellungen` („Training einrichten“): Sportarten, Ziel (bei Rad- und Laufzielen mit
**Höhenmetern**), Zeitbudget je Wochentag, meine Tage für lange Einheiten, Ruhetage (fest oder dynamisch),
Krafttraining (nur nach meinem ausdrücklichen Ja), Leistungswerte, Einschränkungen. Danach Saisonplan und Vorschau
erstellen, prüfen (`python trainer.py check`) und speichern.

## Schritt 10: Übergabe

Fass für mich in wenigen Zeilen zusammen:
- die Links der beiden Seiten und die Zeiten der Routinen
- wie ich Einstellungen ändere (Sätze wie „Ziel ändern“, „Ruhetage ändern“, „Krafttraining an/aus“, „Einstellungen
  anzeigen“ in einer Claude-Code-Sitzung in diesem Ordner)
- was zu tun ist, wenn die Garmin-Anmeldung abläuft: Du startest `python login.py` (ich tippe im Terminal) und danach
  `python token_vault.py upload`
- wie ich später Änderungen am Dashboard wünsche: einfach beschreiben; du gehst mit den `superpowers`-Skills vor
  (klären → Plan zum Freigeben → testgetrieben umsetzen)
