# Empfohlene ScummVM-Einstellungen für Harvester Deutsch

Die folgenden Einstellungen sind eine **Empfehlung für ScummVM 2026.4.0**, keine verpflichtenden Vorgaben. Öffne in ScummVM den Harvester-Eintrag, wähle **Spieloptionen → Grafik** und aktiviere bei Bedarf „Globale Grafikeinstellungen überschreiben“, damit andere Spiele unverändert bleiben.

| Option | Empfehlung | Grund |
| --- | --- | --- |
| Grafikmodus | **OpenGL** | Saubere Skalierung des alten Bildes |
| Streckmodus | **An Fenster anpassen (4:3)** oder seitenverhältnistreu anpassen | Keine Breitbild-Verzerrung |
| Grafik filtern | **Aus** für schärfere Schrift, **Ein** für weichere Videooptik | Individueller Kompromiss zwischen Pixelklarheit und Glättung |
| Vollbild | Nach Wunsch | Hat keinen Einfluss auf die deutschen Texte |
| Seitenverhältniskorrektur | Zunächst Standard belassen | Harvester verwendet sowohl 320×200 als auch 640×480; die optische Wirkung prüfen |
| Audio/Musikgerät | **Standard** | ScummVM wählt damit ein passendes Ausgabegerät |
| Shader | Nicht notwendig | Optionaler Retro-Look, nicht Bestandteil der Übersetzung |

**Meine Empfehlung für deutsche Videountertitel: 11 px**. Auf modernen Monitoren sind die Buchstaben damit leichter zu lesen. 10 px ist etwas kleiner, „ohne“ entfernt ausschließlich die Videountertitel. **Alle drei Modi wurden vom Projektinhaber unter ScummVM bestätigt.** Die Untertitel sind in die FST-Videos gerendert: ScummVM kann sie nicht über den üblichen Untertitel-Schalter verändern.

ScummVM verwendet für die *Harvester*-Engine Grafikmodi mit **320×200 und 640×480**. Bei 320×200 kann die Seitenverhältniskorrektur sinnvoll sein; bei 640×480 ist das Bild bereits 4:3. Der empfohlene 4:3-Streckmodus vermeidet Breitbildverzerrung. Für scharfe Schrift zunächst Filterung deaktivieren; für sanftere Videografik einschalten.

Die englische Originalvertonung bleibt erhalten. **Bestehende ScummVM-Spielstände können weitergeladen werden**, wie im erfolgreichen Test bestätigt. Das bedeutet nicht automatisch, dass DOSBox-/GOG-Spielstände übernommen werden können.

### Tastenkombinationen

- **Alt + Enter:** Vollbild ein/aus
- **Strg + F5:** ScummVM-Spielmenü öffnen
- **Strg + Alt + F:** Grafikfilterung umschalten
- **Strg + Alt + S:** Streckmodus umschalten

### Offizielle ScummVM-Dokumentation (Version 2026.4.0)

- [Einstellungen pro Spiel](https://docs.scummvm.org/en/v2026.4.0/use_scummvm/how_to_settings.html)
- [Grafikeinstellungen](https://docs.scummvm.org/en/v2026.4.0/settings/graphics.html)
- [Grafikmodi und Skalierung erklärt](https://docs.scummvm.org/en/v2026.4.0/advanced_topics/understand_graphics.html)
- [Audioeinstellungen](https://docs.scummvm.org/en/v2026.4.0/settings/audio.html)
- [Tastenkombinationen](https://docs.scummvm.org/en/v2026.4.0/use_scummvm/keyboard_shortcuts.html)
