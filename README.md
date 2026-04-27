# GeoPackage Export – QGIS plugin

Saves selected vector layers of a QGIS project as GeoPackage files and
transfers the styles (colors, symbology) into the `layer_styles` table of
the GeoPackage so they load automatically when the file is reopened.

Deutschsprachige Version: [README.de.md](README.de.md).

## Features

- **Three save modes**
  - Single file: all selected layers in one `.gpkg`
  - Multi file: each layer in its own `.gpkg`
  - Append: add further tables to an existing GeoPackage
- Automatic resolution of duplicate layer names (`Roads`, `Roads_2`, …)
- Confirmation prompt before overwriting existing files or tables
- Optional replacement of the source layers in the project with the new
  GeoPackage layers (style, name and tree position are preserved)
- Progress bar with cancel button for longer exports
- Works with memory layers and (optionally) all other vector layers,
  including WFS and OGC API – Features layers with per-layer export strategy
  (map canvas extent / selected features only / full)

## Installation

1. Copy the `GeoPackage_Export/` folder (not the repo root) into the QGIS plugin
   directory:
   `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/GeoPackage_Export/`
2. Start QGIS, open the Plugin Manager and enable "GeoPackage Export".

## Usage

1. Click **Save Layers as GeoPackage** in the toolbar.
2. Select layers, pick a save mode, choose the target path.
3. Optionally keep styles and replace the source layers in the project.

## Internationalization

The plugin UI is English by default. A German translation is shipped and
activates automatically when QGIS runs with a German locale. Translation
workflow and instructions for adding further languages live in
[`GeoPackage_Export/i18n/README.md`](GeoPackage_Export/i18n/README.md).

## Project layout

```
GeoPackage-Export/                ← repo root (README, LICENSE, CI)
└── GeoPackage_Export/            ← what gets copied into QGIS
    ├── __init__.py               classFactory (QGIS entry point)
    ├── plugin.py                 lifecycle: menu, toolbar, dialog launch
    ├── metadata.txt              QGIS plugin metadata
    ├── icon.png
    ├── core/                     pure logic, no Qt widgets
    │   ├── constants.py          provider names, tables, UI sizes
    │   ├── path_utils.py         path / filename helpers
    │   ├── layer_utils.py        layer selection in the current project
    │   ├── logging_utils.py      QGIS log + message bar
    │   ├── style_utils.py        style transfer (QGIS ≤ 3.38 / ≥ 3.40)
    │   └── export_logic.py       GeoPackage write work (background task)
    ├── gui/                      Qt widget code
    │   ├── main_dialog.py        main dialog
    │   └── ui_dialogs.py         wrappers around QMessageBox/QFileDialog
    └── i18n/                     translations (.ts / .qm / JSON mapping)
```

## Minimum QGIS version

3.28

---

*Developed in my spare time. If you find it useful, consider [sponsoring on GitHub](https://github.com/sponsors/KSSteinbach) or [via PayPal](https://paypal.me/kssteinbach).*
