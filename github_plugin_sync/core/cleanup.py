# -*- coding: utf-8 -*-
"""Cleanup helpers for plugin-owned persistent data.

QGIS does not provide a dedicated "on uninstall" callback: ``unload()``
fires both when the plugin is disabled and when QGIS shuts down. This
module therefore offers two complementary entry points:

* :func:`list_targets` / :func:`delete_targets` drive a user-triggered
  cleanup dialog.
* :func:`register_uninstall_cleanup` schedules an ``atexit`` handler
  that only deletes data when the plugin directory has disappeared by
  the time QGIS exits – i.e. when the plugin was actually uninstalled.

Auto-cleanup preferences are persisted in a tiny JSON file alongside
the plugin's other data so they survive Qt shutting down during atexit.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from . import paths


AUTO_CLEANUP_FILE = "auto_cleanup.json"

# Cleanup target keys used both in the UI and in the auto-cleanup file.
TARGET_MAPPINGS = "mappings"
TARGET_BACKUPS = "backups"
TARGET_LEGACY = "legacy"
TARGET_STORAGE = "storage"


@dataclass
class CleanupTarget:
    key: str
    label: str
    description: str
    paths: List[str]
    exists: bool
    size_bytes: int

    @property
    def human_size(self) -> str:
        return _format_size(self.size_bytes)


# ----------------------------------------------------------------------
# Target enumeration
# ----------------------------------------------------------------------
def list_targets() -> List[CleanupTarget]:
    """Return the set of cleanup targets in a stable order."""
    storage = paths.storage_dir()
    mappings = paths.mappings_path()
    backups = paths.backups_dir()
    legacy_paths = _legacy_paths()

    targets = [
        CleanupTarget(
            key=TARGET_MAPPINGS,
            label="Plugin ↔ repository mappings",
            description="mappings.json (remembered plugin/repo/branch links).",
            paths=[mappings],
            exists=os.path.exists(mappings),
            size_bytes=_path_size(mappings),
        ),
        CleanupTarget(
            key=TARGET_BACKUPS,
            label="Plugin backups",
            description=(
                "Timestamped backups created before each replacement. "
                "Deleting them discards every restore point."
            ),
            paths=[backups],
            exists=_dir_has_content(backups),
            size_bytes=_path_size(backups),
        ),
        CleanupTarget(
            key=TARGET_LEGACY,
            label="Legacy credential files",
            description=(
                "credentials.json / cred.key left over from pre-"
                "authentication-manager releases (migrated copies "
                "included)."
            ),
            paths=legacy_paths,
            exists=any(os.path.exists(p) for p in legacy_paths),
            size_bytes=sum(_path_size(p) for p in legacy_paths),
        ),
        CleanupTarget(
            key=TARGET_STORAGE,
            label="Entire plugin data directory",
            description=(
                "Removes the whole github_plugin_sync data directory, "
                "including everything above."
            ),
            paths=[storage],
            exists=os.path.isdir(storage),
            size_bytes=_path_size(storage),
        ),
    ]
    return targets


def delete_targets(keys: Iterable[str]) -> Dict[str, Optional[str]]:
    """Delete the targets identified by ``keys``.

    Returns a mapping of ``key`` to ``None`` on success or the error
    string on failure. Unknown keys are reported with a descriptive
    message so UI callers can surface the problem.
    """
    key_set = {k for k in keys if k}
    results: Dict[str, Optional[str]] = {}

    # "storage" subsumes all other targets – do it last and skip the
    # rest if it is requested.
    storage_requested = TARGET_STORAGE in key_set
    ordered = [k for k in (TARGET_MAPPINGS, TARGET_BACKUPS, TARGET_LEGACY)
               if k in key_set and not storage_requested]
    if storage_requested:
        ordered.append(TARGET_STORAGE)

    by_key = {t.key: t for t in list_targets()}
    for key in ordered:
        target = by_key.get(key)
        if target is None:
            results[key] = f"unknown cleanup target: {key}"
            continue
        error: Optional[str] = None
        for path in target.paths:
            try:
                _delete_path(path)
            except OSError as exc:
                error = f"{path}: {exc}"
                break
        results[key] = error
    return results


# ----------------------------------------------------------------------
# Auto-cleanup-on-uninstall preferences
# ----------------------------------------------------------------------
def _auto_cleanup_path() -> str:
    return os.path.join(paths.storage_dir(), AUTO_CLEANUP_FILE)


def load_auto_cleanup_keys() -> List[str]:
    """Return the cleanup keys scheduled to run on uninstall."""
    path = _auto_cleanup_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("on_uninstall", [])
    if not isinstance(raw, list):
        return []
    return [str(k) for k in raw if isinstance(k, str)]


def save_auto_cleanup_keys(keys: Iterable[str]) -> None:
    """Persist the cleanup keys to run on uninstall (``[]`` disables it)."""
    allowed = {TARGET_MAPPINGS, TARGET_BACKUPS, TARGET_LEGACY, TARGET_STORAGE}
    filtered = sorted({k for k in keys if k in allowed})
    path = _auto_cleanup_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"on_uninstall": filtered}, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


# ----------------------------------------------------------------------
# Uninstall detection via atexit
# ----------------------------------------------------------------------
_REGISTERED = False


def register_uninstall_cleanup(plugin_dir: str) -> None:
    """Register an ``atexit`` handler that cleans up after uninstall.

    The handler runs when QGIS/Python exits. It only performs the
    deletion when ``plugin_dir`` no longer exists by that time, which
    reliably distinguishes an uninstall from a plain disable or a
    regular shutdown.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True

    captured_plugin_dir = plugin_dir
    captured_storage_dir = paths.storage_dir()
    captured_settings_path = _auto_cleanup_path()
    captured_mappings_path = paths.mappings_path()
    captured_backups_dir = paths.backups_dir()
    captured_legacy_paths = _legacy_paths()

    def _run_if_uninstalled() -> None:
        if os.path.isdir(captured_plugin_dir):
            return
        keys = _read_keys_standalone(captured_settings_path)
        if not keys:
            return
        _delete_by_keys_standalone(
            keys,
            storage_dir=captured_storage_dir,
            mappings_path=captured_mappings_path,
            backups_dir=captured_backups_dir,
            legacy_paths=captured_legacy_paths,
        )

    atexit.register(_run_if_uninstalled)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------
def _legacy_paths() -> List[str]:
    storage = paths.storage_dir()
    return [
        paths.legacy_credentials_path(),
        paths.legacy_key_path(),
        os.path.join(storage, "credentials.json.migrated"),
        os.path.join(storage, "cred.key.migrated"),
    ]


def _path_size(path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def _dir_has_content(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        return any(True for _ in os.scandir(path))
    except OSError:
        return False


def _delete_path(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _format_size(size: int) -> str:
    if size <= 0:
        return "–"
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _read_keys_standalone(settings_path: str) -> List[str]:
    """Read the on-uninstall keys without touching Qt (for atexit use)."""
    if not os.path.exists(settings_path):
        return []
    try:
        with open(settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("on_uninstall", [])
    if not isinstance(raw, list):
        return []
    return [str(k) for k in raw if isinstance(k, str)]


def _delete_by_keys_standalone(
    keys: List[str],
    *,
    storage_dir: str,
    mappings_path: str,
    backups_dir: str,
    legacy_paths: List[str],
) -> None:
    """Perform deletion using captured paths (safe during shutdown)."""
    key_set = set(keys)
    if TARGET_STORAGE in key_set:
        try:
            _delete_path(storage_dir)
        except OSError:
            pass
        return

    if TARGET_MAPPINGS in key_set:
        try:
            _delete_path(mappings_path)
        except OSError:
            pass
    if TARGET_BACKUPS in key_set:
        try:
            _delete_path(backups_dir)
        except OSError:
            pass
    if TARGET_LEGACY in key_set:
        for path in legacy_paths:
            try:
                _delete_path(path)
            except OSError:
                continue
