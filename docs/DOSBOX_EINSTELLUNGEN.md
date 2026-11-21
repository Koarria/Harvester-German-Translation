# DOSBox-Grafikeinstellungen in Harvester GOG Deutsch

Die **GOG-/DOSBox-Fassung** dieser Fanübersetzung wird als **separate Spielkopie** in den Ordner `Harvester GOG Deutsch` installiert. Die drei deutschen Startdateien verwenden die **DOSBox-Dateien aus diesem deutschen Ordner**, nicht automatisch die später angepassten Einstellungen der englischen GOG-Installation.

Das gilt nur für die **GOG-/DOSBox-Version**. Wer die optionale ScummVM-Fassung spielt, stellt Grafik und Audio direkt in ScummVM ein: [ScummVM-Einstellungen](SCUMMVM_EINSTELLUNGEN.md).

## So passt du die Grafik an

1. Harvester und DOSBox vollständig beenden.
2. Den deutschen Spielordner `Harvester GOG Deutsch` öffnen.
3. **`dosbox_harvester.conf` sichern**, beispielsweise als `dosbox_harvester.conf.bak`.
4. **Die Originaldatei `dosbox_harvester.conf`** mit einem Texteditor (z. B. Windows-Editor) öffnen und die gewünschten Einstellungen ändern.
5. Datei speichern und Harvester wie gewohnt über eine der drei **deutschen CMD-Startdateien** öffnen.

Die häufig benötigten DOSBox-Optionen befinden sich typischerweise in folgenden Abschnitten der Konfiguration:

| Einstellung | DOSBox-Option | Zweck |
| --- | --- | --- |
| Vollbild | `[sdl]` → `fullscreen` | `true` = Vollbild, `false` = Fenster |
| Grafikmodus | `[sdl]` → `output` | Ausgabemethode, z. B. `overlay` |
| Fensterausgabe | `[sdl]` → `windowresolution` | Fensterauflösung |
| Doppelpufferung | `[sdl]` → `fulldouble` | Double Buffering, sofern unterstützt |
| Seitenverhältnis | `[render]` → `aspect` | `true` = Seitenverhältniskorrektur aktivieren |
| Skalierung | `[render]` → `scaler` | Zum Beispiel `normal2x` |
| Mausgeschwindigkeit | `[sdl]` → `sensitivity` | Maus-Empfindlichkeit |

Dies sind **Beispiele**, keine zwingenden Vorgaben. Vorhandene Einträge bearbeiten und nicht blind doppelte Optionen hinzufügen. Der verwendete DOSBox-Build bestimmt, welche Grafikmodi unterstützt werden. Bei Darstellungsproblemen die gesicherte Konfiguration wiederherstellen.

## Warum drei weitere .conf-Dateien vorhanden sind

Die drei deutschen CMD-Starter laden jeweils **zwei** Konfigurationen, zuerst die allgemeine `dosbox_harvester.conf`, danach die zum Videomodus gehörende Zusatzdatei:

| Startdatei | Zusatzkonfiguration |
| --- | --- |
| `Harvester_Deutsch_ohne_Videountertitel.cmd` | `dosbox_harvester_single_ohne_VideoUT.conf` |
| `Harvester_Deutsch_mit_10px_Videountertiteln.cmd` | `dosbox_harvester_single_10px.conf` |
| `Harvester_Deutsch_mit_11px_Videountertiteln.cmd` | `dosbox_harvester_single_11px.conf` |

Die Zusatzdateien wählen insbesondere die für den Modus passenden **CD-Abbilder**. **Diese Dateien und die CMD-Starter für normale Grafikänderungen nicht bearbeiten**, sonst können Start oder Untertitelmodus beeinträchtigt werden. Wenn eine Option sowohl in der allgemeinen als auch der später geladenen Zusatzdatei vorkommt, kann der zuletzt geladene Eintrag Vorrang haben.

## Warum Änderungen am englischen GOG Configurator nicht automatisch wirken

Beim Erstellen der deutschen Spielkopie werden die unterstützten GOG-DOSBox-Dateien zunächst aus der englischen Installation übernommen und die drei deutschen Startvarianten ergänzt. **Spätere** Änderungen am Konfigurator der englischen Version aktualisieren die separate deutsche Spielkopie **nicht**.

Es ist **nicht erforderlich**, die Mod neu zu installieren, um gewöhnliche DOSBox-Grafikeinstellungen anzupassen. Bearbeite stattdessen die Konfiguration im **deutschen Spielordner**. Eine modifizierte Installationsdatei kann bei späteren Integritäts- oder Wiederaufnahmeprüfungen vom ursprünglichen Prüfnachweis abweichen; deshalb eine unveränderte Sicherung behalten.

Die Anleitung erklärt die durch den veröffentlichten Quellcode belegte Aufrufreihenfolge der drei CMD-Dateien. Die Bedienung des grafischen DOSBox Configurators **innerhalb der deutschen Kopie** wurde nicht separat getestet und wird daher hier nicht vorausgesetzt.
