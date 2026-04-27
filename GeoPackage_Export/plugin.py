# -*- coding: utf-8 -*-
"""Plugin-Lifecycle: Menü-/Toolbar-Eintrag und Dialog-Start.

Dieses Modul registriert den Plugin-Eintrag in QGIS (Menü + Toolbar),
lädt die passende Übersetzung und öffnet bei Klick den eigentlichen
Export-Dialog. Die Aufrufe folgen dem Standard-QGIS-Plugin-Schema
(``initGui``/``unload``/``run``).
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class GpkgExportPlugin:
    """QGIS-Plugin-Klasse für den GeoPackage-Export.

    QGIS instanziiert diese Klasse einmalig beim Start (sofern das
    Plugin aktiviert ist) und ruft nacheinander :meth:`initGui` und
    später :meth:`unload` auf.
    """

    def __init__(self, iface):
        """Initialisiert das Plugin und lädt ggf. die passende Übersetzung.

        Args:
            iface: QGIS-Interface-Objekt.
        """
        self.iface = iface
        self.action = None
        self.toolbar = None
        self.translator = None
        self._load_translator()

    def _load_translator(self):
        """Lädt die Qt-Übersetzungsdatei passend zur aktuellen Locale.

        Ermittelt die Locale über ``QgsSettings`` (fällt auf die System-
        Locale zurück) und lädt ``i18n/gpkg_export_<xx>.qm``, sofern
        vorhanden. Existiert keine passende Datei, bleibt der Text auf
        Englisch bzw. in der im Code hinterlegten Sprache (Deutsch).
        """
        try:
            from qgis.core import QgsSettings
            locale_str = QgsSettings().value("locale/userLocale", QLocale.system().name())
        except Exception:
            locale_str = QLocale.system().name()
        locale_short = locale_str[:2]
        plugin_dir = os.path.dirname(__file__)
        qm_path = os.path.join(plugin_dir, "i18n", f"gpkg_export_{locale_short}.qm")
        if os.path.isfile(qm_path):
            self.translator = QTranslator()
            if self.translator.load(qm_path):
                QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        """Wird von QGIS aufgerufen, wenn das Plugin aktiviert wird.

        Baut die Toolbar, den Menü-Eintrag und verbindet sie mit
        :meth:`run`.
        """
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(
            icon,
            QCoreApplication.translate("GpkgExportPlugin", "Save Layers as GeoPackage"),
            self.iface.mainWindow(),
        )
        self.action.setToolTip(
            QCoreApplication.translate(
                "GpkgExportPlugin",
                "GeoPackage Export\nExport vector layers to GeoPackage with style transfer.",
            )
        )
        self.action.triggered.connect(self.run)

        self.toolbar = self.iface.mainWindow().addToolBar(
            QCoreApplication.translate("GpkgExportPlugin", "GeoPackage Export")
        )
        self.toolbar.setObjectName("GpkgExportToolbar")
        self.toolbar.addAction(self.action)

        self.iface.addPluginToMenu(
            QCoreApplication.translate("GpkgExportPlugin", "GeoPackage Export"),
            self.action,
        )

    def unload(self):
        """Wird von QGIS aufgerufen, wenn das Plugin deaktiviert wird.

        Entfernt Menü/Toolbar und den geladenen Translator wieder, damit
        keine Leichen im QGIS-Prozess zurückbleiben.
        """
        self.iface.removePluginMenu(
            QCoreApplication.translate("GpkgExportPlugin", "GeoPackage Export"),
            self.action,
        )
        if self.toolbar:
            self.toolbar.deleteLater()
        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
        self.action = None

    def run(self):
        """Öffnet den GeoPackage-Export-Dialog modal.

        Der Import erfolgt erst hier, damit das Plugin beim QGIS-Start
        nicht unnötig schwere Qt-Widget-Module lädt.
        """
        from .gui.main_dialog import GpkgExportDialog
        dlg = GpkgExportDialog(self.iface)
        dlg.exec_()
