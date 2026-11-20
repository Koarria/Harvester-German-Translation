# Harvester – Deutsche Fanübersetzung (GOG und ScummVM)

**Ein gemeinsamer Downloadbereich für beide Spielvarianten.** Die deutsche Fanübersetzung übersetzt Spieltexte und bietet deutsche Untertitel für 66 Videosequenzen. Die englische Originalvertonung bleibt erhalten.

## Welchen Download brauche ich?

| Spielvariante | Download | Versionsstand |
| --- | --- | --- |
| **GOG / DOSBox** | [`Harvester_GOG_Deutsch_v1.0.0.zip`](https://github.com/Koarria/Harvester-German-Translation/releases/download/v1.0.0/Harvester_GOG_Deutsch_v1.0.0.zip) | **v1.0.0**, unverändert und praktisch getestet |
| **ScummVM** | [`Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip`](https://github.com/Koarria/Harvester-German-Translation/releases/download/v1.0.0/Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip) | **v1.0.1**, korrigiert; **11 px voreingestellt** |

Beide Downloads enthalten eine eigenständige Windows-EXE. Auf dem Spieler-PC ist **keine Python-Installation** erforderlich. Eine eigene, unterstützte englische **GOG-Version von Harvester** ist in beiden Fällen Voraussetzung.

## GOG / DOSBox installieren

1. `Harvester_GOG_Deutsch_v1.0.0.zip` entpacken und `Harvester_GOG_Deutsch_Setup.exe` starten.
2. Die englische GOG-Installation auswählen und die Übersetzung installieren.
3. Im neuen Ordner `Harvester GOG Deutsch` eine der drei Start-CMDs verwenden: **ohne Videountertitel**, **10 px** oder **11 px**.

Die originale englische GOG-Version wird nicht überschrieben. Vorhandene GOG/DOSBox-Spielstände konnten in der deutschen Fassung geladen werden.

## ScummVM vorbereiten

**Zuerst die deutsche GOG-Fassung installieren.** Danach:

1. `Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip` entpacken und die EXE starten.
2. Englische GOG-Installation, bereits installierte deutsche GOG-Version und einen separaten Ausgabe-Oberordner wählen.
3. Den gewünschten Modus auswählen: **11 px ist vorausgewählt**; 10 px und ohne Videountertitel bleiben möglich.
4. Die neue ScummVM-Kopie erstellen und ihren Hauptordner in ScummVM über „Spiel hinzufügen“ auswählen.

Die ScummVM-Konvertierung nutzt die bestehenden Spielressourcen, verändert die GOG-Installationen nicht und führt SHA-256-Prüfungen durch. **Verschobene oder kopierte GOG-Installationen** sind seit Konverter v1.0.1 zulässig, sofern ihre Inhalte gültig sind.

**ScummVM-Spielstände** blieben beim Praxistest kompatibel; **DOSBox-Spielstände** werden nicht automatisch in das ScummVM-Format übernommen. ScummVM erkennt die Spielsprache eventuell als Englisch, obwohl die Texte deutsch sind.

Empfohlene ScummVM-Einstellungen: **OpenGL**, unverzerrtes **4:3**, Grafikfilterung zunächst **aus**. [Ausführliche Einstellungen](https://github.com/Koarria/Harvester-German-Translation/blob/main/docs/SCUMMVM_EINSTELLUNGEN.md).

## Vollständiger Quellcode für Nexus Mods und technische Prüfung

**Für die Prüfung beider Installer den aktuellen, vollständigen [Projektstand v1.0.1 als ZIP](https://github.com/Koarria/Harvester-German-Translation/archive/refs/tags/v1.0.1.zip) verwenden.** Er enthält **47 Dateien unter `source/`** (Programmquellen, Tests und Dokumentation), Übersetzungsressourcen, Delta, Untertiteldateien und Windows-Bauskripte.

- [Quellcode am unveränderlichen Git-Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1/source)
- [Deutsche Ressourcen am Git-Tag v1.0.1](https://github.com/Koarria/Harvester-German-Translation/tree/v1.0.1/resources)
- [Technische Quellcodeprüfung, Nachbau und SHA-256-Werte für Nexus](https://github.com/Koarria/Harvester-German-Translation/blob/main/docs/QUELLCODE_PRUEFUNG_NEXUS.md)

**Achtung bei der Source-Auswahl:** Das zusätzlich angebotene `Harvester_GOG_Deutsch_Source_v1.0.0.zip` ist **nur der historische Quellstand** und enthält nicht die aktuelle ScummVM-v1.0.1-Korrektur. Auch die von GitHub automatisch unter **`Source code (zip)`** und **`Source code (tar.gz)`** angebotenen Archive **dieses gemeinsamen Releases** gehören zum früh angelegten Git-Tag `v1.0.0` und enthalten nicht den später veröffentlichten Quellcode. Für die externe Prüfung daher den **obigen v1.0.1-Link** benutzen.

Das **GOG-v1.0.0-Setup** lässt sich über das öffentliche Windows-Bauskript erneut erstellen, verwendet dabei jedoch eine kompilierte eigene C#-Hilfsdatei, deren Quellcode vorliegt; die bitidentische Reproduktion aller EXEs wurde nicht nachgewiesen. Der **ScummVM-v1.0.1-Konverter** ist über den öffentlichen Windows-CI-Workflow mit **23 Regressionstests** geprüft. `Harvester_GOG_Deutsch_Resources_v1.0.0.zip` enthält die veröffentlichten Übersetzungsressourcen; beide Spieler-Installer und ihre Prüfsummen bleiben unverändert.

## Rechtlicher Hinweis

Kostenloses, inoffizielles Fanprojekt ohne Verbindung zu den ursprünglichen Entwicklern, Publishern, GOG oder ScummVM. Alle Rechte an Harvester liegen bei den Rechteinhabern. Es werden **keine vollständigen Originalspiel-Installationen, CD-Abbilder oder Videos** mitgeliefert. Es wird keine rechtliche Freigabe durch Rechteinhaber behauptet.
