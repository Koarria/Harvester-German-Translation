# Harvester – Deutsche Fanübersetzung für ScummVM v1.0.1

Kostenlose, inoffizielle deutsche Fanübersetzung von **Harvester (1996)** für **ScummVM 2026.4.0** unter Windows.

## Download und Installation

**Download:** `Harvester_ScummVM_Deutsch_Konverter_v1.0.1.zip` herunterladen, entpacken und `Harvester_ScummVM_Deutsch_Konverter.exe` starten.

Der Konverter benötigt **keine eigene Python-Installation**. Er verwendet eine **eigene, unterstützte englische GOG-Installation** und eine bereits installierte deutsche GOG-Kopie, um eine zusätzliche ScummVM-Datenkopie zu erstellen. Beide GOG-Installationen bleiben unverändert.

1. Originale englische GOG-Installation auswählen.
2. Bereits installierte deutsche GOG-Version auswählen.
3. Separaten Ausgabe-Oberordner außerhalb beider GOG-Installationen auswählen.
4. Gewünschten Modus auswählen – **11 px ist jetzt vorausgewählt**.
5. „ScummVM-Kopie erstellen“ klicken; danach den erzeugten Ordner in ScummVM als neues Spiel hinzufügen.

## Was enthalten ist

- Deutsche Spieltexte und eingebrannte deutsche Untertitel für die Sprachvideos; die englische Originalvertonung bleibt erhalten.
- Drei auswählbare Videomodi: **11 px (Vorauswahl)**, 10 px und ohne Videountertitel.
- Vorhandene **ScummVM-Spielstände** können weiterverwendet werden. DOSBox-Spielstände werden nicht automatisch importiert.
- SHA-256-Kontrollen der englischen EXE, der deutschen Spiel- und Videoressourcen und der Rendernachweise.
- Ein separater neuer Zielordner; vorhandene GOG-Installationen und Spielstände werden nicht überschrieben.

## Änderungen gegenüber dem ersten ScummVM-Konverter v1.0.0

- **Fehlerbehebung:** Gültige deutsche und englische GOG-Installationen dürfen nach der Installation verschoben oder kopiert worden sein. Historische absolute Pfade im Installationsnachweis blockieren die Konvertierung nicht länger; die inhaltlichen SHA-256-Prüfungen bleiben bestehen.
- **Bedienung:** Der empfohlene Untertitelmodus **11 px** ist standardmäßig ausgewählt.

Der Installer für **GOG/DOSBox v1.0.0** wird durch dieses ScummVM-Update **nicht** verändert und steht weiterhin in [der ursprünglichen Veröffentlichung](https://github.com/Koarria/Harvester-German-Translation/releases/tag/v1.0.0) bereit.

## Empfohlene ScummVM-Einstellungen

OpenGL; Originalbildformat 4:3 beibehalten; zunächst ohne Grafikfilterung, damit kleine Untertitel scharf erscheinen. Weitere Hinweise: [ScummVM-Einstellungen](https://github.com/Koarria/Harvester-German-Translation/blob/main/docs/SCUMMVM_EINSTELLUNGEN.md).

## Quellcode und Rechtliches

Der Konverter ist mit seinem [Python-Quellcode und den Regressionstests](https://github.com/Koarria/Harvester-German-Translation/tree/main/source/tools/developer) öffentlich einsehbar. Das Release-Tag stellt außerdem automatisch den Quellcode als ZIP bereit.

Inoffizielles, kostenloses Fanprojekt ohne Verbindung zu den Entwicklern, Rechteinhabern, GOG oder ScummVM. Es werden keine vollständigen Original-GOG-CDs, Spielvideos oder ausführbaren Originalspiele mitgeliefert. Eine eigene GOG-Version ist erforderlich.
