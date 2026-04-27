# GeoPackage Export – QGIS-Plugin

Speichert ausgewählte Vektor-Layer eines QGIS-Projekts als GeoPackage-Dateien
und überträgt dabei die Stile (Farben, Symbologie) in die `layer_styles`-Tabelle
des GeoPackage, damit sie beim späteren Öffnen automatisch geladen werden.

English version: [README.md](README.md).

## Features

- **Drei Speichermodi**
  - Einzeldatei: alle ausgewählten Layer in eine einzige `.gpkg`
  - Multi-Datei: jeder Layer in eine eigene `.gpkg`
  - Anhängen: an ein bestehendes GeoPackage weitere Tabellen hinzufügen
- Automatische Auflösung von Namensdubletten (`Straßen`, `Straßen_2`, …)
- Warnung vor dem Überschreiben bestehender Dateien oder Tabellen
- Optionales Ersetzen der Quell-Layer im Projekt durch die neuen
  GeoPackage-Layer (Stil, Name und Position im Layer-Baum bleiben erhalten)
- Fortschrittsanzeige mit Abbrechen-Knopf bei längeren Exporten
- Unterstützt Memory-Layer und (optional) alle weiteren Vektor-Layer,
  inklusive WFS- und OGC-API-Features-Layer mit pro-Layer wählbarer
  Export-Strategie (Bildschirmausschnitt / Nur Auswahl / Vollständig)

## Installation

1. Den Ordner `GeoPackage_Export/` (nicht das Repo-Root) in das QGIS-Plugin-Verzeichnis kopieren:
   `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/GeoPackage_Export/`
2. QGIS starten, Plugin-Manager öffnen und „GeoPackage Export" aktivieren.

## Nutzung

1. In der Werkzeugleiste auf **Layer als GeoPackage speichern** klicken.
2. Layer auswählen, Speichermodus festlegen, Zielpfad wählen.
3. Optional Stile übernehmen und Quell-Layer im Projekt ersetzen lassen.

## Internationalisierung

Die Plugin-Oberfläche ist standardmäßig auf Englisch. Eine deutsche
Übersetzung wird mitgeliefert und aktiviert sich automatisch, wenn QGIS
mit deutscher Locale läuft. Übersetzungs-Workflow und Hinweise zum
Hinzufügen weiterer Sprachen stehen in
[`GeoPackage_Export/i18n/README.md`](GeoPackage_Export/i18n/README.md).

## Projektstruktur

```
GeoPackage-Export/                ← Repo-Root (README, LICENSE, CI)
└── GeoPackage_Export/            ← was nach QGIS kopiert wird
    ├── __init__.py               classFactory (QGIS-Einstieg)
    ├── plugin.py                 Lifecycle: Menü, Toolbar, Dialog-Start
    ├── metadata.txt              QGIS-Plugin-Metadaten
    ├── icon.png
    ├── core/                     Reine Logik, keine Qt-Widgets
    │   ├── constants.py          Provider-Namen, Tabellen, UI-Maße
    │   ├── path_utils.py         Pfad-/Dateinamen-Helfer
    │   ├── layer_utils.py        Layer-Auswahl im aktuellen Projekt
    │   ├── logging_utils.py      QGIS-Log + Message-Bar
    │   ├── style_utils.py        Stil-Übernahme QGIS ≤ 3.38 / ≥ 3.40
    │   └── export_logic.py       GeoPackage-Schreibarbeit (Hintergrund-Task)
    ├── gui/                      Qt-Widget-Code
    │   ├── main_dialog.py        Hauptdialog
    │   └── ui_dialogs.py         Wrapper um QMessageBox/QFileDialog
    └── i18n/                     Übersetzungen (.ts / .qm / JSON-Mapping)
```

## Mindest-QGIS-Version

3.28
