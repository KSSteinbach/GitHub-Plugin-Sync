# -*- coding: utf-8 -*-
"""Main plugin class for GitHub Plugin Sync."""

import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class GitHubPluginSyncPlugin:
    """Registers the plugin action and opens the main dialog on demand."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&GitHub Plugin Sync")
        self._translator = None

        self._install_translator()
        self._register_uninstall_cleanup()

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------
    def _install_translator(self):
        locale = QSettings().value("locale/userLocale", QLocale().name())
        if not locale:
            return
        locale = locale[:2]
        qm_path = os.path.join(
            self.plugin_dir, "i18n", f"github_plugin_sync_{locale}.qm"
        )
        if os.path.exists(qm_path):
            self._translator = QTranslator()
            if self._translator.load(qm_path):
                QCoreApplication.installTranslator(self._translator)

    def tr(self, message):
        return QCoreApplication.translate("GitHubPluginSync", message)

    # ------------------------------------------------------------------
    # Auto-cleanup on uninstall
    # ------------------------------------------------------------------
    def _register_uninstall_cleanup(self):
        """Schedule a shutdown-time cleanup if the user opted in.

        QGIS does not expose a dedicated "on uninstall" hook; ``unload``
        also fires on disable and on shutdown. The cleanup module checks
        whether the plugin directory still exists at interpreter exit,
        so a regular shutdown never triggers deletion.
        """
        try:
            from .core.cleanup import register_uninstall_cleanup
        except Exception:  # noqa: BLE001
            return
        try:
            register_uninstall_cleanup(self.plugin_dir)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------
    def initGui(self):  # noqa: N802 (QGIS required name)
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        action = QAction(icon, self.tr("Sync plugin from GitHub…"),
                         self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setWhatsThis(
            self.tr("Replace an installed plugin with files from a GitHub repo"))
        self.iface.addPluginToMenu(self.menu, action)
        self.iface.addToolBarIcon(action)
        self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        if self._translator is not None:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self):
        from .ui.main_dialog import MainDialog

        dlg = MainDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
