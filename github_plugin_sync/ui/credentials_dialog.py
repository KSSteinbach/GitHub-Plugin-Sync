# -*- coding: utf-8 -*-
"""Dialog to manage stored GitHub credential profiles."""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core.credentials import CredentialManager


def tr(message: str) -> str:
    return QCoreApplication.translate("GitHubPluginSync", message)


class CredentialsDialog(QDialog):
    """Simple manager for credential profiles (list, add, remove)."""

    def __init__(self, parent=None, manager: CredentialManager = None):
        super().__init__(parent)
        self.setWindowTitle(tr("GitHub credentials"))
        self.setWindowModality(Qt.WindowModal)
        self.manager = manager or CredentialManager()
        self._build_ui()
        self._reload_profiles()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(tr(
            "Manage stored GitHub credential profiles. Tokens are kept in "
            "QGIS's authentication database and protected by the QGIS "
            "master password."
        ))
        info.setWordWrap(True)
        layout.addWidget(info)

        if not self.manager.encryption_available:
            warn = QLabel(tr(
                "Warning: QGIS's authentication manager is unavailable. "
                "Credentials cannot be stored in this session."
            ))
            warn.setStyleSheet("color: #a65a00;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(tr("Profile:")))
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(False)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo, 1)
        self.delete_btn = QPushButton(tr("Delete"))
        self.delete_btn.clicked.connect(self._on_delete)
        profile_row.addWidget(self.delete_btn)
        layout.addLayout(profile_row)

        group = QGroupBox(tr("Profile details"))
        form = QFormLayout(group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("e.g. personal, work"))
        form.addRow(tr("Name:"), self.name_edit)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText(tr("GitHub username (optional)"))
        form.addRow(tr("Username:"), self.user_edit)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText(tr("Personal access token"))
        form.addRow(tr("Token:"), self.token_edit)

        layout.addWidget(group)

        buttons = QDialogButtonBox()
        self.save_btn = buttons.addButton(tr("Save"), QDialogButtonBox.ApplyRole)
        self.save_btn.clicked.connect(self._on_save)
        buttons.addButton(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _reload_profiles(self, select: str = ""):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem(tr("<new profile>"), "")
        for name in self.manager.list_profiles():
            self.profile_combo.addItem(name, name)
        if select:
            idx = self.profile_combo.findData(select)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        self._on_profile_changed(self.profile_combo.currentIndex())

    def _on_profile_changed(self, _index: int):
        profile = self.profile_combo.currentData() or ""
        if not profile:
            self.name_edit.clear()
            self.user_edit.clear()
            self.token_edit.clear()
            self.delete_btn.setEnabled(False)
            self.name_edit.setEnabled(True)
            return
        data = self.manager.load(profile) or {}
        self.name_edit.setText(profile)
        self.name_edit.setEnabled(False)
        self.user_edit.setText(data.get("username", ""))
        self.token_edit.setText(data.get("token", ""))
        self.delete_btn.setEnabled(True)

    def _on_save(self):
        profile = self.name_edit.text().strip()
        if not profile:
            QMessageBox.warning(
                self, tr("Missing name"),
                tr("Please provide a name for the profile."),
            )
            return
        token = self.token_edit.text()
        if not token:
            QMessageBox.warning(
                self, tr("Missing token"),
                tr("A personal access token is required."),
            )
            return
        try:
            self.manager.save(
                profile,
                self.user_edit.text().strip(),
                token,
            )
        except RuntimeError as exc:
            QMessageBox.warning(
                self, tr("Could not save"), str(exc),
            )
            return
        self.token_edit.clear()
        self._reload_profiles(select=profile)

    def _on_delete(self):
        profile = self.profile_combo.currentData() or ""
        if not profile:
            return
        ok = QMessageBox.question(
            self, tr("Delete profile?"),
            tr("Delete credential profile '{name}'?").format(name=profile),
        )
        if ok == QMessageBox.Yes:
            self.manager.delete(profile)
            self._reload_profiles()
