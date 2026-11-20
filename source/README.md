# Quellcode der deutschen Harvester-Fanübersetzung

Dieses Verzeichnis enthält den **öffentlich einsehbaren Programmquellcode und die Tests** für den GOG-/DOSBox-Installer **v1.0.0** und den ScummVM-Konverter **v1.0.1**. Der GOG-Installer-Code stammt aus dem zum erfolgreichen Windows-Build gehörenden privaten Commit `cd0b3c62f1b374055a47ac819e2ace4e5ff46e46`; die ScummVM-Quellen enthalten zusätzlich den geprüften Fix für verschobene GOG-Ordner und die **11-px-Vorauswahl**. Die bereits veröffentlichten Spieler-EXEs bleiben unverändert.

## Inhalt

| Bereich | Funktion |
| --- | --- |
| [`installer.py`](installer.py) | Deutsch-Installationsprozess, Filmverarbeitung und Orchestrierung |
| [`tools/developer/delta_onepass_wizard.py`](tools/developer/delta_onepass_wizard.py) | Windows-Oberfläche mit Ein-Klick-Installation |
| [`tools/developer/delta_onepass_installer.py`](tools/developer/delta_onepass_installer.py) | Einmaliger Gesamtprozess, eingebettetes Delta und Integritätsprüfungen |
| [`tools/developer/delta_core_shadow_installer.py`](tools/developer/delta_core_shadow_installer.py) | Rekonstruktion der deutschen Zieldateien |
| [`tools/developer/delta_core_proof.py`](tools/developer/delta_core_proof.py) | Pfadgebundener XML-Nachweis und SHA-256-Validierung |
| [`tools/developer/delta_embedded_bundle.py`](tools/developer/delta_embedded_bundle.py) | Prüfung des in der EXE enthaltenen Delta-Bundles |
| [`tools/developer/delta_video_addon.py`](tools/developer/delta_video_addon.py) | Einbau der übersetzten Videountertitel |
| [`tools/developer/unified_delta_bundle.py`](tools/developer/unified_delta_bundle.py) | Delta-Format und Datenrekonstruktion |
| [`runtime/`](runtime/) | ISO-/FST-Codec, Untertitel-Rendering, parallele Verarbeitungslogik |
| [`src/windows/`](src/windows/) | C#-Quellcode des Windows-Patchers und der Videoerweiterung |
| [`tools/developer/test_*.py`](tools/developer/) | Tests für SHA-256, Core, Video, Delta, Bedienung und Paketinhalt |
| [`tools/developer/build_release_private.ps1`](tools/developer/build_release_private.ps1) | Bauablauf für die Onefile-EXE und Paketprüfung |

### ScummVM-Konverter (zusätzlich)

- [`tools/developer/scummvm_converter.py`](tools/developer/scummvm_converter.py) – ISO-Extraktion nach ScummVM-CD1/CD2/CD3, Integritätskontrolle und Spielstand-Schutz
- [`tools/developer/scummvm_converter_gui.py`](tools/developer/scummvm_converter_gui.py) – eigenständiger Windows-Konverter mit drei Untertitelmodi
- [`tools/developer/test_scummvm_converter.py`](tools/developer/test_scummvm_converter.py) – **23 synthetische Regressionstests**, einschließlich verschobener GOG-Ordner, Datei-/SHA-256-Manipulationen, Installationsnachweis-Sonderfällen und 11-px-Vorauswahl
- [`../docs/SCUMMVM_EINSTELLUNGEN.md`](../docs/SCUMMVM_EINSTELLUNGEN.md) – optionale ScummVM-Einstellungen

Die ScummVM-Konverterlogik wurde unter Windows mit eigenen GOG-Daten geprüft: deutsche Texte, Videountertitel und vorhandene ScummVM-Spielstände funktionierten. Die aktuelle GUI-Vorauswahl **11 px** und die Sicherheitskontrollen wurden zusätzlich im Windows-Bau mit **23/23 Regressionstests** geprüft. Diese Dateien gehören **nicht** zur unveränderten GOG-Setup-EXE.

Die Dateien liegen in der ursprünglichen relativen Projektstruktur unter diesem `source/`-Verzeichnis. Damit lassen sich Implementierung, Hashprüfungen, Übersetzungspipeline und Sicherheitsverhalten untersuchen.

## Aktueller, vollständig herunterladbarer Prüfstand

Für Nexus Mods und andere externe Prüfer ist **[Git-Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1)** der geeignete, unveränderliche Projektstand. Dort sind alle **47 Quelldateien unter `source/`**, die deutschen Ressourcen (einschließlich Delta, SRT und XML), die Bauskripte und die ScummVM-Korrekturen enthalten. **[Ganzes v1.0.1-Archiv herunterladen](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip)**.

Das separate **GOG-Source-ZIP `Harvester_GOG_Deutsch_Source_v1.0.0.zip`** im gemeinsamen Release dokumentiert einen älteren Stand. Es ist **nicht** das maßgebliche Quellarchiv für **ScummVM v1.0.1**. Die Anleitung [Quellcodeprüfung für Nexus Mods](../docs/QUELLCODE_PRUEFUNG_NEXUS.md) beschreibt die Zuordnung von EXEs, Quelltext, Übersetzungsdateien, Builds und bekannten Grenzen.

## Programmcode, Delta und Übersetzungsdaten

Dieses `source/`-Verzeichnis enthält ausschließlich **Programmquelltext und technische Tests**. Die deutschen Übersetzungsressourcen liegen jetzt ebenfalls öffentlich vor, jedoch **getrennt vom reinen Source-ZIP**:

- [Geprüftes Delta-ZIP](../resources/delta/Harvester_GOG_Deutsch_Delta_v1.0.0.zip): 20 Binärdeltas für 18 übersetzte Zielressourcen; exakt die Bytes des vom Nutzer getesteten Buildstands
- [128 deutsche SRT-Dateien](../resources/payload/subtitles/) mit 10-/11-px-Modi und vier Endsequenzen
- [Regeln.xml](../resources/payload/Regeln.xml) und [VideoManifest.xml](../resources/payload/VideoManifest.xml)
- [Kompilierter eigener C#-Patcher](../resources/payload/Harvester_Deutsch_Patcher.exe) mit [vollständigem C#-Quellcode](src/windows/)

Der öffentliche Code plus die Ressourcen ermöglichen es, mit [dem Windows-Bauskript](../build/Harvester_aus_Quellcode_bauen.cmd) **den GOG-Installer eigenständig nachzubauen**. Dabei wird die veröffentlichte, bereits kompilierte C#-Hilfs-EXE aus `resources/payload/` mitverwendet; ihr Quellcode liegt unter `source/src/windows/` vor. Ein **bitidentischer Neubau dieser Hilfs-EXE** oder der ursprünglichen GOG-Setup-EXE ist nicht nachgewiesen. Der **ScummVM-Konverter** wird separat aus Python-Quellen gemäß [Windows-GitHub-Actions-Workflow](../.github/workflows/harvester-scummvm-v101-windows-qa.yml) gebaut.

**Nicht veröffentlicht** werden Original-GOG-Spielmedien, unveränderte FST/MP4-Videos, fertige komplette Spielinstallationen, originale EXEs und Savegames sowie private Git-Historie und Entwicklerprotokolle. Zur *Installation* wird weiterhin eine eigene unterstützte englische GOG-Version benötigt.

Das Delta enthält aus dem Originalspiel abgeleitete Übersetzungsdaten. Seine Veröffentlichung bedeutet **keine urheberrechtliche Genehmigung** durch die Rechteinhaber. Die privaten historischen Kennzeichen in `bundle.json` bleiben aus Gründen der Byteidentität erhalten; Einzelheiten in der [Ressourcen-README](../resources/README.md).

## Prüfbarkeit und Tests

Die veröffentlichte Installer-EXE wurde auf Windows mit einer unterstützten englischen GOG-Installation getestet: Deutsch, bestehende Spielstände und Videountertitel funktionierten. Die ursprünglichen Windows-CI-Tests wurden im privaten Entwicklungsprojekt ausgeführt; zahlreiche technische Tests liegen hier als Quellcode bei. Einige Tests benötigen die [nun getrennt veröffentlichten Ressourcen](../resources/README.md); aus dem `source/`-Verzeichnis allein sind sie daher nicht zwingend ausführbar. Das öffentliche Buildskript fügt Code und Ressourcen vor dem Bau zusammen.

Die **frische GOG-Installation** prüft die Dateiinhalte unabhängig vom frei wählbaren ursprünglichen GOG-Ordnernamen und Laufwerk. Aus Sicherheitsgründen wird der automatisch erzeugte Zielordner `Harvester GOG Deutsch` fest benannt. **Bei Wiederaufnahme einer abgebrochenen GOG-Installation** müssen die Quell-/Zielpfade im bestehenden XML-Nachweis weiterhin passen. Der **ScummVM-Konverter v1.0.1** akzeptiert nachträglich verschobene vollständige GOG-Installationen, wenn die SHA-256-Prüfungen bestanden werden. Interne Originaldateinamen und die unterstützte GOG-Dateiversion sind in beiden Programmen fest vorgegeben.

**Wichtig:** Der gemeinsame [Spieler-Release `v1.0.0`](../../releases/tag/v1.0.0) wurde angelegt, **bevor der Quellcode veröffentlicht wurde**. Sein automatisches GitHub-Archiv `Source code (zip)` enthält deshalb nur die damaligen README-/Release-Texte. Das zusätzliche `Harvester_GOG_Deutsch_Source_v1.0.0.zip` ist ein historischer Quellstand und enthält **nicht den aktuellen ScummVM-Fix**. Für eine vollständige externe Prüfung unbedingt das **[gesamte Git-Tag v1.0.1 als ZIP](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip)** verwenden (47 Quelldateien, Ressourcen und Bauskripte). Weitere Hinweise: [Technische Quellcodeprüfung für Nexus](../docs/QUELLCODE_PRUEFUNG_NEXUS.md). Der alte Git-Tag wird nicht rückwirkend verändert.

## Lizenz und Rechte

Der Programmcode wird zur **öffentlichen Einsicht** bereitgestellt. Es wurde noch **keine ausdrücklich freie Softwarelizenz** für alle Teile vergeben; öffentliche Sichtbarkeit bedeutet nicht automatisch uneingeschränkte Wiederverwendung. Die Rechte am Spiel sowie an originalen bzw. abgeleiteten Spielinhalten liegen bei den jeweiligen Rechteinhabern. Das Projekt ist inoffiziell und nichtkommerziell.

Wer nur **spielen** möchte, benötigt nicht diesen Quellcode, sondern den fertigen Installer aus dem [v1.0.0-Release](../../releases/tag/v1.0.0) und seine eigene unterstützte englische GOG-Installation.
