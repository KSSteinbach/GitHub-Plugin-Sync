# -*- coding: utf-8 -*-
"""Pfad- und Dateinamen-Helfer.

Kleine Hilfsfunktionen rund um Dateipfade, die vorher an mehreren Stellen
im Dialog-Code dupliziert waren. Bewusst ohne Qt-Abhängigkeit gehalten,
damit dieses Modul auch vom reinen Logik-Teil (``export_logic.py``)
genutzt werden kann.
"""

import os

from qgis.core import QgsProject

from .constants import FILE_EXT_GPKG


def ensure_gpkg_extension(path: str) -> str:
    """Hängt ``.gpkg`` an, falls der Pfad noch keine GeoPackage-Endung hat.

    Der Vergleich ist groß-/klein-unabhängig: ``.GPKG`` wird akzeptiert
    wie ``.gpkg``. Ist der Pfad leer, wird er unverändert zurückgegeben.

    Args:
        path: Vom Nutzer eingegebener oder per Datei-Dialog gewählter Pfad.

    Returns:
        Der Pfad mit sicher vorhandener ``.gpkg``-Endung.
    """
    if not path:
        return path
    if path.lower().endswith(FILE_EXT_GPKG):
        return path
    return path + FILE_EXT_GPKG


def is_existing_directory(path: str) -> bool:
    """True, wenn ``path`` ein existierendes Verzeichnis ist.

    Dünner, aber lesbarer Wrapper um ``os.path.isdir`` – leere Pfade
    liefern sauber ``False``, ohne dass der Aufrufer das separat prüfen muss.
    """
    return bool(path) and os.path.isdir(path)


def is_existing_file(path: str) -> bool:
    """True, wenn ``path`` auf eine existierende Datei zeigt."""
    return bool(path) and os.path.isfile(path)


def default_start_dir() -> str:
    """Liefert den bevorzugten Startordner für Datei-/Verzeichnis-Dialoge.

    Vorrang hat der aktuelle QGIS-Projektordner, weil der Nutzer seine
    Exporte meist neben dem Projekt ablegen möchte. Existiert kein
    Projektpfad, wird ein leerer String zurückgegeben – Qt wählt dann
    den zuletzt genutzten Pfad.
    """
    home = QgsProject.instance().homePath()
    if is_existing_directory(home):
        return home
    return ""


def safe_filename(name: str) -> str:
    """Entfernt oder ersetzt Zeichen, die in Dateinamen nicht erlaubt sind.

    Erlaubt bleiben Buchstaben/Ziffern sowie die Zeichen Leerzeichen,
    Punkt, Unterstrich und Bindestrich. Alle anderen werden durch einen
    Unterstrich ersetzt. Führende/nachfolgende Leerzeichen werden
    entfernt.

    Args:
        name: Ausgangsname (meist ein Layername).

    Returns:
        Ein für Windows/macOS/Linux unbedenklicher Dateiname.
    """
    keepchars = (" ", ".", "_", "-")
    return "".join(
        c if (c.isalnum() or c in keepchars) else "_" for c in name
    ).strip()
