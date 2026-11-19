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

## Was ausdrücklich **nicht** veröffentlicht wird

Dies ist ein **Quellcode-Archiv, keine vollständige reproduzierbare Distribution**. Nicht enthalten sind:

- Das private **binäre Delta-Bundle**, mit dem die lokal geprüften deutschen Ressourcen erstellt werden
- Originale GOG-Spielmedien, CD-Abbilder, MP4-/FST-Videos oder DOSBox-Spieldateien
- Binärdateien der übersetzten Spielressourcen (`payload/Daten/*.bin`)
- Der kompilierte native Patch-Code als `payload/Harvester_Deutsch_Patcher.exe`; der zugehörige **C#-Quellcode** ist jedoch vorhanden
- Die vollständigen Übersetzungs-/Videountertitel-Datendateien und die produktiven `Regeln.xml`-/`VideoManifest.xml`-Daten
- Private Projektunterlagen, Git-Historie, Testergebnisse mit persönlichen Pfaden und historische Test-Installer

Die Binärdaten sind erforderlich, wenn man **dieselbe spielbare deutsche Ausgabe** selbst aus dem Quellcode bauen will. Sie sind Teil des separat bereitgestellten, überprüften Installers, werden jedoch **nicht als eigenständiges Git-Quellpaket** veröffentlicht. Deshalb bitte **nicht** behaupten, aus diesem Ordner allein sei ein identisches Release ohne weitere Ressourcen vollständig reproduzierbar.

## Prüfbarkeit und Tests

Die veröffentlichte Installer-EXE wurde auf Windows mit einer unterstützten englischen GOG-Installation getestet: Deutsch, bestehende Spielstände und Videountertitel funktionierten. Die ursprünglichen Windows-CI-Tests wurden im privaten Entwicklungsprojekt ausgeführt; zahlreiche technische Tests liegen hier als Quellcode bei. Einige Tests benötigen die im öffentlichen Repository ausgelassenen Ressourcen und sind daher **aus diesem öffentlichen Source-Verzeichnis allein nicht zwingend ausführbar**.

Die zentrale Regel bleibt: **SHA-256-Prüfungen beziehen sich auf den Dateiinhalt und sind unabhängig vom Speicherort des Spiels.** Der XML-Prüfnachweis enthält den tatsächlichen Quell- und Zielpfad; sein kompletter SHA-256 darf deshalb nicht als universell erwarteter Wert festgelegt werden.

**Wichtig:** Der Release-Tag `v1.0.0` wurde angelegt, bevor der Quellcode separat veröffentlicht wurde. Der Quellcode für genau diesen getesteten Build liegt hier und wird zusätzlich zum Release verlinkt, ohne den bestehenden Release-Tag rückwirkend zu ändern.

## Lizenz und Rechte

Der Programmcode wird zur **öffentlichen Einsicht** bereitgestellt. Es wurde noch **keine ausdrücklich freie Softwarelizenz** für alle Teile vergeben; öffentliche Sichtbarkeit bedeutet nicht automatisch uneingeschränkte Wiederverwendung. Die Rechte am Spiel sowie an originalen bzw. abgeleiteten Spielinhalten liegen bei den jeweiligen Rechteinhabern. Das Projekt ist inoffiziell und nichtkommerziell.

Wer nur **spielen** möchte, benötigt nicht diesen Quellcode, sondern den fertigen Installer aus dem [v1.0.0-Release](../../releases/tag/v1.0.0) und seine eigene unterstützte englische GOG-Installation.
