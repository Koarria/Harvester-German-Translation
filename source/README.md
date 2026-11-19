# Quellcode der deutschen Harvester-Fanübersetzung

Hier liegt der **einsehbare Programmquellcode** des am 19. November 2026 getesteten Windows-Installers für **Harvester GOG Deutsch v1.0.0**. Der Code wurde aus dem exakt zum erfolgreichen Windows-GitHub-Build gehörenden privaten Git-Commit `cd0b3c62f1b374055a47ac819e2ace4e5ff46e46` übernommen. Der veröffentlichte Setup-Build selbst wird **nicht verändert**.

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

Die Dateien liegen in der ursprünglichen relativen Projektstruktur unter diesem `source/`-Verzeichnis. Damit lassen sich Implementierung, Hashprüfungen, Übersetzungspipeline und Sicherheitsverhalten untersuchen.

## Programmcode, Delta und Übersetzungsdaten

Dieses `source/`-Verzeichnis enthält ausschließlich **Programmquelltext und technische Tests**. Die deutschen Übersetzungsressourcen liegen jetzt ebenfalls öffentlich vor, jedoch **getrennt vom reinen Source-ZIP**:

- [Geprüftes Delta-ZIP](../resources/delta/Harvester_GOG_Deutsch_Delta_v1.0.0.zip): 20 Binärdeltas für 18 übersetzte Zielressourcen; exakt die Bytes des vom Nutzer getesteten Buildstands
- [128 deutsche SRT-Dateien](../resources/payload/subtitles/) mit 10-/11-px-Modi und vier Endsequenzen
- [Regeln.xml](../resources/payload/Regeln.xml) und [VideoManifest.xml](../resources/payload/VideoManifest.xml)
- [Kompilierter eigener C#-Patcher](../resources/payload/Harvester_Deutsch_Patcher.exe) mit [vollständigem C#-Quellcode](src/windows/)

Der öffentliche Code plus die Ressourcen ermöglichen es, mit [dem Windows-Bauskript](../build/Harvester_aus_Quellcode_bauen.cmd) **einen eigenständigen Installer nachzubauen**. Eine bitgenaue SHA-256-Übereinstimmung der neu kompilierten EXE mit der früheren Release-EXE ist jedoch nicht garantiert.

**Nicht veröffentlicht** werden Original-GOG-Spielmedien, unveränderte FST/MP4-Videos, fertige komplette Spielinstallationen, originale EXEs und Savegames sowie private Git-Historie und Entwicklerprotokolle. Zur *Installation* wird weiterhin eine eigene unterstützte englische GOG-Version benötigt.

Das Delta enthält aus dem Originalspiel abgeleitete Übersetzungsdaten. Seine Veröffentlichung bedeutet **keine urheberrechtliche Genehmigung** durch die Rechteinhaber. Die privaten historischen Kennzeichen in `bundle.json` bleiben aus Gründen der Byteidentität erhalten; Einzelheiten in der [Ressourcen-README](../resources/README.md).

## Prüfbarkeit und Tests

Die veröffentlichte Installer-EXE wurde auf Windows mit einer unterstützten englischen GOG-Installation getestet: Deutsch, bestehende Spielstände und Videountertitel funktionierten. Die ursprünglichen Windows-CI-Tests wurden im privaten Entwicklungsprojekt ausgeführt; zahlreiche technische Tests liegen hier als Quellcode bei. Einige Tests benötigen die [nun getrennt veröffentlichten Ressourcen](../resources/README.md); aus dem `source/`-Verzeichnis allein sind sie daher nicht zwingend ausführbar. Das öffentliche Buildskript fügt Code und Ressourcen vor dem Bau zusammen.

Die zentrale Regel bleibt: **SHA-256-Prüfungen beziehen sich auf den Dateiinhalt und sind unabhängig vom Speicherort des Spiels.** Der XML-Prüfnachweis enthält den tatsächlichen Quell- und Zielpfad; sein kompletter SHA-256 darf deshalb nicht als universell erwarteter Wert festgelegt werden.

**Wichtig:** Der Release-Tag `v1.0.0` wurde angelegt, bevor der Quellcode separat veröffentlicht wurde. Der Quellcode für genau diesen getesteten Build liegt hier und wird zusätzlich zum Release verlinkt, ohne den bestehenden Release-Tag rückwirkend zu ändern.

## Lizenz und Rechte

Der Programmcode wird zur **öffentlichen Einsicht** bereitgestellt. Es wurde noch **keine ausdrücklich freie Softwarelizenz** für alle Teile vergeben; öffentliche Sichtbarkeit bedeutet nicht automatisch uneingeschränkte Wiederverwendung. Die Rechte am Spiel sowie an originalen bzw. abgeleiteten Spielinhalten liegen bei den jeweiligen Rechteinhabern. Das Projekt ist inoffiziell und nichtkommerziell.

Wer nur **spielen** möchte, benötigt nicht diesen Quellcode, sondern den fertigen Installer aus dem [v1.0.0-Release](../../releases/tag/v1.0.0) und seine eigene unterstützte englische GOG-Installation.
