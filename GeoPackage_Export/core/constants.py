# -*- coding: utf-8 -*-
"""Zentrale Konstanten des GeoPackage-Export-Plugins.

Alle Werte, die an mehreren Stellen benötigt werden (Provider-Namen,
Datei-Endungen, SQLite-Tabellennamen, UI-Dimensionen, Retry-Parameter),
stehen hier gebündelt. Vorteil: Ein einziger Ort zum Nachschlagen und
Ändern, keine „versteckten" String-Literale im restlichen Code.

Die Konstanten sind thematisch gruppiert; die Kommentare erklären kurz,
wofür der jeweilige Wert steht – auch für Leser, die QGIS oder OGR
noch nicht im Detail kennen.
"""

# ---------------------------------------------------------------------------
# Daten-Provider-Namen
# ---------------------------------------------------------------------------
# Ein „Provider" ist in QGIS die Datenquelle eines Layers. Jeder Layer kennt
# seinen Provider, abrufbar über ``layer.dataProvider().name()``.
# Die hier gelisteten Strings sind die offiziellen Kurznamen, die QGIS
# intern benutzt – sie sind nicht lokalisiert und stabil über Versionen.

PROVIDER_MEMORY = "memory"   # Temporärer Layer nur im RAM (geht beim Schließen verloren).
PROVIDER_OGR = "ogr"         # Datei-basierte Layer via GDAL/OGR (Shapefile, GeoPackage, …).
PROVIDER_WFS = "WFS"         # Web Feature Service – Geodaten über HTTP.
PROVIDER_OAPIF = "OAPIF"     # OGC API – Features, Nachfolger von WFS.

# „Remote"-Provider: Layer, deren Daten über das Netz kommen. Für diese
# ist ein vollständiger Export potenziell teuer (viele Features vom Server).
REMOTE_FEATURE_PROVIDERS = (PROVIDER_WFS, PROVIDER_OAPIF)


# ---------------------------------------------------------------------------
# GeoPackage-Datei-Format
# ---------------------------------------------------------------------------
# GeoPackage (.gpkg) ist eine SQLite-Datenbank mit OGC-Schema, die mehrere
# Layer samt Stilen in einer einzigen Datei speichert.

FILE_EXT_GPKG = ".gpkg"                      # Dateiendung (immer klein prüfen).
DRIVER_GPKG = "GPKG"                         # OGR-Treibername für den Writer.
GPKG_FILE_FILTER = "GeoPackage (*.gpkg)"     # Qt-Filter-String für Datei-Dialoge.


# ---------------------------------------------------------------------------
# Export-Modi für Remote-Layer (WFS/OAPIF)
# ---------------------------------------------------------------------------
# Der Nutzer kann für jeden Remote-Layer wählen, wie viel vom Server geholt
# werden soll. Diese Strings landen als ``currentData()`` in den QComboBoxen
# und werden von ``GpkgExporter._apply_wfs_filter`` ausgewertet.

EXPORT_MODE_FULL = "full"            # Kompletten Datensatz vom Server holen.
EXPORT_MODE_BBOX = "bbox"            # Nur Features im aktuellen Kartenausschnitt.
EXPORT_MODE_SELECTION = "selection"  # Nur im Layer selektierte Objekte.


# ---------------------------------------------------------------------------
# GeoPackage-interne Tabellen- und Spaltennamen
# ---------------------------------------------------------------------------
# Diese Namen sind Teil der GeoPackage-Spezifikation bzw. der QGIS-Style-
# Ablage und werden in direkten SQLite-Queries (``_fix_layer_styles_table``)
# verwendet. Sie sind stabil und dürfen nicht lokalisiert werden.

TABLE_LAYER_STYLES = "layer_styles"                # QGIS-Stiltabelle.
TABLE_GPKG_GEOMETRY_COLUMNS = "gpkg_geometry_columns"  # GPKG-Spec-Tabelle.
COL_F_TABLE_NAME = "f_table_name"                  # Verweis auf Tabellennamen.
COL_F_GEOMETRY_COLUMN = "f_geometry_column"        # Geometrie-Spaltenname.
COL_USE_AS_DEFAULT = "useAsDefault"                # 1 = Standardstil der Tabelle.


# ---------------------------------------------------------------------------
# UI-Dimensionen
# ---------------------------------------------------------------------------
# Gesammelte Pixelwerte für die Layer-Listenzeilen. Änderungen hier wirken
# sich auf das Layout aller Zeilen gemeinsam aus und bleiben so konsistent.

ICON_COL_WIDTH = 19          # Breite der Icon-Spalten (Status, Geometrie).
ICON_PIXMAP_SIZE = 16        # Kantenlänge des Icons in der Zelle.
MIN_ROW_HEIGHT = 22          # Unterer Anschlag für die Zeilenhöhe.
TITLE_FONT_POINT_SIZE = 13   # Schriftgröße der Dialog-Überschrift.


# ---------------------------------------------------------------------------
# Retry-Parameter für SQLite-Korrektur
# ---------------------------------------------------------------------------
# Wenn QGIS die Datei gerade noch geöffnet hält, kann SQLite „database is
# locked" melden. Deshalb versuchen wir es kurz hintereinander mehrfach.

SQLITE_LOCK_RETRY_ATTEMPTS = 3     # Maximale Versuche bei „database is locked".
SQLITE_LOCK_BASE_DELAY_S = 0.2     # Basis-Wartezeit in Sekunden (wird pro Versuch hochgezählt).


# ---------------------------------------------------------------------------
# Logging-Kategorie
# ---------------------------------------------------------------------------
# Kategorie-Tag, unter dem Meldungen im QGIS-Log auftauchen
# (Registerreiter „GPKG Export" im QGIS-Meldungsfenster).

LOG_CATEGORY = "GPKG Export"
