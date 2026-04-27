# -*- coding: utf-8 -*-
"""Main dialog: select plugin, repo, branch, validate metadata and replace."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from typing import Optional

from qgis.PyQt.QtCore import QCoreApplication, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..core.credentials import CredentialManager
from ..core.github_client import GitHubClient, GitHubError, RepoRef
from ..core.mappings import MappingManager, PluginMapping
from ..core.metadata_check import compare as compare_metadata
from ..core.plugin_replacer import PluginReplacer
from .cleanup_dialog import CleanupDialog
from .credentials_dialog import CredentialsDialog
from .help_dialog import HelpDialog


def tr(message: str) -> str:
    return QCoreApplication.translate("GitHubPluginSync", message)


# ----------------------------------------------------------------------
# Worker threads
# ----------------------------------------------------------------------
class _BranchesWorker(QThread):
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, client: GitHubClient, repo: RepoRef, parent=None):
        super().__init__(parent)
        self.client = client
        self.repo = repo

    def run(self):
        try:
            branches = self.client.list_branches(self.repo)
            self.finished_ok.emit(branches)
        except GitHubError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _SubdirWorker(QThread):
    finished_ok = pyqtSignal(list)   # list[str] of candidate folder paths
    failed = pyqtSignal(str)

    def __init__(self, client: GitHubClient, repo: RepoRef, branch: str,
                 parent=None):
        super().__init__(parent)
        self.client = client
        self.repo = repo
        self.branch = branch

    def run(self):
        try:
            folders = self.client.find_plugin_folders(self.repo, self.branch)
            self.finished_ok.emit(folders)
        except GitHubError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _DownloadWorker(QThread):
    finished_ok = pyqtSignal(str)    # path to extracted source dir
    failed = pyqtSignal(str)

    def __init__(self, client: GitHubClient, repo: RepoRef, branch: str,
                 dest: str, subdir: str = "", parent=None):
        super().__init__(parent)
        self.client = client
        self.repo = repo
        self.branch = branch
        self.dest = dest
        self.subdir = subdir.strip("/")

    def run(self):
        try:
            root = self.client.download_tarball(self.repo, self.branch, self.dest)
            result_dir = os.path.join(root, self.subdir) if self.subdir else root
            if not os.path.isdir(result_dir):
                self.failed.emit(tr(
                    "Sub-directory '{path}' not found in the downloaded archive."
                ).format(path=self.subdir))
                return
            self.finished_ok.emit(result_dir)
        except GitHubError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ----------------------------------------------------------------------
# Main dialog
# ----------------------------------------------------------------------
class MainDialog(QDialog):
    """The central UI for the plugin."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle(tr("Sync plugin from GitHub"))
        self.setModal(True)
        self.resize(680, 620)

        self.credentials = CredentialManager()
        self.mappings = MappingManager()
        self.replacer = PluginReplacer(self._resolve_plugins_dir())

        self._temp_dir: Optional[str] = None
        self._branch_worker: Optional[_BranchesWorker] = None
        self._download_worker: Optional[_DownloadWorker] = None
        self._subdir_worker: Optional[_SubdirWorker] = None
        self._incoming_metadata_text: Optional[str] = None
        self._downloaded_source_dir: Optional[str] = None
        self._help_dialog: Optional[HelpDialog] = None

        self._build_ui()
        self._populate_plugins()
        self._populate_profiles()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Plugin selector ---
        plugin_group = QGroupBox(tr("Installed plugin"))
        plugin_form = QFormLayout(plugin_group)
        self.plugin_combo = QComboBox()
        self.plugin_combo.setEditable(True)
        self.plugin_combo.lineEdit().setPlaceholderText(tr(
            "Existing plugin, or new folder name to install"
        ))
        self.plugin_combo.currentIndexChanged.connect(self._on_plugin_selected)
        self.plugin_combo.editTextChanged.connect(self._update_install_hint)
        plugin_form.addRow(tr("Target plugin:"), self.plugin_combo)
        self.install_hint = QLabel("")
        self.install_hint.setWordWrap(True)
        plugin_form.addRow("", self.install_hint)
        self.plugins_dir_label = QLabel(self.replacer.plugins_dir)
        self.plugins_dir_label.setWordWrap(True)
        self.plugins_dir_label.setStyleSheet("color: #666;")
        plugin_form.addRow(tr("Plugins directory:"), self.plugins_dir_label)
        layout.addWidget(plugin_group)

        # --- GitHub repo/credentials ---
        gh_group = QGroupBox(tr("GitHub source"))
        gh_form = QFormLayout(gh_group)

        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText(tr("owner/name or full GitHub URL"))
        self.repo_edit.textChanged.connect(self._on_repo_text_changed)
        gh_form.addRow(tr("Repository:"), self.repo_edit)

        cred_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        cred_row.addWidget(self.profile_combo, 1)
        manage_btn = QPushButton(tr("Manage…"))
        manage_btn.clicked.connect(self._on_manage_credentials)
        cred_row.addWidget(manage_btn)
        gh_form.addRow(tr("Credential profile:"), cred_row)

        branch_row = QHBoxLayout()
        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.setMinimumWidth(180)
        branch_row.addWidget(self.branch_combo, 1)
        self.fetch_branches_btn = QPushButton(tr("Load branches"))
        self.fetch_branches_btn.clicked.connect(self._on_fetch_branches)
        branch_row.addWidget(self.fetch_branches_btn)
        gh_form.addRow(tr("Branch:"), branch_row)

        subdir_row = QHBoxLayout()
        self.subdir_combo = QComboBox()
        self.subdir_combo.setEditable(True)
        self.subdir_combo.setMinimumWidth(180)
        self.subdir_combo.lineEdit().setPlaceholderText(
            tr("Optional: sub-folder inside the repository (empty = repo root)")
        )
        # A first empty entry means "use repo root".
        self.subdir_combo.addItem("")
        subdir_row.addWidget(self.subdir_combo, 1)
        self.detect_subdir_btn = QPushButton(tr("Detect"))
        self.detect_subdir_btn.setToolTip(tr(
            "Scan the selected branch for folders containing a metadata.txt"
        ))
        self.detect_subdir_btn.clicked.connect(self._on_detect_subdirs)
        subdir_row.addWidget(self.detect_subdir_btn)
        gh_form.addRow(tr("Sub-directory:"), subdir_row)

        self.remember_check = QCheckBox(
            tr("Remember this repository for the selected plugin"))
        gh_form.addRow("", self.remember_check)

        layout.addWidget(gh_group)

        # --- Log / status ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log.setPlaceholderText(tr("Status messages will appear here."))
        layout.addWidget(self.log, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        # --- Buttons ---
        buttons = QDialogButtonBox()
        self.cleanup_btn = buttons.addButton(
            tr("Cleanup …"), QDialogButtonBox.ActionRole)
        self.cleanup_btn.setToolTip(tr(
            "Delete stored mappings, backups or legacy files."
        ))
        self.cleanup_btn.clicked.connect(self._on_cleanup)
        self.check_btn = buttons.addButton(
            tr("Check metadata"), QDialogButtonBox.ActionRole)
        self.check_btn.clicked.connect(self._on_check_metadata)
        self.replace_btn = buttons.addButton(
            tr("↪ Replace the plugin"), QDialogButtonBox.AcceptRole)
        self.replace_btn.clicked.connect(self._on_replace)
        buttons.addButton(QDialogButtonBox.Close).clicked.connect(self.reject)

        button_row = QHBoxLayout()
        self.help_btn = QPushButton(tr("Help"))
        self.help_btn.setToolTip(tr(
            "Open the plugin help in a separate window."
        ))
        self.help_btn.clicked.connect(self._on_help)
        button_row.addWidget(self.help_btn)
        button_row.addStretch(1)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

    # ------------------------------------------------------------------
    # Population helpers
    # ------------------------------------------------------------------
    def _resolve_plugins_dir(self) -> str:
        try:
            from qgis.core import QgsApplication
            return os.path.join(
                QgsApplication.qgisSettingsDirPath(), "python", "plugins"
            )
        except Exception:  # noqa: BLE001
            return os.path.expanduser("~/.qgis/python/plugins")

    def _populate_plugins(self):
        self.plugin_combo.blockSignals(True)
        self.plugin_combo.clear()
        self.plugin_combo.addItem(tr("<select plugin>"), "")
        for name in self.replacer.list_installed_plugins():
            self.plugin_combo.addItem(name, name)
        self.plugin_combo.blockSignals(False)

    def _populate_profiles(self):
        self.profile_combo.clear()
        self.profile_combo.addItem(tr("<anonymous / public>"), "")
        for name in self.credentials.list_profiles():
            self.profile_combo.addItem(name, name)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_plugin_selected(self, _index: int):
        plugin_id = self._current_plugin_id()
        self._update_install_hint()
        if not plugin_id:
            return
        self._reset_subdir_combo()
        self._reset_branch_combo()
        mapping = self.mappings.get(plugin_id)
        if mapping:
            self.repo_edit.setText(mapping.repo)
            idx = self.profile_combo.findData(mapping.credential_profile)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
            self.remember_check.setChecked(True)
            self._log(tr("Loaded stored mapping for '{name}'.").format(
                name=plugin_id))
        else:
            self.remember_check.setChecked(False)

    def _on_manage_credentials(self):
        dlg = CredentialsDialog(self, self.credentials)
        dlg.exec_()
        current = self.profile_combo.currentData() or ""
        self._populate_profiles()
        idx = self.profile_combo.findData(current)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def _on_help(self):
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def _on_cleanup(self):
        dlg = CleanupDialog(self)
        dlg.exec_()
        # A cleanup run may have removed the mapping for the currently
        # selected plugin; re-apply the selection so stale fields clear.
        plugin_id = self._current_plugin_id()
        if plugin_id:
            self._on_plugin_selected(self.plugin_combo.currentIndex())

    _VALID_PLUGIN_ID = re.compile(r"^[A-Za-z_][\w.\-]*$")

    def _current_plugin_id(self) -> str:
        """The currently selected/typed plugin folder name (may be new)."""
        data = self.plugin_combo.currentData() or ""
        text = self.plugin_combo.currentText().strip()
        # ``currentData`` only returns a value for entries that were added
        # via addItem; for freshly typed text it is empty.
        return (data if data else text).strip()

    def _is_new_install(self, plugin_id: str) -> bool:
        if not plugin_id:
            return False
        return not self.replacer.is_installed(plugin_id)

    def _update_install_hint(self, *_):
        plugin_id = self._current_plugin_id()
        if not plugin_id:
            self.install_hint.setText("")
            return
        if self._is_new_install(plugin_id):
            if self._VALID_PLUGIN_ID.match(plugin_id):
                self.install_hint.setText(tr(
                    "'{name}' is not installed yet – a new plugin folder "
                    "will be created."
                ).format(name=plugin_id))
                self.install_hint.setStyleSheet("color: #1a7f37;")
            else:
                self.install_hint.setText(tr(
                    "'{name}' is not a valid plugin folder name. Use "
                    "letters, digits, '_', '.' or '-' (no spaces/slashes)."
                ).format(name=plugin_id))
                self.install_hint.setStyleSheet("color: #b42318;")
        else:
            self.install_hint.setText("")

    def _current_subdir(self) -> str:
        """Return the trimmed sub-directory path (``""`` means repo root)."""
        return self.subdir_combo.currentText().strip().strip("/")

    def _reset_subdir_combo(self) -> None:
        """Clear the sub-directory combo, leaving only the empty entry."""
        self.subdir_combo.clear()
        self.subdir_combo.addItem("")

    def _reset_branch_combo(self) -> None:
        """Drop any branches loaded from a previous repository."""
        current = self.branch_combo.currentText()
        self.branch_combo.clear()
        self.branch_combo.setEditText(current)

    def _on_repo_text_changed(self, _text: str) -> None:
        self._reset_subdir_combo()
        self._reset_branch_combo()

    def _set_subdir_value(self, value: str) -> None:
        """Set the sub-directory combo to ``value``, adding it if missing."""
        value = (value or "").strip().strip("/")
        idx = self.subdir_combo.findText(value)
        if idx < 0:
            self.subdir_combo.addItem(value)
            idx = self.subdir_combo.findText(value)
        self.subdir_combo.setCurrentIndex(idx)

    def _current_client(self) -> Optional[GitHubClient]:
        profile = self.profile_combo.currentData() or ""
        token = ""
        if profile:
            data = self.credentials.load(profile) or {}
            token = data.get("token", "") or ""
            if not token:
                QMessageBox.warning(
                    self, tr("No token"),
                    tr("Could not load the token for profile '{p}'.").format(
                        p=profile),
                )
                return None
        return GitHubClient(token=token or None)

    def _current_repo(self) -> Optional[RepoRef]:
        try:
            return RepoRef.parse(self.repo_edit.text())
        except GitHubError as exc:
            QMessageBox.warning(self, tr("Invalid repository"), str(exc))
            return None

    # ------------------------------------------------------------------
    # Branch listing
    # ------------------------------------------------------------------
    def _on_fetch_branches(self):
        repo = self._current_repo()
        if not repo:
            return
        client = self._current_client()
        if client is None:
            return
        self._set_busy(True, tr("Loading branches…"))
        self._branch_worker = _BranchesWorker(client, repo, self)
        self._branch_worker.finished_ok.connect(self._on_branches_loaded)
        self._branch_worker.failed.connect(self._on_worker_failed)
        self._branch_worker.start()

    def _on_branches_loaded(self, branches):
        self._set_busy(False)
        current = self.branch_combo.currentText().strip()
        self.branch_combo.clear()
        self.branch_combo.addItems(branches)
        if current and current in branches:
            self.branch_combo.setCurrentText(current)
        elif "main" in branches:
            self.branch_combo.setCurrentText("main")
        elif "master" in branches:
            self.branch_combo.setCurrentText("master")
        self._log(tr("Loaded {n} branch(es).").format(n=len(branches)))

    def _on_worker_failed(self, message: str):
        self._set_busy(False)
        self._log(tr("Error: {msg}").format(msg=message))
        QMessageBox.critical(self, tr("GitHub error"), message)

    # ------------------------------------------------------------------
    # Sub-directory detection
    # ------------------------------------------------------------------
    def _on_detect_subdirs(self):
        repo = self._current_repo()
        if not repo:
            return
        branch = self.branch_combo.currentText().strip()
        if not branch:
            QMessageBox.warning(self, tr("Missing branch"),
                                tr("Please provide or select a branch."))
            return
        client = self._current_client()
        if client is None:
            return
        self._set_busy(True, tr("Scanning repository for plugin folders…"))
        self._subdir_worker = _SubdirWorker(client, repo, branch, self)
        self._subdir_worker.finished_ok.connect(self._on_subdirs_loaded)
        self._subdir_worker.failed.connect(self._on_worker_failed)
        self._subdir_worker.start()

    def _on_subdirs_loaded(self, folders):
        self._set_busy(False)
        current = self._current_subdir()
        # Empty entry keeps the "use repo root" option visible & first.
        self._reset_subdir_combo()
        for path in folders:
            if path not in ("",):
                self.subdir_combo.addItem(path)
        if current:
            self._set_subdir_value(current)
        elif folders and folders[0] != "":
            # No root-level metadata.txt: pre-select the first candidate.
            self._set_subdir_value(folders[0])
        if not folders:
            self._log(tr("No folder with metadata.txt was found in this branch."))
        else:
            self._log(tr(
                "Detected {n} candidate folder(s) containing metadata.txt."
            ).format(n=len(folders)))

    # ------------------------------------------------------------------
    # Metadata check
    # ------------------------------------------------------------------
    def _on_check_metadata(self):
        plugin_id = self._current_plugin_id()
        if not plugin_id:
            QMessageBox.warning(self, tr("Select plugin"),
                                tr("Please choose a target plugin."))
            return
        if not self._VALID_PLUGIN_ID.match(plugin_id):
            QMessageBox.warning(
                self, tr("Invalid plugin folder name"),
                tr("'{name}' is not a valid plugin folder name. Use letters, "
                   "digits, '_', '.' or '-' (no spaces/slashes).").format(
                       name=plugin_id),
            )
            return
        repo = self._current_repo()
        if not repo:
            return
        branch = self.branch_combo.currentText().strip()
        if not branch:
            QMessageBox.warning(self, tr("Missing branch"),
                                tr("Please provide or select a branch."))
            return
        client = self._current_client()
        if client is None:
            return

        subdir = self._current_subdir()
        meta_path = f"{subdir}/metadata.txt" if subdir else "metadata.txt"
        self._set_busy(True, tr("Downloading metadata.txt…"))
        try:
            incoming = client.get_file(repo, branch, meta_path)
        except GitHubError as exc:
            self._set_busy(False)
            QMessageBox.critical(self, tr("GitHub error"), str(exc))
            return
        finally:
            self._set_busy(False)

        incoming_text = incoming.decode("utf-8", errors="replace") \
            if incoming is not None else None
        self._incoming_metadata_text = incoming_text

        installed_text = self.replacer.read_metadata(plugin_id)
        report = compare_metadata(installed_text, incoming_text, plugin_id)

        self._log(tr("metadata.txt check for '{name}':").format(name=plugin_id))
        if not report.issues:
            self._log(tr("  - No issues detected."))
        for issue in report.issues:
            self._log(f"  [{issue.severity.upper()}] {issue.message}")

        return report

    # ------------------------------------------------------------------
    # Replacement flow
    # ------------------------------------------------------------------
    def _on_replace(self):
        plugin_id = self._current_plugin_id()
        if not plugin_id:
            QMessageBox.warning(self, tr("Select plugin"),
                                tr("Please choose a target plugin."))
            return
        if not self._VALID_PLUGIN_ID.match(plugin_id):
            QMessageBox.warning(
                self, tr("Invalid plugin folder name"),
                tr("'{name}' is not a valid plugin folder name. Use letters, "
                   "digits, '_', '.' or '-' (no spaces/slashes).").format(
                       name=plugin_id),
            )
            return
        repo = self._current_repo()
        if not repo:
            return
        branch = self.branch_combo.currentText().strip()
        if not branch:
            QMessageBox.warning(self, tr("Missing branch"),
                                tr("Please provide or select a branch."))
            return

        report = self._on_check_metadata()
        if report is None:
            return
        if report.has_errors:
            QMessageBox.critical(
                self, tr("Metadata errors"),
                tr("Aborting – the incoming metadata.txt has errors. "
                   "See the log for details."),
            )
            return
        if report.has_warnings:
            text = "\n".join(
                f"- {i.message}" for i in report.issues if i.severity != "info"
            )
            proceed = QMessageBox.question(
                self, tr("Proceed despite warnings?"),
                tr("The following issues were detected:\n\n{issues}\n\n"
                   "Replace the plugin anyway?").format(issues=text),
            )
            if proceed != QMessageBox.Yes:
                self._log(tr("User aborted after metadata warnings."))
                return

        # Confirm action (wording depends on new install vs replacement)
        if self._is_new_install(plugin_id):
            title = tr("Confirm installation")
            body = tr(
                "Plugin '{name}' is not installed yet. A new plugin folder "
                "will be created from {repo} @ {branch} and activated in "
                "QGIS. Continue?"
            ).format(name=plugin_id, repo=repo.full_name, branch=branch)
        else:
            title = tr("Confirm replacement")
            body = tr(
                "The files of plugin '{name}' will be replaced with the "
                "contents of {repo} @ {branch}. A backup is created "
                "automatically. Continue?"
            ).format(name=plugin_id, repo=repo.full_name, branch=branch)
        confirm = QMessageBox.question(self, title, body)
        if confirm != QMessageBox.Yes:
            self._log(tr("User cancelled before replacement."))
            return

        client = self._current_client()
        if client is None:
            return

        # Clean any previous temporary directory.
        self._cleanup_temp()
        self._temp_dir = tempfile.mkdtemp(prefix="gps_")
        self._set_busy(True, tr("Downloading archive…"))
        self._download_worker = _DownloadWorker(
            client, repo, branch, self._temp_dir,
            subdir=self._current_subdir(),
            parent=self,
        )
        self._download_worker.finished_ok.connect(
            lambda path: self._perform_replacement(plugin_id, repo, branch, path)
        )
        self._download_worker.failed.connect(self._on_worker_failed)
        self._download_worker.start()

    def _perform_replacement(self, plugin_id: str, repo: RepoRef,
                             branch: str, source_dir: str):
        self._set_busy(False)
        self._downloaded_source_dir = source_dir
        self._log(tr("Archive extracted to: {path}").format(path=source_dir))

        try:
            result = self.replacer.replace(plugin_id, source_dir, try_reload=True)
        except Exception as exc:  # noqa: BLE001
            self._log(tr("Replacement failed: {err}").format(err=exc))
            QMessageBox.critical(self, tr("Replacement failed"), str(exc))
            self._cleanup_temp()
            return

        for msg in result.messages:
            self._log(msg)

        if result.fresh_install:
            # Make the new folder visible in the installed-plugins list.
            self._populate_plugins()
            idx = self.plugin_combo.findData(plugin_id)
            if idx >= 0:
                self.plugin_combo.setCurrentIndex(idx)
            else:
                self.plugin_combo.setEditText(plugin_id)

        if self.remember_check.isChecked():
            self.mappings.save(PluginMapping(
                plugin_id=plugin_id,
                repo=repo.full_name,
                credential_profile=self.profile_combo.currentData() or "",
            ))
            self._log(tr("Saved mapping for '{name}'.").format(name=plugin_id))

        self._cleanup_temp()

        if result.restart_required:
            QMessageBox.information(
                self, tr("Restart required"),
                tr("Files replaced successfully. Please restart QGIS to "
                   "finish integrating the new version."),
            )
        else:
            if result.fresh_install:
                QMessageBox.information(
                    self, tr("Installation complete"),
                    tr("Plugin '{name}' was installed from GitHub and "
                       "activated successfully.").format(name=plugin_id),
                )
            else:
                QMessageBox.information(
                    self, tr("Replacement complete"),
                    tr("Plugin '{name}' was replaced and reloaded "
                       "successfully.").format(name=plugin_id),
                )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, message: str = ""):
        self.progress.setVisible(busy)
        self.replace_btn.setEnabled(not busy)
        self.check_btn.setEnabled(not busy)
        self.cleanup_btn.setEnabled(not busy)
        self.fetch_branches_btn.setEnabled(not busy)
        self.detect_subdir_btn.setEnabled(not busy)
        if busy and message:
            self._log(message)
        QApplication.processEvents()

    def _log(self, message: str):
        self.log.appendPlainText(message)

    def _cleanup_temp(self):
        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = None
        self._downloaded_source_dir = None

    def closeEvent(self, event):  # noqa: N802 (Qt API)
        self._cleanup_temp()
        if self._help_dialog is not None:
            self._help_dialog.close()
            self._help_dialog = None
        super().closeEvent(event)
