# Trainingsmethodik

Grundlage für jeden Trainingsvorschlag. Was der Athlet erreichen will, steht im Trainerprofil
`training/profile.json` (Sportarten, Ziel, Zeitbudget, lange Tage, Ruhetage, Krafttraining). Die lange Sicht steht
im Saisonplan `training/season.json`, die nächsten 7–10 Tage in der Vorschau `training/schedule.json`.
`python3 trainer.py check` prüft Profil, Saisonplan und Vorschau gegen die festen Regeln unten.

## 1. Langfristig: Blockperiodisierung

- Beim Ziel „allgemeine Fitness“ wechseln sich Blöcke ab: VO2max-Block (3 Wochen) → Entlastung → Anaerob-Block
  (2 Wochen) → Entlastung → Grundlagen-Block (4 Wochen) → Entlastung, danach von vorn. Bei Wettkampf- und
  Disziplinzielen gilt Abschnitt 5.
- Blöcke mit einem klaren Schwerpunkt bringen bei trainierten Radfahrern mindestens so viel wie gemischtes Training,
  bei der VO2max oft mehr (Rønnestad et al. 2014; Mølmen et al. 2019).
- Die anderen Fähigkeiten werden im Block mit wenig Aufwand erhalten (siehe `notes` der Phase im Saisonplan).
- Entlastung: etwa 40 % weniger Umfang, ein kurzer Reiz, mindestens ein Ruhetag.

## 2. Intensitätsverteilung

- Etwa 75-80 % der Trainingszeit locker (Puls-Zone 1-2), der Rest mittel bis hart. Polarisierte und pyramidale
  Verteilungen sind beide wirksam; polarisiert hat bei gut trainierten Athleten einen kleinen Vorteil für die VO2max
  (Seiler 2010; Stöggl & Sperlich 2014; Oliveira et al. 2024).
- Mindestens 48 h zwischen zwei harten Einheiten für dasselbe System.
- Lockere Einheiten wirklich locker fahren. Entscheidend für die Grundlage ist der Gesamtumfang, nicht eine exakt
  getroffene „Zone 2“ (Storoschuk et al. 2025).
- Die Verteilung gilt über alle Sportarten zusammen; die Zielwerte der Phase stehen in `intensity_target`.

## 3. Täglich: Entscheidung nach Tagesform (HRV-gesteuert)

HRV-gesteuertes Training brachte bei Radfahrern mehr als ein starrer Plan (Javaloyes et al. 2019; Plews et al. 2013).
Gehe so vor:

1. **Was steht heute in der Vorschau?** Der Tag in `training/schedule.json` ist der Ausgangspunkt (Sportart,
   Einheit, Schlüssel- oder lange Einheit). Fehlt der Tag, entscheide vorsichtig nach Saisonphase und Tagesform.
2. **Ampel aus der Tagesform:**
   - **Grün:** HRV letzte Nacht im oder über dem ausgeglichenen Bereich, Trainingsbereitschaft ≥ 70, Ruhepuls
     höchstens ~2 Schläge über dem 7-Tage-Schnitt, Schlaf-Score ≥ 75, Rest-Erholungszeit < 12 h,
     Belastungsverhältnis ≤ 1,3. → Einheit wie geplant.
   - **Gelb:** Ein bis zwei Werte leicht daneben (Bereitschaft 50-69, Schlaf 60-74, Ruhepuls +3/+4).
     → Schlüsseleinheit abgeschwächt: 1-2 Wiederholungen weniger und im unteren Teil des Bereichs. Passt sie im
     Abschnitt noch später, lieber locker und den Tag als „geändert“ markieren.
   - **Rot:** HRV unter dem ausgeglichenen Bereich oder Status „low“/„poor“, Bereitschaft < 50, Ruhepuls ≥ 5 über dem
     Schnitt, Schlaf-Score < 60 bzw. weniger als 6 h Schlaf, Rest-Erholungszeit > 24 h oder
     Belastungsverhältnis > 1,5. → Locker (Ausrollen, `rec_spin_40`) oder Ruhetag. Nichts nachholen.
   Schlafmangel senkt besonders die Leistung bei hoher Intensität (Fullagar et al. 2015).
3. **Ruhetag oder nicht entscheidet die Abwägung aus Abschnitt 7**, nicht die Ampel allein. Eine rote Ampel mit nur
   einem auffälligen Signal (typisch nach einer harten Einheit) führt zu einem lockeren Tag.
4. **Intensitätsverteilung prüfen:** War in den letzten 7 Tagen deutlich mehr als 25 % der Zeit in Zone 3-5,
   heute eher locker.
5. **Einheit wählen:** aus `training/sessions.json`, passend zu Phase und Vorschau. Anpassen erlaubt:
   Wiederholungen, Dauer im Rahmen des Zeitbudgets, Bereiche innerhalb der Bibliothek. Nie härter als die Bibliothek
   vorgibt. Wird eine Schlüsseleinheit abgesagt, bekommt der Tag den Status „geändert“; neu eingeplant wird sie am
   Abend vom Daily Wrap-Up.
6. **Wenn Ruhepuls deutlich erhöht und HRV niedrig sind**, kann das ein Infekt oder eine Überlastung sein: Ruhetag
   empfehlen und das klar, aber ohne Diagnose sagen.

## 4. Intensitätsbereiche Rad (in % der FTP)

| Bereich | % FTP | Zweck |
|---|---|---|
| Erholung | < 55 | Regeneration |
| Grundlage | 56-75 | aerobe Basis, Umfang |
| Tempo | 76-87 | aerobe Kraftausdauer |
| Sweet Spot | 88-93 | Schwelle anheben, zeiteffizient |
| Schwelle | 94-105 | Laktatschwelle |
| VO2max | 106-120 | maximale Sauerstoffaufnahme |
| Anaerob | > 120 | anaerobe Kapazität, Sprints |

Bei VO2max- und Anaerob-Intervallen hinkt der Puls hinterher; dort zählen Watt und Gefühl (8-9 von 10).
Auf Rädern ohne Powermeter nach Puls und Gefühl fahren.

## 5. Saisonplanung (`training/season.json`)

Der Saisonplan wird beim Einrichten und bei jeder Zieländerung ab dem heutigen Tag neu erstellt und vom Daily Wrap-Up
verlängert, wenn weniger als 21 Tage übrig sind.

- **Wettkampfziel:** rückwärts vom Wettkampftag planen: Grundlage → Aufbau → wettkampfspezifisch → Tapering
  (Abschnitt 13) → Wettkampf → Erholung. Entlastung je nach Verlauf alle 2–4 Abschnitte. Bleibt wenig Zeit, werden
  Phasen verkürzt statt ausgelassen. B- und C-Wettkämpfe bekommen ein kurzes Tapering von 2–3 Tagen.
- **Disziplinziel:** wiederkehrende Blöcke mit Schwerpunkt auf dem Ziel:
  - Gran Fondo: lange Grundlage, Sweet Spot und Tempo, Verpflegung im Training üben
  - Zeitfahren: Sweet Spot, Schwelle, VO2max, Training in Aero-Position
  - Bergfahren: lange Anstiege an der Schwelle, Kraftausdauer mit niedriger Trittfrequenz, VO2max (Abschnitt 8)
  - Laufen 5 km bis Marathon und Trail: Grundlage und lange Läufe, Schwelle, VO2max; je länger die Strecke, desto
    mehr Gewicht auf langen Läufen und Schwelle
- **Fitnessziel:** Wechsel VO2max / anaerob / Grundlage (Abschnitt 1).
- **Regeln für die Datei:** Phasen lückenlos und ohne Überschneidung; keine Phase liegt ganz vor dem
  Erstellungsdatum (`created`); das Tapering endet am Tag vor dem Wettkampf und eine Wettkampf-Phase enthält den
  Wettkampftag. Jede Phase hat Name, Schwerpunkt (`focus`), Zeitraum, Arten von
  Schlüsseleinheiten (`key_sessions`), Schlüsseleinheiten pro Abschnitt (`key_per_cycle`), Krafttrainingsphase
  (`strength_phase`), angestrebte Intensitätsverteilung (`intensity_target`) und Hinweise (`notes`).
  `trainer.py write-season` prüft das vor dem Speichern.

## 6. Rollierende Vorschau (`training/schedule.json`)

Kein festes 7-Tage-Raster. Ein Trainingsabschnitt (Mikrozyklus) dauert, was zu Erholung und Zeitbudget passt, meist
7–10 Tage, z. B. 9 Tage mit 3 harten Einheiten. Die Vorschau zeigt immer die nächsten 7–10 Tage und wird jeden Abend
vom Daily Wrap-Up fortgeschrieben. Das Morning Briefing ändert nur den heutigen Tag (Status „erledigt“ oder
„geändert“).

**Feste Regeln** (prüft `trainer.py write-schedule` vor dem Speichern):
- Höchstens eine Einheit pro Tag. Ein Koppeltraining (Rad direkt gefolgt von Lauf) zählt als eine Einheit und ist nur
  bei Triathlon oder Duathlon vorgesehen.
- Lange Einheiten nur an den festen Tagen des Athleten für lange Einheiten (mit der dort festgelegten Sportart), sofern er
  welche festgelegt hat.
- Feste Ruhetage bleiben immer frei. Mindestens die im Profil festgelegte Zahl Ruhetage („Ruhetag“ oder
  „Ruhetag voraussichtlich“) pro Abschnitt.
- Keine zwei Schlüsseleinheiten derselben Sportart an aufeinanderfolgenden Tagen.
- Krafttraining nie am Tag vor einer Schlüssel- oder langen Einheit.
- Der Tagesumfang bleibt im Zeitbudget des Wochentags.
- Nur Sportarten und Einheiten aus Profil und Bibliothek; Krafttraining nur, wenn es bestätigt eingeschaltet ist.

**Planungsregeln** (darauf achtet der Trainer selbst):
- Mindestens 48 h zwischen zwei harten Einheiten für dasselbe System, auch über Sportarten hinweg (harter Lauf und
  harte Radeinheit belasten beide das Herz-Kreislauf-System).
- Lange Einheiten nicht länger als die beim langen Tag festgelegte Höchstdauer.
- Den Pflicht-Ruhetag bevorzugt nach den härtesten Tagen oder vor eine Schlüssel- oder lange Einheit legen.
- Monotonie vermeiden: Tage mit ähnlich hoher Belastung wechseln sich mit lockeren ab. Eine gleichförmig hohe
  Belastung ohne leichte Tage geht mit mehr Infekten und Überlastung einher (Foster 1998).

## 7. Dynamische Ruhetage: Abwägung aller Signale

Nach einer harten Einheit sinken Bereitschaft und HRV kurzfristig, und Garmin zeigt eine lange Erholungszeit. Das ist
normal und gewollt. Auf eine harte Einheit folgt deshalb ein **lockerer Tag**, nicht automatisch ein Ruhetag. Einen
Ruhetag gibt es, wenn das Gesamtbild über mehrere Tage auf angesammelte Ermüdung zeigt. `trainer.recovery_assessment`
rechnet das aus; `briefing.py context` liefert das Ergebnis als `recovery`. Grenzwerte stehen in
`profile.rest_rules`.

| Signal | zählt, wenn … |
|---|---|
| Trainingsbereitschaft | sie heute unter 50 liegt und gestern auch schon unter 50 lag oder gestern locker war |
| Erholungszeit (Garmin) | sie am Morgen nach einem lockeren Tag noch über 24 h liegt |
| Belastungsverhältnis | es über 1,3 liegt und seit gestern weiter gestiegen ist |
| HRV der letzten Nächte | der Schnitt der letzten 3 Nächte unter dem Normalbereich liegt oder sie 3 Nächte in Folge um insgesamt mindestens 10 % fällt |
| Schlaf-Scores | der Schnitt der letzten 2–3 Nächte unter 70 liegt |
| Ruhepuls-Entwicklung | er heute und gestern jeweils 3 oder mehr Schläge über dem 7-Tage-Schnitt liegt |
| Trainingstage in Folge | seit dem letzten trainingsfreien Tag 6 oder mehr Tage vergangen sind |

Fehlende Werte zählen nie als Signal.

**Entscheidung**
- **Sofort Ruhetag:** Ruhepuls 5 oder mehr über dem Schnitt **und** HRV letzte Nacht unter dem Normalbereich. Das kann
  auf einen Infekt oder eine Überlastung hindeuten.
- **Ruhetag:** mindestens 3 Signale.
- **Lockerer Tag** (Ausrollen oder kurze Grundlage): 1–2 Signale. Das ist der typische Tag nach einer harten Einheit.
- **Sonst** nach Plan trainieren.

In der Vorschau steht ein dynamischer Ruhetag als „Ruhetag voraussichtlich“; endgültig entscheidet das Morning Briefing
mit den frischen Nachtwerten. Die Grenzwerte sind Startwerte. Nach einigen Wochen darf der Trainer sie an die
typischen Werte des Athleten anpassen (z. B. an seinen üblichen Schlaf-Score); jede Anpassung kommt ins Journal.
HRV-Trend statt Einzelwert (Plews et al. 2013); Leistungsabfall, Schlafprobleme und erhöhter Ruhepuls zusammen sind
die frühen Zeichen einer Überlastung (Meeusen et al. 2013).

## 8. Höhenmeter und Bergtraining

Aus Distanz und Höhenmetern des Ziels ergibt sich das Profil (Höhenmeter pro km). Als Richtwert gilt ein Ziel ab
etwa 10 Hm/km beim Rad oder 20 Hm/km beim Laufen als bergig.

- **Rad:** lange Anstiegsintervalle an Sweet Spot und Schwelle (`climb_sst_3x20`), dazu VO2max für die steilen
  Stücke und lange Ausfahrten mit von Abschnitt zu Abschnitt steigenden Höhenmetern. Kraftausdauer mit 50–60 U/min
  (`climb_lowcad_5x6`) gewöhnt an steile Anstiege; zusätzliche Leistungseffekte sind in Studien klein
  (Kristoffersen et al. 2014), deshalb sparsam einsetzen.
- **Laufen:** Bergintervalle (`run_hills_8x60`), Bergablaufen behutsam steigern (die exzentrische Belastung erzeugt
  sonst starken Muskelkater), einen Höhenmeter-Umfang pro Abschnitt planen und steigern.
- In den letzten 4–6 Wochen vor dem Wettkampf sollen die langen Einheiten der Zielstrecke in Höhenmetern ähneln.
- Hat das Ziel einen bekannten längsten Anstieg, orientieren sich Dauer und Länge der Anstiegsintervalle daran.

## 9. Laufen

- Intensität nach Laufschwelle (Pace oder Puls aus dem Profil); fehlt sie, nach Pulszonen und Gefühl und einen Test
  vorschlagen (z. B. 30 min allein so schnell wie gleichmäßig möglich, Durchschnittspuls der letzten 20 min).
- Wie beim Rad etwa 80 % locker (`run_easy_45`, `run_long_90`), dazu Schwelle (`run_tempo_3x10`), VO2max
  (`run_vo2_5x3`) und Bergintervalle; Steigerungsläufe (`run_strides_6`) halten Schnelligkeit und Laufstil.
- Laufumfang behutsam steigern, Richtwert höchstens etwa 10 % pro Abschnitt. Sprünge von über 30 % gingen in einer
  Studie mit mehr Verletzungen einher (Nielsen et al. 2014). Laufen belastet Sehnen und Knochen stärker als Radfahren,
  deshalb nach Pausen langsamer wieder aufbauen als auf dem Rad.
- Ein harter Lauf und eine harte Radeinheit belasten dasselbe Herz-Kreislauf-System: die 48-h-Regel gilt über beide
  Sportarten.

## 10. Schwimmen

- Intensität nach kritischer Schwimmgeschwindigkeit (CSS, Pace pro 100 m; Wakayoshi et al. 1992). Fehlt sie, einen
  Test vorschlagen: 400 m und 200 m maximal, CSS = 200 m ÷ (Zeit 400 m − Zeit 200 m).
- Technik zuerst (`swim_tech_2000`), dazu Schwellen-Serien (`swim_css_10x100`) und lockerer Umfang
  (`swim_endurance_3000`). Strecken passend zur Bahnlänge aus dem Profil.
- Schwimmen belastet die Beine kaum; eine lockere Schwimmeinheit passt deshalb auch zwischen zwei harte Rad- oder
  Laufeinheiten.

## 11. Triathlon und Duathlon

- Die Zeit verteilt sich nach Ziel und Schwachstelle; als Startwert beim Triathlon etwa 20 % Schwimmen, 50 % Rad,
  30 % Laufen, beim Duathlon etwa 60 % Rad und 40 % Laufen. Schlüsseleinheiten der schwächsten oder wichtigsten
  Disziplin haben Vorrang.
- Koppeltraining (`brick_bike90_run20`) gewöhnt die Beine an den Wechsel vom Rad zum Laufen; in der wettkampfspezifischen
  Phase etwa einmal pro Abschnitt, sonst seltener. Es zählt als eine Einheit und meist als lange Einheit.
- Die 48-h-Regel für harte Einheiten gilt über alle Disziplinen; Schwimmen kann an lockeren Tagen dazukommen, aber nie
  als zweite Einheit am selben Tag.

## 12. Krafttraining

Schweres Krafttraining verbessert bei Rad- und Laufsportlern Leistung und Ökonomie, ohne der Ausdauer zu schaden
(Rønnestad & Mujika 2014; Beattie et al. 2014). Es wird nur geplant, wenn der Athlet es ausdrücklich bestätigt hat
(`strength.enabled`).

- **Phasen:** Gewöhnung 2–3 Wochen (`str_adapt`, leichtere Gewichte, Technik) → Maximalkraft 2× pro Abschnitt in
  Grundlagenphasen (`str_bike_max`, 4–6 Wiederholungen, schwer, lange Pausen) → 1× pro Abschnitt zum Erhalt in Aufbau-
  und Wettkampfphasen (`str_bike_maint`) → Pause ab 7–10 Tage vor einem A-Wettkampf. Die Phase steht je Saisonphase
  in `strength_phase`.
- **Platzierung:** Krafttraining ersetzt einen lockeren Tag, nie den Tag vor einer Schlüsseleinheit oder einer langen
  Einheit. Keine zweite Einheit am selben Tag.
- **Übungen je Sportart:** Rad: Kniebeuge, Kreuzheben, Ausfallschritt oder bulgarische Kniebeuge, Step-ups, Waden,
  Rumpf. Laufen zusätzlich einbeinige Übungen, Waden und Sprungkraft (`str_run`). Schwimmen: Zugübungen und
  Schulterstabilität (`str_swim`). Die Übungsnamen kommen aus der Garmin-Übungsliste, damit die Einheit im
  Garmin-Kalender richtig erscheint.
- Belastung nach Gefühl (RPE 7–8, 2–3 Wiederholungen „im Tank“); Technik vor Gewicht.

## 13. Tapering

- Vor einem A-Wettkampf 7–14 Tage: Umfang um 40–60 % senken, Intensität und Häufigkeit der Einheiten erhalten. So
  lässt sich die Leistung im Mittel um etwa 2–3 % steigern (Bosquet et al. 2007).
- Kurze, scharfe Reize bleiben (z. B. `rec_opener`); keine neuen oder ungewohnten Einheiten.
- B- und C-Wettkämpfe: 2–3 Tage leichter, danach direkt weiter im Plan.
- Nach dem Wettkampf eine Erholungsphase, deren Länge zur Belastung des Wettkampfs passt.

## Quellen

- Beattie K, Kenny IC, Lyons M, Carson BP (2014). The effect of strength training on performance in endurance athletes. Sports Medicine.
- Bosquet L, Montpetit J, Arvisais D, Mujika I (2007). Effects of tapering on performance: a meta-analysis. Med Sci Sports Exerc.
- Buchheit M, Laursen PB (2013). High-intensity interval training, solutions to the programming puzzle. Sports Medicine.
- Foster C (1998). Monitoring training in athletes with reference to overtraining syndrome. Med Sci Sports Exerc.
- Fullagar HHK et al. (2015). Sleep and athletic performance. Sports Medicine.
- Gist NH et al. (2014). Sprint interval training effects on aerobic capacity: meta-analysis. Sports Medicine.
- Javaloyes A et al. (2019). Training prescription guided by heart-rate variability in cycling. Int J Sports Physiol Perform.
- Kristoffersen M et al. (2014). Low cadence interval training at moderate intensity does not improve cycling performance in highly trained veteran cyclists. Frontiers in Physiology.
- Laursen PB, Jenkins DG (2002). The scientific basis for high-intensity interval training. Sports Medicine.
- Meeusen R et al. (2013). Prevention, diagnosis, and treatment of the overtraining syndrome: joint consensus statement of the ECSS and the ACSM. Med Sci Sports Exerc.
- Mølmen KS, Øfsteng SJ, Rønnestad BR (2019). Block periodization of endurance training: systematic review and meta-analysis. Open Access J Sports Med.
- Nielsen RO et al. (2014). Excessive progression in weekly running distance and risk of running-related injuries. J Orthop Sports Phys Ther.
- Oliveira PS et al. (2024). Polarized versus other training intensity distributions: systematic review with meta-analysis. Sports Medicine.
- Plews DJ et al. (2013). Training adaptation and heart rate variability in elite endurance athletes. Sports Medicine.
- Rønnestad BR, Mujika I (2014). Optimizing strength training for running and cycling endurance performance: a review. Scand J Med Sci Sports.
- Rønnestad BR et al. (2014). Block periodization of high-intensity aerobic intervals in trained cyclists. Scand J Med Sci Sports.
- Rønnestad BR et al. (2015). Short intervals induce superior training adaptations compared with long intervals in cyclists. Scand J Med Sci Sports.
- Rønnestad BR et al. (2020). Short-interval vs effort-matched long-interval training in elite cyclists. Scand J Med Sci Sports.
- Seiler S (2010). What is best practice for training intensity and duration distribution in endurance athletes? Int J Sports Physiol Perform.
- Seiler S et al. (2013). Adaptations to aerobic interval training: interactive effects of exercise intensity and total work duration. Scand J Med Sci Sports.
- Stöggl T, Sperlich B (2014). Polarized training has greater impact on key endurance variables than threshold, high intensity, or high volume training. Frontiers in Physiology.
- Storoschuk KL et al. (2025). Much ado about zone 2: efficacy of zone 2 training for mitochondrial capacity and fitness. Sports Medicine.
- Wakayoshi K et al. (1992). Determination and validity of critical velocity as an index of swimming performance in the competitive swimmer. Eur J Appl Physiol.
