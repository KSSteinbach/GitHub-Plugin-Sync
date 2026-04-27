# -*- coding: utf-8 -*-
"""Einstiegspunkt des GeoPackage-Export-Plugins für QGIS.

QGIS sucht in jedem Plugin nach einer Funktion ``classFactory``. Sie
erhält die ``iface``-Referenz und muss die Haupt-Plugin-Klasse
zurückgeben. Damit der Import schnell bleibt, erfolgt die eigentliche
Klassen-Import erst innerhalb der Funktion.
"""


def classFactory(iface):
    """Wird von QGIS aufgerufen, um die Haupt-Plugin-Klasse zu erzeugen.

    Args:
        iface: QGIS-Interface-Objekt, das dem Plugin Zugriff auf QGIS
            gibt (Menüs, Toolbars, Kartenfenster …).

    Returns:
        Die initialisierte :class:`GpkgExportPlugin`-Instanz.
    """
    from .plugin import GpkgExportPlugin
    return GpkgExportPlugin(iface)
