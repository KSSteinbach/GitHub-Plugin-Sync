# -*- coding: utf-8 -*-
"""Einheitliches Logging für das GeoPackage-Export-Plugin.

QGIS bietet zwei parallele Ausgabekanäle, zwischen denen man sich gern
vertut:

* ``QgsMessageLog``: persistentes Log-Fenster (Reiter „GPKG Export")
  – für Fehler, Warnungen und technische Details, die der Nutzer
  später nachschlagen möchte.
* ``iface.messageBar()``: kurzlebige Einblendung am oberen Rand des
  Hauptfensters – für Rückmeldungen zum aktuellen Arbeitsschritt.

Dieses Modul kapselt beide Kanäle als dünne Funktionen, damit im
restlichen Code nicht immer Category-Strings und ``Qgis.Info``-Defaults
doppelt hingeschrieben werden müssen.
"""

from qgis.core import Qgis, QgsMessageLog

from .constants import LOG_CATEGORY


def log_message(message: str, level: int = Qgis.Info) -> None:
    """Schreibt eine Meldung ins persistente QGIS-Log.

    Args:
        message: Text, der im Log erscheinen soll.
        level: QGIS-Level (``Qgis.Info``, ``Qgis.Warning``,
            ``Qgis.Critical``). Standard: Info.
    """
    QgsMessageLog.logMessage(message, LOG_CATEGORY, level)


def push_bar_message(
    iface,
    title: str,
    message: str,
    level: int = Qgis.Info,
    duration: int = 0,
) -> None:
    """Zeigt eine Einblendung am oberen Rand des QGIS-Hauptfensters.

    Diese Meldungen sind flüchtig – sie verschwinden nach ``duration``
    Sekunden wieder.

    Args:
        iface: Die QGIS-``iface``-Referenz (aus dem Plugin-Konstruktor).
        title: Fett gesetzter Titelteil vor dem Meldungstext.
        message: Eigentlicher Meldungstext.
        level: QGIS-Level (s. ``log_message``). Standard: Info.
        duration: Anzeigedauer in Sekunden. 0 = bis zum Schließen.
    """
    if iface is None:
        return
    iface.messageBar().pushMessage(title, message, level, duration)
