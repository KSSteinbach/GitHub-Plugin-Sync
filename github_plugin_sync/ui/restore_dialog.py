# -*- coding: utf-8 -*-
"""Dialog for restoring a plugin from a timestamped backup."""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..core.plugin_replacer import BackupEntry, PluginReplacer


def tr(message: str) -> str:
    return QCoreApplication.translate("GitHubPluginSync", message)


class RestoreDialog(QDialog):
    """Let the user pick a plugin backup and restore it."""

    def __init__(self, replacer: PluginReplacer, parent=None):
        super().__init__(parent)
        self.replacer = replacer
        self.setWindowTitle(tr("Restore plugin from backup"))
        self.setWindowModality(Qt.WindowModal)
        self.resize(540, 500)

        self._build_ui()
        self._refresh_plugins()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(tr(
            "Select a plugin and choose one of its backups to restore. "
            "The current plugin files will be backed up automatically "
            "before the restore takes place."
        ))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # --- Plugin selection ---
        plugin_group = QGroupBox(tr("Plugin with backups"))
        plugin_vbox = QVBoxLayout(plugin_group)
        self.plugin_combo = QComboBox()
        self.plugin_combo.currentIndexChanged.connect(self._on_plugin_selected)
        plugin_vbox.addWidget(self.plugin_combo)
        layout.addWidget(plugin_group)

        # --- Backup list ---
        backup_group = QGroupBox(tr("Available backups (newest first)"))
        backup_vbox = QVBoxLayout(backup_group)
        self.backup_list = QListWidget()
        self.backup_list.setAlternatingRowColors(True)
        self.backup_list.currentItemChanged.connect(self._on_backup_selected)
        backup_vbox.addWidget(self.backup_list)
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666;")
        backup_vbox.addWidget(self.path_label)
        layout.addWidget(backup_group, 1)

        # --- Log ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.log.setPlaceholderText(tr("Status messages will appear here."))
        layout.addWidget(self.log)

        # --- Buttons ---
        buttons = QDialogButtonBox()
        self.restore_btn = buttons.addButton(
            tr("↩ Restore selected backup"), QDialogButtonBox.AcceptRole
        )
        self.restore_btn.clicked.connect(self._on_restore)
        self.restore_btn.setEnabled(False)
        buttons.addButton(QDialogButtonBox.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _refresh_plugins(self) -> None:
        self.plugin_combo.blockSignals(True)
        self.plugin_combo.clear()
        backups = self.replacer.list_backups()
        if not backups:
            self.plugin_combo.addItem(tr("(no backups available)"), "")
            self.plugin_combo.setEnabled(False)
            self.restore_btn.setEnabled(False)
        else:
            self.plugin_combo.setEnabled(True)
            for plugin_id in sorted(backups.keys()):
                count = len(backups[plugin_id])
                label = (
                    f"{plugin_id}  "
                    f"({count} {'Backup' if count == 1 else 'Backups'})"
                )
                self.plugin_combo.addItem(label, plugin_id)
        self.plugin_combo.blockSignals(False)
        self._on_plugin_selected(self.plugin_combo.currentIndex())

    def _on_plugin_selected(self, _index: int) -> None:
        self.backup_list.clear()
        self.path_label.setText("")
        self.restore_btn.setEnabled(False)
        plugin_id = self.plugin_combo.currentData() or ""
        if not plugin_id:
            return
        backups = self.replacer.list_backups()
        for entry in backups.get(plugin_id, []):
            item = QListWidgetItem(entry.label)
            item.setData(Qt.UserRole, entry)
            self.backup_list.addItem(item)
        if self.backup_list.count():
            self.backup_list.setCurrentRow(0)

    def _on_backup_selected(self,
                            current: QListWidgetItem, _prev) -> None:
        if current is None:
            self.path_label.setText("")
            self.restore_btn.setEnabled(False)
            return
        entry: BackupEntry = current.data(Qt.UserRole)
        self.path_label.setText(entry.path)
        self.restore_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Restore action
    # ------------------------------------------------------------------
    def _on_restore(self) -> None:
        item = self.backup_list.currentItem()
        if item is None:
            return
        entry: BackupEntry = item.data(Qt.UserRole)

        confirm = QMessageBox.question(
            self,
            tr("Confirm restore"),
            tr(
                "Restore plugin '{plugin}' from the backup dated:\n"
                "  {ts}\n\n"
                "The current plugin files will be backed up first. Continue?"
            ).format(plugin=entry.plugin_id, ts=entry.label),
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            result = self.replacer.restore_backup(entry, try_reload=True)
        except Exception as exc:  # noqa: BLE001
            self._log(tr("Restore failed: {err}").format(err=exc))
            QMessageBox.critical(self, tr("Restore failed"), str(exc))
            return

        for msg in result.messages:
            self._log(msg)

        self._refresh_plugins()

        if result.restart_required:
            QMessageBox.information(
                self,
                tr("Restart required"),
                tr(
                    "Files of '{name}' were restored. Please restart QGIS "
                    "to finish integrating the restored version."
                ).format(name=entry.plugin_id),
            )
        else:
            QMessageBox.information(
                self,
                tr("Restore complete"),
                tr(
                    "Plugin '{name}' was restored and reloaded successfully."
                ).format(name=entry.plugin_id),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, message: str) -> None:
        self.log.appendPlainText(message)
