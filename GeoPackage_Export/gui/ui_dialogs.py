# -*- coding: utf-8 -*-
"""Qt-Dialog-Helfer.

Dünne Wrapper um die Standard-Qt-Dialoge (``QMessageBox``, ``QFileDialog``).
Sie reduzieren das Boilerplate im Haupt-Dialog deutlich und sorgen dafür,
dass alle Meldungen und Dateiauswahlen einheitlich aussehen.

Alle Funktionen nehmen ein ``parent``-Widget entgegen; wird keines
übergeben, erscheint der Dialog als Top-Level-Fenster – für unsere
Zwecke ist fast immer der Dialog selbst der passende Eltern-Widget.
"""

from typing import Optional

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from ..core.path_utils import ensure_gpkg_extension


def show_warning(parent, title: str, text: str) -> None:
    """Zeigt eine Warnung (gelbes Dreieck, nur „OK"-Button).

    Args:
        parent: Eltern-Widget (z. B. der aufrufende Dialog).
        title: Fensterüberschrift.
        text: Angezeigter Meldungstext.
    """
    QMessageBox.warning(parent, title, text)


def ask_yes_no(
    parent,
    title: str,
    text: str,
    default_no: bool = True,
) -> bool:
    """Zeigt einen Ja/Nein-Dialog und liefert die Auswahl als Bool.

    Args:
        parent: Eltern-Widget.
        title: Fensterüberschrift.
        text: Fragestellung.
        default_no: Ist True (Standard), steht der Fokus auf „Nein" –
            sicherer Default bei potenziell zerstörerischen Aktionen
            wie Überschreiben.

    Returns:
        True, wenn der Nutzer „Ja" gewählt hat; sonst False.
    """
    default_button = QMessageBox.No if default_no else QMessageBox.Yes
    reply = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.Yes | QMessageBox.No,
        default_button,
    )
    return reply == QMessageBox.Yes


def pick_directory(
    parent,
    caption: str,
    start_path: str,
) -> Optional[str]:
    """Öffnet einen Verzeichnis-Auswahl-Dialog.

    Args:
        parent: Eltern-Widget.
        caption: Fenstertitel.
        start_path: Pfad, mit dem der Dialog startet.

    Returns:
        Den gewählten Verzeichnis-Pfad oder ``None``, wenn der Nutzer
        abbricht.
    """
    path = QFileDialog.getExistingDirectory(parent, caption, start_path)
    return path or None


def pick_save_gpkg(
    parent,
    caption: str,
    start_path: str,
) -> Optional[str]:
    """Öffnet einen „Speichern unter …"-Dialog für eine GeoPackage-Datei.

    Hängt automatisch ``.gpkg`` an, falls der Nutzer die Endung weglässt
    – sonst würde Qt je nach OS inkonsistent reagieren.

    Args:
        parent: Eltern-Widget.
        caption: Fenstertitel.
        start_path: Vorschlagspfad, mit dem der Dialog startet.

    Returns:
        Den gewählten (und ggf. um ``.gpkg`` ergänzten) Pfad oder
        ``None``, wenn der Nutzer abbricht.
    """
    from ..core.constants import GPKG_FILE_FILTER
    path, _ = QFileDialog.getSaveFileName(
        parent, caption, start_path, GPKG_FILE_FILTER
    )
    if not path:
        return None
    return ensure_gpkg_extension(path)


def pick_open_gpkg(
    parent,
    caption: str,
    start_path: str,
) -> Optional[str]:
    """Öffnet einen „Datei öffnen …"-Dialog, gefiltert auf ``*.gpkg``.

    Args:
        parent: Eltern-Widget.
        caption: Fenstertitel.
        start_path: Vorschlagspfad, mit dem der Dialog startet.

    Returns:
        Den gewählten Pfad oder ``None``, wenn der Nutzer abbricht.
    """
    from ..core.constants import GPKG_FILE_FILTER
    path, _ = QFileDialog.getOpenFileName(
        parent, caption, start_path, GPKG_FILE_FILTER
    )
    return path or None
