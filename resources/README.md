# Harvester GOG Deutsch v1.0.0 – Übersetzungsressourcen

Hier liegen die **unveränderten, per SHA-256 geprüften Ressourcen** des unter Windows getesteten Installers vom 19. November 2026.

## Inhalt

| Dateien | Beschreibung |
| --- | --- |
| [`delta/Harvester_GOG_Deutsch_Delta_v1.0.0.zip`](delta/Harvester_GOG_Deutsch_Delta_v1.0.0.zip) | Das originale **328.000-Byte-Delta** des erfolgreich getesteten v1.0.0-Builds |
| [`payload/Regeln.xml`](payload/Regeln.xml) | Ressourcenzuordnung, Original- und Zielprüfsummen der übersetzten Spieldaten |
| [`payload/VideoManifest.xml`](payload/VideoManifest.xml) | Film-/CD-/Untertitel-Zuordnung mit 196 Videoeinträgen |
| [`payload/subtitles/10px/`](payload/subtitles/10px/) | 62 deutsche SRT-Dateien für die 10-px-Variante |
| [`payload/subtitles/11px/`](payload/subtitles/11px/) | 62 deutsche SRT-Dateien für die 11-px-Variante |
| [`payload/subtitles/endings/`](payload/subtitles/endings/) | Vier Untertiteldateien der Endsequenzen |
| [`payload/Harvester_Deutsch_Patcher.exe`](payload/Harvester_Deutsch_Patcher.exe) | Unverändertes native C#-Patcher-Binary aus dem getesteten Build; der [C#-Quellcode](../source/src/windows/) ist ebenfalls veröffentlicht |

**Insgesamt 132 Binär-/XML-/SRT-Dateien** plus diese README. Die 128 SRT-Dateien unterstützen zusammen mit dem Delta und den Laufzeitroutinen 66 Videosequenzen und 132 gerenderte Videovarianten. Für die vier Endsequenzen werden die Untertitel in beiden Modi wiederverwendet.

## Fest geprüfte SHA-256-Werte

- Delta-Bundle: `e690300e4d858992c140d00eceee1ef9e6a4911f32faf98ed7feba93f5794768`
- Native-Patcher-EXE: `9b8fada91a55db9c069309deb69137277cc951b154781523f7571c704f7a62e0`
- `Regeln.xml`: `7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b`

Die Dateien wurden gegen den **genauen privaten Build-Commit `cd0b3c62f1b374055a47ac819e2ace4e5ff46e46`** verglichen. Ein eigenständiger privater CI-Inhaltsaudit bestätigte ZIP-Struktur, 20 Delta-Varianten für 18 Zielressourcen, 48 Ressourcenzuordnungen, 128 SRTs und die Videomanifeste.

## Neu bauen

Für einen Nachbau unter Windows das **gesamte öffentliche Repository** herunterladen oder klonen (nicht nur dieses Verzeichnis). Dann [`build/Harvester_aus_Quellcode_bauen.cmd`](../build/Harvester_aus_Quellcode_bauen.cmd) starten.

Das Skript erstellt in einem separaten Arbeitsordner die erforderliche Projektstruktur aus [`source/`](../source/), den hier vorhandenen Ressourcen und der deutschen [`release/LIES_MICH.txt`](../release/LIES_MICH.txt). Es kontrolliert die festen Hashwerte, installiert bei Zustimmung Python-Bauabhängigkeiten und ruft den bereits getesteten PyInstaller-Bauablauf auf. **Python 3.13 wird nur zum Bauen benötigt.** Das Ergebnis liegt nach erfolgreichem Durchlauf unter `public_build_output/Harvester_GOG_Deutsch_v1.0.0.zip`.

Dieser neu erstellte Installer ist **funktional nachbaubar**, muss aber nicht denselben EXE-Datei-SHA-256 wie die bereits vom Projektinhaber getestete Release-EXE haben (Bauumgebung, PyInstaller/Compiler). **Wer nur spielen möchte, sollte weiterhin das getestete Originalrelease verwenden.**

Zum Erstellen des Installers werden **keine** GOG-Spieldateien benötigt. Erst die spätere Installation beim Spieler verlangt eine eigene unterstützte englische GOG-Fassung.

## Kein Originalspiel enthalten

Es werden **keine** vollständigen Original-CDs, ISOs, unveränderten FST-Filme, GOG-HARVEST.EXE oder Spielstände veröffentlicht. Die Delta-Dateien enthalten zwar keine vollständige GOG-Installation, aber **abgeleitete bzw. übersetzte Spielinhalte**. Deshalb ist die Veröffentlichung nicht automatisch urheberrechtlich freigegeben.

**Historische Bundle-Kennzeichen:** Das byteidentische `bundle.json` enthält weiterhin `private_only: true` und `legal_clearance: false`. Diese Werte stammen vom ursprünglichen Entwicklungs-Bundle und wurden **absichtlich nicht verändert**, um die bereits getesteten Bytes beizubehalten. Sie sind **kein Nachweis einer urheberrechtlichen Genehmigung**. Der öffentliche Installer verwendet exakt dieses Delta bereits eingebettet.

Der Code und die Übersetzungsressourcen sind zur Einsicht verfügbar; eine allgemeine freie Nachnutzungslizenz wurde bisher nicht festgelegt. Alle Rechte am Originalspiel verbleiben bei ihren jeweiligen Rechteinhabern.
