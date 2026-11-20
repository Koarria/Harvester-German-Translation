# Harvester – Deutsche Fanübersetzung (GOG und ScummVM) v1.0.0

**Inoffizielle, kostenlose deutsche Fanübersetzung für Harvester (1996).**

Die Mod übersetzt die Spieltexte und ergänzt die englische Originalvertonung um deutsche Untertitel für **66 Videosequenzen**. Die Untertitel stehen in **10 px und 11 px** zur Verfügung. Zwischen den drei Startmöglichkeiten – ohne Videountertitel, 10 px und 11 px – kann vor jedem Spielstart gewählt werden.

## Installation

Die Datei **`Harvester_GOG_Deutsch_Setup.exe`** startet den Installationsassistenten unter Windows. Ein Klick auf **„Deutsch installieren“** genügt: Nach der Bestätigung prüft das Programm **automatisch vor dem Installieren** die englische GOG-Version und alle erforderlichen Daten per SHA-256 und erstellt bei erfolgreicher Prüfung eine **separate deutsche Spielkopie** im Ordner `Harvester GOG Deutsch`. Eine vorherige manuelle SHA-Prüfung ist nicht nötig; sie bleibt optional in den erweiterten Einstellungen verfügbar.

**Erforderlich:** Eine eigene, unterstützte englische GOG-Version von Harvester und genügend freier Speicherplatz. **Python, ein separates Delta-ZIP oder Original-CD-Abbilder als Mod-Download werden nicht benötigt.**

Nach der Installation befinden sich drei Startdateien im neuen Ordner:

- `Harvester_Deutsch_ohne_Videountertitel.cmd` – deutsche Texte ohne Videountertitel
- `Harvester_Deutsch_mit_10px_Videountertiteln.cmd` – mit 10-px-Videountertiteln
- `Harvester_Deutsch_mit_11px_Videountertiteln.cmd` – mit 11-px-Videountertiteln

Das englische Original wird nicht überschrieben; bereits vorhandene deutsche Zielordner werden nicht überschrieben. Vorhandene Spielstände ließen sich im erfolgreichen GOG-Windows-Test weiterhin laden.

## Hinweise

Die **englische Sprachausgabe** bleibt erhalten. Die Videountertitel beziehen sich auf gesprochene Dialoge; einige Grafiken und Beschriftungen bleiben englisch. Unterstützt wird die geprüfte englische GOG-Fassung, nicht pauschal jede andere Spielversion oder Plattform.

Ein einzelner Installationsassistent wurde im Windows-GOG-Test erfolgreich verwendet: deutscher Text sichtbar, bestehende Spielstände ladbar, deutsche Videountertitel sichtbar. Die automatisierten Prüfungen bestätigten 66 Filmquellen, 132 Untertitelvarianten, sechs Video-CD-Abbilder und drei Startmöglichkeiten. Nicht jede einzelne Videosequenz und Startvariante wurde zuletzt separat im Spiel durchlaufen.

## Download

**Empfohlen:** `Harvester_GOG_Deutsch_v1.0.0.zip` herunterladen, entpacken, `LIES_MICH.txt` lesen und `Harvester_GOG_Deutsch_Setup.exe` starten. Das ZIP enthält ausschließlich diese EXE, die Anleitung und eine SHA-256-Prüfsummendatei.

## Rechtlicher Hinweis

Inoffizielles, nichtkommerzielles Fanprojekt ohne Verbindung zu den ursprünglichen Entwicklern, Publishern oder GOG. Alle Rechte an Harvester liegen bei den jeweiligen Rechteinhabern. Es wird keine vollständige Original-GOG-Installation mitgeliefert.


## Prüfsumme des getesteten Builds

SHA-256 von `Harvester_GOG_Deutsch_Setup.exe` aus dem erfolgreich getesteten GitHub-Build vom 19. November 2026:

`8c04747dacf74ca7ec1a15fd7a96fc21366f6c74895e743e2f29e467b4b428e9`

Der Wert gilt für exakt diese EXE-Datei, nicht für das gesamte ZIP. Die `SHA256SUMS.txt` im Download enthält die zugehörige Prüfsumme.

## Quellcode und Übersetzungsressourcen

Der Quellcode des getesteten Installers ist in [source/](source/README.md) einsehbar. **Das überprüfte Original-Delta-ZIP und die vollständigen deutschen SRT-/XML-Ressourcen** sind jetzt separat unter [resources/](resources/README.md) verfügbar.

Im Release werden ergänzend zwei ZIP-Dateien bereitgestellt:
- `Harvester_GOG_Deutsch_Source_v1.0.0.zip` – Python-/C#-Programmquelltext und Tests
- `Harvester_GOG_Deutsch_Resources_v1.0.0.zip` – Delta, deutsche Untertitel, Manifeste, eigener nativer C#-Patcher

Mit dem [Windows-Bauskript](build/Harvester_aus_Quellcode_bauen.cmd) lässt sich der Installer aus diesen öffentlichen Ressourcen nachbauen. Für den Nachbau wird Python 3.13 benötigt; der SHA-256 einer neu gebauten EXE muss nicht dem ursprünglich getesteten Binary entsprechen.

Das **bereits getestete Installer-ZIP bleibt unverändert**. Weder vollständige GOG-Spielmedien noch originale FST-Filme oder Spielstände sind in den Quellcode-/Ressourcenpaketen enthalten. Das Übersetzungs-Delta enthält urheberrechtlich möglicherweise geschützte Bearbeitungen; eine Freigabe durch Rechteinhaber wird nicht behauptet.


## Zusätzliche ScummVM-Variante (v1.0.0)

**Download:** `Harvester_ScummVM_Deutsch_Konverter_v1.0.0.zip`

Der eigenständige Windows-Konverter erstellt aus einer **eigenen englischen GOG-Version** und der mit unserem GOG-Installer **bereits installierten deutschen Fassung** eine separate Datenkopie für **ScummVM 2026.4.0**. Es gibt drei auswählbare Modi: **ohne Videountertitel**, **10 px** und **11 px**. Keine Python-Installation erforderlich.

**Bestätigt durch den Projektinhaber:** Alle drei Modi funktionieren unter ScummVM; deutsche Spieltexte werden angezeigt, Videountertitel in den entsprechenden Modi funktionieren, und zuvor angelegte **ScummVM-Spielstände** lassen sich weiterhin laden. **DOSBox-/GOG-Spielstände werden nicht automatisch konvertiert.**

Das ZIP enthält den Konverter, `LIES_MICH_SCUMMVM.txt`, `SCUMMVM_EINSTELLUNGEN.txt` und `SHA256SUMS.txt`. Die [ScummVM-Einstellungsempfehlungen](docs/SCUMMVM_EINSTELLUNGEN.md) erläutern OpenGL, 4:3-Darstellung und scharfe gegenüber geglätteter Videografik. Original-Harvester-GOG-Dateien werden nicht mitgeliefert oder überschrieben.

Der [öffentliche Quellcode des ScummVM-Konverters](source/tools/developer/scummvm_converter.py) ist dem getrennten Quellcodepaket beigefügt. Die bestehenden GOG-/DOSBox-/Source-/Resource-Downloads sowie der Release-Tag `v1.0.0` bleiben unverändert.
