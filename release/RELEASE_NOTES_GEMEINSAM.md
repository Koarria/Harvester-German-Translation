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

## Weitere Dateien und Quellcode

Die ergänzenden Dateien `Harvester_GOG_Deutsch_Source_v1.0.0.zip` und `Harvester_GOG_Deutsch_Resources_v1.0.0.zip` richten sich an technisch Interessierte; normale Spieler benötigen sie nicht.

Der frei einsehbare [Quellcode auf GitHub](https://github.com/Koarria/Harvester-German-Translation/tree/main/source) enthält auch die **ScummVM-Konverter-Korrekturen und Regressionstests**. Das gesonderte Source-ZIP v1.0.0 dokumentiert den ursprünglichen GOG-Release-Stand. Im gemeinsamen Release steht ausschließlich der aktuelle **ScummVM-Konverter v1.0.1** zum Download bereit.

## Rechtlicher Hinweis

Kostenloses, inoffizielles Fanprojekt ohne Verbindung zu den ursprünglichen Entwicklern, Publishern, GOG oder ScummVM. Alle Rechte an Harvester liegen bei den Rechteinhabern. Es werden **keine vollständigen Originalspiel-Installationen, CD-Abbilder oder Videos** mitgeliefert. Es wird keine rechtliche Freigabe durch Rechteinhaber behauptet.
