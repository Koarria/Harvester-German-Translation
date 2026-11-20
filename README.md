# Harvester – Deutsche Fanübersetzung (GOG und ScummVM)

Inoffizielle, kostenlose deutsche Fanübersetzung für **Harvester (1996)**.

Diese Fanübersetzung bietet deutsche Spieltexte und deutsche Untertitel für die **66 Videosequenzen** des Spiels. Die englische Originalvertonung bleibt erhalten.

## Downloads

**Ein gemeinsamer Release für beide Varianten:** Der ursprüngliche **GOG-/DOSBox-Installer v1.0.0** und der aktualisierte **ScummVM-Konverter v1.0.1** stehen auf [derselben Downloadseite](../../releases/tag/v1.0.0).

| Variante | Download | Verwendung |
| --- | --- | --- |
| **GOG / DOSBox** | [`Harvester_GOG_Deutsch_v1.0.0.zip`](../../releases/download/v1.0.0/Harvester_GOG_Deutsch_v1.0.0.zip) | Installiert die deutsche GOG-Fassung mit drei Startmöglichkeiten |
| **ScummVM** | [`Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip`](../../releases/download/v1.0.0/Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip) | Erstellt eine separate ScummVM-Datenkopie; **11 px ist vorausgewählt** |

Beide Programme sind eigenständige Windows-EXEs und benötigen bei Spielern **kein Python**. Der GOG-Installer bleibt unverändert. Die gemeinsamen Release-Assets enthalten außerdem die Übersetzungsressourcen und ein historisches GOG-Quellcodearchiv; **den vollständigen aktuellen Quellstand für beide Programme** gibt es separat als [Projektarchiv v1.0.1](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip).

## Harvester Deutsch unter ScummVM

**ScummVM v1.0.1:** Verschobene GOG-Installationen mit unveränderten Spieldateien werden akzeptiert; die Integritätsprüfung bleibt bestehen. **11 px** ist die neue Vorauswahl. Der GOG-Installer v1.0.0 ist unverändert. **Beide Downloads findest du unter demselben Release v1.0.0; die jeweiligen Versionsnummern stehen in den Dateinamen.**

Für [ScummVM 2026.4.0](https://www.scummvm.org/downloads/) gibt es jetzt einen zusätzlichen **deutschen Konverter**. Die ScummVM-Fassung wurde vom Projektinhaber unter Windows mit **allen drei Modi (ohne Videountertitel, 10 px und 11 px)** erfolgreich getestet. Deutsche Spieltexte, Videountertitel in den entsprechenden Modi und das Laden vorhandener **ScummVM-Spielstände** funktionieren.

1. Zunächst die deutsche GOG-Fassung über `Harvester_GOG_Deutsch_Setup.exe` installieren.
2. Den zusätzlichen ScummVM-Konverter herunterladen und starten.
3. Originale englische GOG-Installation, deutsche GOG-Installation und einen **neuen Ausgabe-Oberordner** auswählen.
4. Den gewünschten Videomodus wählen (**11 px vorausgewählt**, alternativ 10 px oder ohne Videountertitel) und die ScummVM-Datenkopie erstellen.
5. Im ScummVM-Launcher **Spiel hinzufügen** wählen und den neu erstellten Ordner `Harvester ScummVM Deutsch ...` auswählen.

**Spielstände:** ScummVM-Spielstände blieben beim Nutzertest kompatibel. Eine automatische Übernahme von **DOSBox-Spielständen** ist dagegen nicht vorgesehen. Die Originaldateien werden nicht überschrieben. ScummVM kann wegen der englischen Original-EXE die Sprache als Englisch erkennen, obwohl die Spieltexte deutsch sind.

**[Empfohlene ScummVM-Grafik-, Audio- und Untertitel-Einstellungen](docs/SCUMMVM_EINSTELLUNGEN.md)** sind zusätzlich im Downloadpaket enthalten: OpenGL, seitenverhältnistreues 4:3 und zunächst ausgeschaltete Grafikfilterung für scharfe Untertitel.

## Quellcode und deutsche Übersetzungsdaten

**Der aktuelle Projektstand für die technische Prüfung beider Installer ist [Git-Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1)** mit 47 Quelldateien, Übersetzungsressourcen und Windows-Bauskripten. [Komplettes Archiv herunterladen](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip).

- [Programmquellcode](source/README.md) – Python-Installer, FST-Renderer, C#-Patcher, Hashprüfungen und Tests
- [Übersetzungsressourcen](resources/README.md) – das geprüfte Delta-Bundle, 128 deutsche SRT-Dateien, zwei XML-Manifeste und der eigene C#-Patcher
- [Installer aus Quellcode bauen](build/Harvester_aus_Quellcode_bauen.cmd) – Windows-Bauskript für den GOG-Installer
- [Technische Quellcodeprüfung für Nexus Mods](docs/QUELLCODE_PRUEFUNG_NEXUS.md) – Zuordnung der veröffentlichten EXEs, Hashes, Windows-CI-Builds und bekannte Grenzen

Auf der [gemeinsamen Release-Seite](../../releases/tag/v1.0.0) stehen **beide getesteten Spieler-Installer**, das GOG-v1.0.0-Source-ZIP und die Übersetzungsressourcen. Das zusätzliche `Harvester_GOG_Deutsch_Source_v1.0.0.zip` dokumentiert jedoch **einen älteren Stand** und enthält nicht die aktuellen ScummVM-v1.0.1-Korrekturen. Auch GitHubs automatisch zum Release `v1.0.0` angebotene `Source code`-Archive sind nicht der vollständige Quellcode; für externe Prüfungen bitte das oben verlinkte **v1.0.1-Projektarchiv** verwenden. Zum Spielen braucht man lediglich den passenden Installer und die eigene englische GOG-Version – weder Python noch separate Delta-Dateien.

Die ursprünglich getestete **GOG-v1.0.0-EXE** wurde nicht verändert. Ein neuer Build aus Quellen benötigt Python 3.13 und kann technisch einen anderen EXE-SHA-256 erzeugen. Die deutschen Delta-Ressourcen enthalten Bearbeitungen des Originalspiels; ihre Veröffentlichung ist keine automatische urheberrechtliche Freigabe.

## Voraussetzungen

- Eine eigene, unterstützte englische **GOG-Version von Harvester**
- **Windows**
- Genügend freier Speicherplatz für eine separate deutsche Spielkopie

Andere Fassungen (z. B. Steam oder CD-Versionen) werden nicht pauschal unterstützt.

## Installation

1. `Harvester_GOG_Deutsch_Setup.exe` starten.
2. Den Ordner der englischen GOG-Installation und den gewünschten übergeordneten Zielordner auswählen.
3. Auf **„Deutsch installieren“** klicken und die Sicherheitsabfrage mit `JA` bestätigen.
4. Der Installer prüft die Spieldateien automatisch per SHA-256. Erst danach erstellt er im gewählten Ziel den neuen Ordner `Harvester GOG Deutsch`.

Die englische Installation wird nicht überschrieben. Bereits vorhandene deutsche Zielordner werden ebenfalls nicht überschrieben.

## Spiel starten

Im neu erstellten Ordner `Harvester GOG Deutsch` stehen drei Startdateien bereit:

| Startdatei | Wirkung |
| --- | --- |
| `Harvester_Deutsch_ohne_Videountertitel.cmd` | Deutsche Spieltexte, ohne Videountertitel |
| `Harvester_Deutsch_mit_10px_Videountertiteln.cmd` | Deutsche Spieltexte und 10-px-Videountertitel |
| `Harvester_Deutsch_mit_11px_Videountertiteln.cmd` | Deutsche Spieltexte und 11-px-Videountertitel |

Die englische Sprachausgabe bleibt erhalten. Die Videountertitel geben gesprochene Dialoge wieder. Einige Beschriftungen und Grafiken bleiben englisch.

## Getesteter Umfang

Der Installer wurde mit einer englischen GOG-Installation unter Windows getestet. Bestätigt wurden die erfolgreiche Erstellung der deutschen Spielkopie, deutsche Spieltexte, das Laden bestehender Spielstände und die Anzeige deutscher Videountertitel.

Die automatische Installationsprüfung umfasst 66 Videoquellen, 132 Untertitelvarianten (10/11 px), sechs Video-CD-Abbilder und drei Startmöglichkeiten. Nicht jede einzelne Videosequenz wurde im letzten Test erneut durchgespielt.

## Hinweis

Dies ist ein **inoffizielles, nichtkommerzielles Fanprojekt** und steht in keiner Verbindung zu den Entwicklern, Publishern oder GOG. Die Rechte am Originalspiel liegen bei ihren jeweiligen Rechteinhabern. Es wird keine vollständige Original-GOG-Installation mitgeliefert.

Die Fanübersetzung ersetzt nicht den Erwerb des Spiels.
