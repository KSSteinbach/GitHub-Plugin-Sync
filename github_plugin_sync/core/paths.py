# -*- coding: utf-8 -*-
"""Shared filesystem paths for the GitHub Plugin Sync plugin.

All plugin-owned persistent data lives under a single directory inside
the active QGIS profile so it is easy to back up, inspect or move to
another machine. The directory is created on demand.

Credentials themselves are stored in QGIS's native authentication
database (``QgsAuthManager``); the ``legacy_*`` helpers below only
point at the files used by earlier releases so they can be migrated
into the auth database on first run.
"""

from __future__ import annotations

import os


def storage_dir() -> str:
    """Return ``{qgisSettingsDirPath}/github_plugin_sync/`` (created if missing).

    Falls back to ``~/.qgis_github_plugin_sync/github_plugin_sync/`` when
    QGIS is not available (e.g. during tests).
    """
    try:
        from qgis.core import QgsApplication
        base = QgsApplication.qgisSettingsDirPath()
    except Exception:  # noqa: BLE001 - fallback outside QGIS
        base = os.path.expanduser("~/.qgis_github_plugin_sync")
    folder = os.path.join(base, "github_plugin_sync")
    os.makedirs(folder, exist_ok=True)
    return folder


def mappings_path() -> str:
    return os.path.join(storage_dir(), "mappings.json")


def backups_dir() -> str:
    path = os.path.join(storage_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def legacy_credentials_path() -> str:
    """Path to the pre-QgsAuthManager ``credentials.json`` file."""
    return os.path.join(storage_dir(), "credentials.json")


def legacy_key_path() -> str:
    """Path to the pre-QgsAuthManager Fernet key file."""
    return os.path.join(storage_dir(), "cred.key")
