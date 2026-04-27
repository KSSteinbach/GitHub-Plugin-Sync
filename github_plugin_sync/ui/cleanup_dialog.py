# -*- coding: utf-8 -*-
"""Dialog to delete plugin-owned persistent data on demand.

The dialog exposes two groups of controls:

* "Delete now" – run an immediate, user-confirmed cleanup of the
  selected targets.
* "Automatic cleanup on uninstall" – persist a set of targets that the
  plugin will remove at QGIS shutdown when the plugin directory has
  been removed in the meantime.
"""

from __future__ import annotations

from typing import Dict, List

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core import cleanup


def tr(message: str) -> str:
    return QCoreApplication.translate("GitHubPluginSync", message)


class CleanupDialog(QDialog):
    """Interactive cleanup of mappings, backups and legacy files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Clean up plugin data"))
        self.setWindowModality(Qt.WindowModal)
        self.resize(560, 520)

        self._now_checks: Dict[str, QCheckBox] = {}
        self._auto_checks: Dict[str, QCheckBox] = {}

        self._build_ui()
        self._reload()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(tr(
            "Review the data this plugin stores in your QGIS profile and "
            "choose what to delete. GitHub credentials are managed by "
            "QGIS's authentication database and are not affected."
        ))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # --- Delete now ---
        now_group = QGroupBox(tr("Delete now"))
        now_layout = QVBoxLayout(now_group)
        self._now_layout = now_layout
        layout.addWidget(now_group)

        run_btn = QPushButton(tr("Delete selected items now"))
        run_btn.clicked.connect(self._on_run_now)
        layout.addWidget(run_btn)

        # --- Auto cleanup ---
        auto_group = QGroupBox(tr("Automatic cleanup on uninstall"))
        auto_layout = QVBoxLayout(auto_group)
        auto_info = QLabel(tr(
            "When this plugin is uninstalled, the items ticked below are "
            "deleted automatically the next time QGIS closes. Disabling "
            "the plugin or restarting QGIS does not trigger the cleanup."
        ))
        auto_info.setWordWrap(True)
        auto_layout.addWidget(auto_info)
        self._auto_layout = auto_layout
        layout.addWidget(auto_group)

        save_btn = QPushButton(tr("Save auto-cleanup settings"))
        save_btn.clicked.connect(self._on_save_auto)
        layout.addWidget(save_btn)

        # --- Close ---
        buttons = QDialogButtonBox()
        buttons.addButton(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _reload(self) -> None:
        self._rebuild_checkboxes(self._now_layout, self._now_checks,
                                 enabled_keys=None, only_if_exists=True)
        self._rebuild_checkboxes(self._auto_layout, self._auto_checks,
                                 enabled_keys=cleanup.load_auto_cleanup_keys(),
                                 only_if_exists=False)

    def _rebuild_checkboxes(self, layout: QVBoxLayout,
                            store: Dict[str, QCheckBox],
                            *, enabled_keys, only_if_exists: bool) -> None:
        # Remove previous checkboxes (keep any non-checkbox widgets).
        for check in list(store.values()):
            layout.removeWidget(check)
            check.deleteLater()
        store.clear()

        targets = cleanup.list_targets()
        any_visible = False
        for target in targets:
            if only_if_exists and not target.exists:
                continue
            any_visible = True
            label = target.label
            if target.exists:
                label = f"{label}  ({target.human_size})"
            else:
                label = f"{label}  ({tr('not present')})"
            check = QCheckBox(label)
            check.setToolTip(target.description)
            if enabled_keys is not None and target.key in enabled_keys:
                check.setChecked(True)
            if target.key == cleanup.TARGET_STORAGE:
                check.stateChanged.connect(
                    lambda state, s=store: self._on_storage_toggled(s, state))
            layout.addWidget(check)
            store[target.key] = check

        if not any_visible:
            placeholder = QCheckBox(tr("Nothing to clean up."))
            placeholder.setEnabled(False)
            layout.addWidget(placeholder)
            store["__placeholder__"] = placeholder

    def _on_storage_toggled(self, store: Dict[str, QCheckBox], state: int) -> None:
        """When the umbrella target is selected, tick & lock the others."""
        checked = state == Qt.Checked
        for key, check in store.items():
            if key == cleanup.TARGET_STORAGE or key == "__placeholder__":
                continue
            if checked:
                check.setChecked(True)
            check.setEnabled(not checked)

    def _selected_keys(self, store: Dict[str, QCheckBox]) -> List[str]:
        return [key for key, check in store.items()
                if key != "__placeholder__" and check.isChecked()]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_run_now(self) -> None:
        keys = self._selected_keys(self._now_checks)
        if not keys:
            QMessageBox.information(
                self, tr("Nothing selected"),
                tr("Tick at least one item to delete."),
            )
            return

        labels = {t.key: t.label for t in cleanup.list_targets()}
        summary = "\n".join(f"- {labels.get(k, k)}" for k in keys)
        confirm = QMessageBox.question(
            self, tr("Delete selected items?"),
            tr("The following items will be permanently deleted:\n\n"
               "{items}\n\nProceed?").format(items=summary),
        )
        if confirm != QMessageBox.Yes:
            return

        results = cleanup.delete_targets(keys)
        errors = [f"{labels.get(k, k)}: {msg}"
                  for k, msg in results.items() if msg]
        if errors:
            QMessageBox.warning(
                self, tr("Cleanup finished with errors"),
                tr("Some items could not be deleted:\n\n{errors}").format(
                    errors="\n".join(errors)),
            )
        else:
            QMessageBox.information(
                self, tr("Cleanup complete"),
                tr("Selected items were deleted."),
            )
        self._reload()

    def _on_save_auto(self) -> None:
        keys = self._selected_keys(self._auto_checks)
        try:
            cleanup.save_auto_cleanup_keys(keys)
        except OSError as exc:
            QMessageBox.warning(
                self, tr("Could not save"),
                tr("Failed to save auto-cleanup settings: {err}").format(
                    err=exc),
            )
            return
        if keys:
            QMessageBox.information(
                self, tr("Saved"),
                tr("The selected items will be deleted automatically when "
                   "QGIS is closed AND the plugin is uninstalled."),
            )
        else:
            QMessageBox.information(
                self, tr("Saved"),
                tr("Automatic cleanup on uninstall is disabled."),
            )
