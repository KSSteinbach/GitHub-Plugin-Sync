# -*- coding: utf-8 -*-
"""Safely unload, replace and reload an installed QGIS plugin."""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from . import paths


@dataclass
class BackupEntry:
    """A single timestamped backup of a plugin folder."""
    plugin_id: str
    timestamp: datetime
    path: str

    @property
    def label(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d  %H:%M:%S")


@dataclass
class ReplacementResult:
    plugin_id: str
    backup_path: str
    reloaded: bool
    restart_required: bool
    messages: List[str]
    fresh_install: bool = False


_BACKUP_FOLDER_RE = re.compile(r"^(.+)_(\d{8}-\d{6})$")


class PluginReplacer:
    """Perform the actual plugin-folder swap.

    The operations are defensive: the current folder is copied to a backup
    location before deletion; if copying the new files fails, the backup is
    restored automatically.
    """

    def __init__(self, plugins_dir: str, backup_root: Optional[str] = None):
        self.plugins_dir = plugins_dir
        self.backup_root = backup_root

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def list_installed_plugins(self) -> List[str]:
        if not os.path.isdir(self.plugins_dir):
            return []
        entries = []
        for name in sorted(os.listdir(self.plugins_dir)):
            full = os.path.join(self.plugins_dir, name)
            if not os.path.isdir(full) or name.startswith("."):
                continue
            if os.path.exists(os.path.join(full, "__init__.py")):
                entries.append(name)
        return entries

    def plugin_path(self, plugin_id: str) -> str:
        return os.path.join(self.plugins_dir, plugin_id)

    def read_metadata(self, plugin_id: str) -> Optional[str]:
        path = os.path.join(self.plugin_path(plugin_id), "metadata.txt")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def list_backups(self) -> Dict[str, List[BackupEntry]]:
        """Return all available backups grouped by plugin ID, newest first."""
        backups_root = self.backup_root or paths.backups_dir()
        result: Dict[str, List[BackupEntry]] = {}
        if not os.path.isdir(backups_root):
            return result
        for name in os.listdir(backups_root):
            m = _BACKUP_FOLDER_RE.match(name)
            if not m:
                continue
            plugin_id, stamp = m.group(1), m.group(2)
            try:
                ts = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            full_path = os.path.join(backups_root, name)
            if not os.path.isdir(full_path):
                continue
            result.setdefault(plugin_id, []).append(
                BackupEntry(plugin_id=plugin_id, timestamp=ts, path=full_path)
            )
        for entries in result.values():
            entries.sort(key=lambda e: e.timestamp, reverse=True)
        return result

    def restore_backup(self, entry: BackupEntry,
                       try_reload: bool = True) -> "ReplacementResult":
        """Restore *entry* as the active plugin version.

        The current plugin folder is backed up first, so the restore itself
        is reversible. Delegates to :meth:`replace` for the actual swap.
        """
        return self.replace(
            plugin_id=entry.plugin_id,
            source_dir=entry.path,
            try_reload=try_reload,
        )

    # ------------------------------------------------------------------
    # Unload / reload via qgis.utils.plugins
    # ------------------------------------------------------------------
    def is_installed(self, plugin_id: str) -> bool:
        return os.path.isdir(self.plugin_path(plugin_id))

    def enable_plugin_in_qsettings(self, plugin_id: str) -> bool:
        """Persistently mark the plugin as enabled in QGIS.

        QGIS reads ``PythonPlugins/<plugin_id> = true`` from QSettings to
        decide which plugins to start on the next launch. For a fresh
        install we therefore need to set this flag, otherwise the plugin
        would appear disabled in the Plugin Manager after a restart.
        """
        try:
            from qgis.PyQt.QtCore import QSettings
        except ImportError:
            return False
        QSettings().setValue(f"PythonPlugins/{plugin_id}", True)
        return True

    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload the plugin if it is currently loaded. Returns True on unload."""
        try:
            from qgis import utils as qgis_utils
        except ImportError:
            return False
        if plugin_id not in getattr(qgis_utils, "plugins", {}):
            return False
        try:
            qgis_utils.unloadPlugin(plugin_id)
            return True
        except Exception:  # noqa: BLE001 - QGIS can raise anything here
            return False

    def reload_plugin(self, plugin_id: str) -> bool:
        try:
            from qgis import utils as qgis_utils
        except ImportError:
            return False
        try:
            # updateAvailablePlugins re-reads metadata files from disk.
            if hasattr(qgis_utils, "updateAvailablePlugins"):
                qgis_utils.updateAvailablePlugins()
            qgis_utils.loadPlugin(plugin_id)
            qgis_utils.startPlugin(plugin_id)
            return plugin_id in getattr(qgis_utils, "plugins", {})
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Core replacement
    # ------------------------------------------------------------------
    def replace(self, plugin_id: str, source_dir: str,
                backup_root: Optional[str] = None,
                try_reload: bool = True) -> ReplacementResult:
        if not os.path.isdir(source_dir):
            raise FileNotFoundError(f"Source directory not found: {source_dir}")

        target = self.plugin_path(plugin_id)
        messages: List[str] = []
        fresh_install = not os.path.isdir(target)

        if fresh_install:
            messages.append(
                f"Target folder does not exist – installing '{plugin_id}' "
                "as a new plugin."
            )

        unloaded = self.unload_plugin(plugin_id)
        if unloaded:
            messages.append(f"Unloaded plugin '{plugin_id}'.")
        elif not fresh_install:
            messages.append(
                f"Plugin '{plugin_id}' was not active – skipping unload."
            )

        backup_path = self._backup(target, backup_root)
        if backup_path:
            messages.append(f"Created backup at: {backup_path}")

        try:
            self._copy_new_files(source_dir, target)
            messages.append(f"Copied new files into: {target}")
        except Exception as exc:  # noqa: BLE001 - we re-raise after rollback
            messages.append(f"Copy failed, rolling back: {exc}")
            self._rollback(backup_path, target)
            raise

        if fresh_install:
            if self.enable_plugin_in_qsettings(plugin_id):
                messages.append(
                    f"Enabled '{plugin_id}' in QGIS settings."
                )

        reloaded = False
        restart_required = False
        if try_reload:
            reloaded = self.reload_plugin(plugin_id)
            if reloaded:
                messages.append(
                    f"{'Loaded' if fresh_install else 'Reloaded'} "
                    f"plugin '{plugin_id}'."
                )
            else:
                restart_required = True
                messages.append(
                    "Automatic load was not possible. "
                    "Please restart QGIS to finish integration."
                )
        else:
            restart_required = True
            messages.append(
                "Load skipped – restart QGIS to activate the new files."
            )

        return ReplacementResult(
            plugin_id=plugin_id,
            backup_path=backup_path or "",
            reloaded=reloaded,
            restart_required=restart_required,
            messages=messages,
            fresh_install=fresh_install,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _backup(self, target: str, backup_root: Optional[str]) -> Optional[str]:
        if not os.path.isdir(target):
            return None
        root = backup_root or self.backup_root or paths.backups_dir()
        os.makedirs(root, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(root, f"{os.path.basename(target)}_{stamp}")
        shutil.copytree(target, dest)
        return dest

    def _copy_new_files(self, source_dir: str, target: str) -> None:
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(source_dir, target)

    def _rollback(self, backup_path: Optional[str], target: str) -> None:
        if not backup_path or not os.path.isdir(backup_path):
            return
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        try:
            shutil.copytree(backup_path, target)
        except OSError:
            pass
