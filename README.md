# Evaluationen bereinigen

Kleine Windows-Desktop-Anwendung zum Finden und kontrollierten Löschen alter
Evaluationen. Python 3.12, Flet 0.85.3 und Standardbibliothek; keine Inhaltsanalyse.

**Aktueller Stand: Dry-Run. `DELETE_ENABLED = False`.** Die Oberfläche simuliert
Löschungen und verändert keine gefundenen Dateien. Windows-Abnahme und Freigabe
für produktives Löschen stehen noch aus.

## Für die Anwenderin

1. `Evaluationen-bereinigen.exe` starten.
2. Prüfen, ob der Basisordner erreichbar ist. Andernfalls Laufwerk `T:` verbinden
   und **Erneut prüfen** anklicken.
3. Das gewünschte Grenzjahr auswählen.
4. **Evaluationen suchen** anklicken und die Treffer prüfen.
5. Unerwünschte Häkchen entfernen; alternativ **Alle auswählen / Alle abwählen**.
6. **Auswahl löschen** anklicken.
7. Im Dialog abbrechen oder die beschriftete Löschfläche bewusst mit Maus/Touch
   anklicken. Enter bestätigt keine Löschung.

Im Testmodus bleibt jede Datei erhalten. Im später freigegebenen Echtbetrieb
werden Dateien **endgültig gelöscht, nicht in den Papierkorb verschoben**.
Ergebnis und Einzelfehler erscheinen im Anschluss. Vor einem weiteren Auftrag
ist eine neue Suche erforderlich.

## Entwicklung

Voraussetzungen: Python 3.12, [uv](https://docs.astral.sh/uv/), für die native
Oberfläche eine Desktop-Sitzung. Die Zielplattform ist Windows 10/11.

```console
uv sync --locked
uv run flet run src/main.py
```

Alternativ startet `uv run evaluation-cleanup` dieselbe Anwendung. Der bestehende
ASCII-Projekt-/Paketname `evaluation-cleanup` / `evaluation_cleanup` bleibt erhalten.
Auf Linux funktioniert die Entwicklung mit temporären Testdaten; der fest
eingestellte Windows-Pfad wird dort als nicht erreichbar angezeigt.

### Lokale Demo ohne Netzlaufwerk

#### Demo mit den bereitgestellten PDF-/Excel-Dateien

```console
uv run python tools/demo.py --documents
```

Der Starter kopiert die fünf Originaldateien aus
`development/documents/Evaluationen_löschen.zip` nach
`development/demo/Seminare/` und öffnet die Anwendung im **Dry-Run**. Das Archiv
bleibt unverändert. Die Jahres-, Kategorie- und Seminarzuordnung ist für den
Test fiktiv festgelegt:

| Jahr | Datei |
| --- | --- |
| 2023 | `Evaluation FührungsSnack Danke_11.7_.xlsx` |
| 2024 | `Evaluationen Creative Dates bis Juli 24.xlsx` |
| 2024 | `Evaluation_Teamrollen_26.11.pdf` |
| 2024 | `Feedbackbögen_DHBW_20240513_Umgang mit schwierigen Menschen.PDF` |
| 2025 | `Feedback_5298.pdf` |

**Zum Testen:** Grenzjahr 2023 auswählen → **1 Treffer**, 2024 → **4 Treffer**,
2025 → **5 Treffer**. Anschließend einzelne Dateien abwählen und einen
Löschvorgang bestätigen. Die Oberfläche muss die Löschungen als **simuliert**
melden; alle PDF-/Excel-Dateien bleiben erhalten.

Die Demo-Dateien bleiben auch nach dem Schließen bestehen. Das Protokoll liegt
nach einem Testlauf unter `development/demo/actions.csv`. Wiederholte Starts
verwenden identische Kopien weiter und ergänzen das Protokoll. Abweichende
vorhandene Dateien werden mit einer Fehlermeldung abgewiesen, niemals überschrieben.
Das gesamte Verzeichnis `development/` ist bereits von Git ausgeschlossen.

Nur die Daten einrichten, ohne die Oberfläche zu öffnen:

```console
uv run python tools/demo.py --documents --prepare-only
```

#### Temporäre Demo mit Dummy-Dateien

```console
uv run python tools/demo.py
```

Der separate Entwicklungsstarter erzeugt einen **eigenen temporären** Seminarbaum,
öffnet dieselbe Oberfläche und erlaubt ausschließlich den Dry-Run. Es gibt weder
einen Pfadparameter noch ein editierbares Basisverzeichnis. Bei **2024** werden
**6 Kandidaten** aus 2022–2024 gefunden; Teilnehmerliste, Vorlagen, `2024_alt` und
die Datei aus 2025 bleiben außen vor. Nach normalem Schließen wird überprüft, ob
alle zehn Dummy-Dateien unverändert sind. Testdaten und Demo-Protokoll werden
anschließend entfernt. Die Platzhalter sind keine tatsächlich lesbaren PDFs/Excel-Dateien.

`tools/` wird nicht in das Windows-App-Paket aufgenommen. Der normale Start
verwendet immer den fest konfigurierten Produktionspfad.

### Qualitätsprüfungen

```console
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

Die Tests verwenden ausschließlich temporäre Verzeichnisse, niemals `T:` und
kein Netzwerk. Echtes Löschen wird in einzelnen Tests gezielt mit temporären
Dummy-Dateien geprüft; der Konfigurationsschalter bleibt dabei unverändert im
Quelltext auf `False`. Die Flet-Integrationstests führen die registrierten
Ereignishandler mit echten Controls und einem simulierten Page-Objekt aus. Das
ersetzt keine sichtbare Windows-Abnahme. Symlink-Tests werden übersprungen, falls
das Betriebssystem keine entsprechenden Rechte gewährt.

## Struktur

```text
pyproject.toml                  Abhängigkeiten, Flet-Build und Qualitätswerkzeuge
uv.lock                         Aufgelöste, reproduzierbare Python-Abhängigkeiten
src/
  main.py                       Offizieller Flet-Einstiegspunkt
  evaluation_cleanup/
    __init__.py                 Bestehender Konsolen-Einstiegspunkt
    app.py                      Fensterkonfiguration und Start
    config.py                   Root, Dateiendungen, Suchwörter, Löschschalter
    models.py                   Unveränderliche Dataclasses
    safety.py                   Gemeinsame Pfad- und Dateiprüfung
    scanner.py                  Rein lesende Suche
    deletion.py                 Löschservice, Dry-Run und CSV-Protokoll
    workflow.py                 Aktueller Scan, Auswahl, einmalige Bestätigung
    ui.py                       Ein Flet-Hauptbildschirm
tests/                          Scanner-, Sicherheits-, Workflow- und GUI-Tests
tools/demo.py                   Separater lokaler Demo-Starter
```

## Zentrale Konfiguration und Sicherheitsverhalten

`src/evaluation_cleanup/config.py` enthält:

- `ALLOWED_ROOT`: ausschließlich `T:\ZHL\Personalförderung\02_Seminare`.
- `DELETE_ENABLED = False`: kein echtes Löschen im ausgelieferten Entwicklungsstand.
- `SUPPORTED_EXTENSIONS`: `.pdf`, `.xlsx`, `.xls`, unabhängig von Groß-/Kleinschreibung.
- `EVALUATION_KEYWORDS`: Unicode-normalisierte, nicht case-sensitive Teilstringsuche.

Nur unmittelbar untergeordnete Ordner mit exakt vier ASCII-Ziffern gelten als
Jahresordner. Gesucht wird bis einschließlich des gewählten Jahres. Die ersten
beiden Unterordner liefern Kategorie und Seminar; kürzere Pfade sind erlaubt.

Die Suche folgt keinen symbolischen Links, Junctions oder anderen
Windows-Reparse-Points. Auch Reparse-Points in übergeordneten Pfadkomponenten und
Dateien mit mehreren Hardlinks werden abgewiesen. Nicht lesbare oder unsichere
Teilpfade erscheinen unter **Hinweise anzeigen**; die übrigen Treffer bleiben
prüfbar. Solche Hinweise bedeuten, dass nicht alle Dateien durchsucht werden konnten.

Vor jeder Löschung werden Root, Pfadgrenze, Dateityp und die beim Scan erfassten
Dateimerkmale erneut geprüft. Dateien außerhalb des Scans, veränderte Dateien,
Ordner und fremde Roots werden abgewiesen. Ein Wechsel des Jahres, eine neue
Suche oder eine geänderte Auswahl entwertet vorherige Bestätigungen. Ein Auftrag
kann nur einmal bestätigt werden. Scan und Löschung laufen im Hintergrund;
währenddessen sind die betreffenden Bedienelemente gesperrt.

**Betriebsgrenze:** Die erneute Pfadprüfung und `Path.unlink()` sind getrennte
Betriebssystemoperationen, keine atomare Transaktion. Gegen einen gezielten
gleichzeitigen Austausch von Pfadkomponenten im winzigen Zwischenraum besteht
keine handlebasierte Absicherung. Für die Produktivfreigabe muss dieser Punkt
für das Netzlaufwerk bewertet werden; bei entsprechenden Anforderungen ist vor
Aktivierung eine Windows-handlebasierte Löschimplementierung nötig.

### Protokoll

Windows: `%LOCALAPPDATA%\evaluation-cleanup\actions.csv`.
Linux-Entwicklung: `$XDG_STATE_HOME/evaluation-cleanup/actions.csv`, ersatzweise
`~/.local/state/evaluation-cleanup/actions.csv`.

UTF-8-CSV mit Semikolon, ohne Kopfzeile:

```text
Zeitpunkt;Aktion;Dateipfad;Jahr;Ergebnis;Fehlermeldung
```

Aktionen: `DRY_RUN` oder `DELETE`. Ergebnisse: `START`, `SIMULATED`, `OK`,
`MISSING`, `ERROR`. Jeder Einzelauftrag wird zunächst als `START` und danach mit
seinem Ergebnis protokolliert. Das Protokoll wird vor Löschoperationen auf den
Datenträger geschrieben. Kann es nicht geschrieben werden, werden keine weiteren
Dateien gelöscht. Ein Fehler **nach** einer Löschung wird angezeigt und stoppt
den restlichen Auftrag; die bereits erfolgte Löschung wird weiterhin als Erfolg
gemeldet. Ein alleiniger `START`-Eintrag erfordert nach einem Programmabbruch eine
manuelle Prüfung. Dateiinhalte werden nie protokolliert.

## Windows-Build

Der moderne offizielle Weg ist **`flet build windows`**, nicht `flet pack`.
Ein Windows-Build kann nur auf einem Windows-Host erstellt werden.

### Voraussetzungen auf dem Build-Rechner

- Windows 10/11, Python 3.12, uv und Git.
- Visual Studio 2022 mit **Desktop development with C++**, einschließlich
  MSVC-Toolchain, CMake und Windows SDK.
- Internetzugriff für den ersten Download der Flet-/Flutter-Buildwerkzeuge und
  Paketabhängigkeiten. Flet 0.85.3 meldet Flutter 3.41.7 als zugehörige Version.

Im Projektverzeichnis (PowerShell):

```powershell
uv sync --locked
uv run flet --version
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
uv run flet build windows --artifact Evaluationen-bereinigen
```

`[tool.flet.app].path = "src"` legt den zu paketierenden App-Code fest.
`--artifact` setzt den Dateinamen der Anwendung; der Anzeigename steht als
`product` in `pyproject.toml`. Der erwartete Ausgabeordner ist `build/windows/`
mit `Evaluationen-bereinigen.exe` und den zugehörigen Bibliotheken/Daten.

**Den gesamten Ausgabeordner verteilen**, beispielsweise als ZIP. Die EXE allein
reicht bei diesem Buildverfahren nicht. Die Anwenderin entpackt den Ordner und
startet die EXE per Doppelklick; Python und Terminal sind nicht erforderlich.
Die Flet-/Python-Laufzeit wird mitgeliefert. Den Build auf einem Windows-Rechner
ohne Entwicklungsumgebung prüfen, einschließlich etwaiger nativer
Laufzeitvoraussetzungen. Ein Windows-Build wurde in der Linux-Entwicklungsumgebung
noch nicht erzeugt oder ausgeführt.

Offizielle Referenzen:
- [Flet-Veröffentlichung](https://flet.dev/docs/publish)
- [Windows-Build](https://flet.dev/docs/publish/windows)

## Manuelle Abnahme und Freigabe

1. **Lokale Demo:** Jahre, Grenze 2024, sechs Treffer, tiefe/kurze Pfade und
   Nicht-Treffer kontrollieren. Lange Namen, Scrollen und Notebook-Auflösung testen.
2. **Auswahl:** Einzelne Häkchen, Alle auswählen/abwählen, Zähler und deaktivierten
   Löschbutton ohne Auswahl prüfen.
3. **Dialog:** Abbrechen und Schließen dürfen nichts verändern. Enter darf keine
   Löschung auslösen. Doppelklick darf nur einen Auftrag ausführen.
4. **Dry-Run:** Testlauf bestätigen, Ergebnis prüfen, Demo normal schließen und
   die Meldung über unveränderte Dummy-Dateien kontrollieren.
5. **Sicherheits- und echte Dummy-Löschtests unter Windows:** `uv run pytest`
   ausführen. Windows-Junctions, Netzlaufwerksrechte und die oben genannte
   Betriebsgrenze zusätzlich bewerten.
6. **Windows-Paket:** Im Testmodus bauen und auf einem Rechner ohne Python/
   Entwicklungsumgebung starten. Nicht verbundenes `T:`, Wiederverbinden und
   anschließend den reinen Scan auf `T:` mit der Fachanwenderin prüfen.
7. **Produktivfreigabe:** Erst nach dokumentierter Abnahme und expliziter Freigabe
   `DELETE_ENABLED = True` setzen und neu bauen. Der Test für den sicheren
   Auslieferungsmodus muss dann bewusst an den freigegebenen Release-Stand
   angepasst werden. Zunächst ausschließlich 1–2 ausdrücklich dafür vorgesehene
   Testdateien auf dem Produktivlaufwerk löschen und Protokoll/Ergebnis prüfen.

Die Freigabe erfolgt nicht automatisch durch bestandene Unit-Tests.
