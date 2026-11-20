# Harvester Deutsch – Technische Quellcodeprüfung für Nexus Mods

Dieses Dokument soll externen Prüfern die **Nachvollziehbarkeit beider Windows-EXEs** ermöglichen. Es ist keine Zusage einer Freigabe durch Nexus Mods oder die Rechteinhaber.

## Verbindlicher Projektstand

- **Gemeinsame Spieler-Release-Seite:** [GOG v1.0.0 + ScummVM v1.0.1](https://github.com/Koarria/Harvester-German-Translation/releases/tag/v1.0.0)
- **Vollständiger, versionierter Prüfstand:** [Git-Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1)
- **Alle Quellen und Ressourcen als ein ZIP:** [Projektarchiv v1.0.1](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip)
- **Programmsourcen (47 Dateien):** [source/ am Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1/source)
- **Übersetzungsressourcen:** [resources/ am Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1/resources)

**Nicht verwechseln:** Das separat angebotene `Harvester_GOG_Deutsch_Source_v1.0.0.zip` ist ein **historisches GOG-Source-Archiv**, kein vollständiges Paket für den inzwischen korrigierten ScummVM-Konverter v1.0.1. Die auf der Release-Seite automatisch angebotenen GitHub-Archive **`Source code (zip)` / `(tar.gz)`** beziehen sich auf den **ursprünglichen Tag `v1.0.0`**, der noch vor der eigentlichen Quellcodeveröffentlichung gesetzt wurde. Deshalb zur aktuellen technischen Prüfung das **v1.0.1-Projektarchiv** aus dem Link oben verwenden.

## Zuordnung der beiden Spielerdateien

| Datei aus dem gemeinsamen Release | Maßgebliche Implementierung | Erzeugung |
| --- | --- | --- |
| `Harvester_GOG_Deutsch_v1.0.0.zip` | `source/tools/developer/delta_onepass_installer.py`, `delta_onepass_wizard.py`, `source/installer.py`, `source/runtime/`, `source/src/windows/` | [GOG-Windows-Bauskript](https://github.com/Koarria/Harvester-German-Translation/blob/v1.0.1/build/Harvester_aus_Quellcode_bauen.cmd) |
| `Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip` | `source/tools/developer/scummvm_converter.py`, `scummvm_converter_gui.py`, `source/runtime/harvester_iso.py` | [ScummVM-Windows-CI-Bau](https://github.com/Koarria/Harvester-German-Translation/blob/v1.0.1/.github/workflows/harvester-scummvm-v101-windows-qa.yml) |

Zum Bau der Programme wird **kein Originalspiel heruntergeladen oder mitgeliefert**. Zum **Installieren/Verwenden** benötigen Spieler dagegen eine eigene, **in den Dateihashes unterstützte englische GOG-Version von Harvester**. Der ScummVM-Konverter setzt eine zuvor mit dem GOG-Installer erstellte deutsche GOG-Kopie voraus.

## GOG-Installer: Transparenz und Nachbau

1. Das vollständige v1.0.1-Projektarchiv herunterladen und entpacken.
2. Unter Windows `build/Harvester_aus_Quellcode_bauen.cmd` ausführen (Python 3.13 und die im Repository benannten Bauabhängigkeiten erforderlich).
3. Das Bauskript kontrolliert die Prüfsummen der Delta-/XML-/C#-Hilfsressourcen und baut ein **neues** `Harvester_GOG_Deutsch_v1.0.0.zip`.

Der veröffentlichte GOG-Installer ist ein **älterer, vom Projektinhaber getesteter v1.0.0-Build**. Das Bauskript verwendet eine bereits kompilierte **eigene C#-Hilfs-EXE** unter `resources/payload/Harvester_Deutsch_Patcher.exe`; der zugehörige Code liegt unter `source/src/windows/`. **Ein bitidentischer Neubau dieser C#-Hilfs-EXE sowie der ursprünglichen GOG-Spieler-EXE ist nicht nachgewiesen.** Der erfolgreiche unabhängige Windows-Nachbau zeigt die Funktionsfähigkeit des öffentlichen Buildwegs, nicht die Identität sämtlicher kompilierten Bytes.

[Öffentlicher GOG-Nachbau / GitHub Actions](https://github.com/Koarria/Harvester-German-Translation/actions/runs/44708777057)

## ScummVM-Konverter: Transparenz und Nachbau

Der Konverter ist aus Python-Quellen über den öffentlichen Windows-Workflow mit **PyInstaller** gebaut. Der [Workflow](https://github.com/Koarria/Harvester-German-Translation/blob/v1.0.1/.github/workflows/harvester-scummvm-v101-windows-qa.yml) dokumentiert Python 3.13, die Abhängigkeiten, die `--add-data`-Ressourcen, den Onefile-Befehl, Selbsttest, Paketinhalt und SHA-256-Prüfungen.

Die [23 Regressionstests](https://github.com/Koarria/Harvester-German-Translation/blob/v1.0.1/source/tools/developer/test_scummvm_converter.py) kontrollieren unter anderem verschobene GOG-Installationspfade, abweichende Dateien, die lokale Render-QA, ISO-Extraktion, Spielstand-Sicherheit und die **11-px-Vorauswahl**. Die Tests arbeiten mit synthetischen Daten; zusätzlich bestätigte der Projektinhaber bei einem praktischen Windows-Test deutsche Spieltexte, Videountertitel und vorhandene ScummVM-Spielstände.

[Erfolgreicher öffentlicher ScummVM-v1.0.1-Bau / GitHub Actions](https://github.com/Koarria/Harvester-German-Translation/actions/runs/44708777068)

Die Konverter-EXE benötigt beim Spieler **kein Python** und enthält laut Windows-CI weder Originalspiel-Datenträger noch das deutsche GOG-Delta.

## Übersetzungsressourcen und Dateischutz

Das öffentliche Repository enthält das binäre Delta für die deutsche GOG-Fassung, **128 SRT-Untertiteldateien**, `Regeln.xml` und `VideoManifest.xml` sowie die öffentlichen Patcher-/Renderer-Implementierungen. Die Installer überprüfen feste Datei- und Manifestsummen. Der Originalordner kann frei benannt und auf einem anderen Laufwerk liegen, aber die erwarteten **Dateinamen und geprüften Datei-Inhalte** müssen passen. Neue Zielordner sind fest benannt; vorhandene Spielordner werden nicht überschrieben. Für den **Wiederaufnahmemodus einer abgebrochenen GOG-Installation** gilt weiterhin eine zusätzliche historische Pfadbindung.

## SHA-256 der veröffentlichten Spieler-ZIPs

Diese Werte entsprechen den unveränderten Dateien auf der gemeinsamen Release-Seite:

| Download | SHA-256 |
| --- | --- |
| `Harvester_GOG_Deutsch_v1.0.0.zip` | `0135d48708a11635f66d315d7af88bf63ad15f3aba59346e1e0b9acb7c0146f8` |
| `Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip` | `d94f8c87cd7b13ffcee66ff0c95decf118dde87d1a0ad60611b8b84f3c5901c2` |
| `Harvester_GOG_Deutsch_Source_v1.0.0.zip` (historisch) | `14fb36f59765622bd7d72c9eabd9c93ea2c1d36de1d0f114103f4acf569fda43` |
| `Harvester_GOG_Deutsch_Resources_v1.0.0.zip` | `b74d3b3b028d5075f681c756128f83d0c5aa156a8d25437391104d23681dcc39` |

## Rechte und bekannte Grenzen

Die Veröffentlichung bietet Code und übersetzte Ressourcen **zur Einsicht**, aber keine ausdrücklich freie Lizenz für alle Teile und **keine belegte urheberrechtliche Erlaubnis** der ursprünglichen Rechteinhaber. Auch das kleine Delta enthält abgeleitete Spielinhalte. Weder die öffentliche Prüfbarkeit noch ein erfolgreicher Windows-Bau garantieren deshalb die Freigabe durch Nexus Mods.

**Vollständige Quelltexte zur Prüfung** bedeutet nicht automatisch, dass sämtliche Binärdateien bitidentisch aus diesen Quellen reproduzierbar sind. Die Unterschiede sind oben ausdrücklich dokumentiert.
