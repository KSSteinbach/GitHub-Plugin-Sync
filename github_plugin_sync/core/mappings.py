# -*- coding: utf-8 -*-
"""Persistence of plugin ↔ GitHub repository mappings.

Mappings are stored as JSON inside
``{qgisSettingsDirPath}/github_plugin_sync/mappings.json``. Each mapping
links an installed plugin (identified by its folder name inside the QGIS
plugins directory) to a GitHub repository and optionally the credential
profile to use for authentication.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from . import paths


SETTINGS_KEY = "GitHubPluginSync/mappings"  # legacy QSettings key, migration only


@dataclass
class PluginMapping:
    plugin_id: str           # folder name of the installed plugin
    repo: str                # "owner/name"
    credential_profile: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> Optional["PluginMapping"]:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: object) -> Optional["PluginMapping"]:
        if not isinstance(data, dict) or "plugin_id" not in data:
            return None
        return cls(
            plugin_id=str(data.get("plugin_id", "")),
            repo=str(data.get("repo", "")),
            credential_profile=str(data.get("credential_profile", "")),
        )


class MappingManager:
    """Persist plugin-to-repository links."""

    def __init__(self, storage_path: Optional[str] = None):
        self._path = storage_path or paths.mappings_path()
        self._migrate_from_qsettings()

    # ------------------------------------------------------------------
    # Storage I/O
    # ------------------------------------------------------------------
    def _load_all(self) -> Dict[str, PluginMapping]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: Dict[str, PluginMapping] = {}
        for key, value in data.items():
            mapping = PluginMapping.from_dict(value)
            if mapping:
                out[str(key)] = mapping
        return out

    def _save_all(self, mappings: Dict[str, PluginMapping]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        serialised = {key: asdict(m) for key, m in mappings.items()}
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(serialised, fh, indent=2, sort_keys=True)
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------
    # Migration from legacy QSettings storage
    # ------------------------------------------------------------------
    def _migrate_from_qsettings(self) -> None:
        if os.path.exists(self._path):
            return
        try:
            from qgis.PyQt.QtCore import QSettings
        except Exception:  # noqa: BLE001
            return
        try:
            settings = QSettings()
            raw = settings.value(SETTINGS_KEY, "")
            if not raw:
                return
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                return
            if not isinstance(data, dict):
                return
            out: Dict[str, PluginMapping] = {}
            for key, value in data.items():
                if isinstance(value, str):
                    mapping = PluginMapping.from_json(value)
                else:
                    mapping = PluginMapping.from_dict(value)
                if mapping:
                    out[str(key)] = mapping
            if not out:
                return
            self._save_all(out)
            settings.remove(SETTINGS_KEY)
        except Exception:  # noqa: BLE001 - best-effort migration
            return

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list(self) -> List[PluginMapping]:
        return list(self._load_all().values())

    def get(self, plugin_id: str) -> Optional[PluginMapping]:
        return self._load_all().get(plugin_id)

    def save(self, mapping: PluginMapping) -> None:
        all_mappings = self._load_all()
        all_mappings[mapping.plugin_id] = mapping
        self._save_all(all_mappings)

    def delete(self, plugin_id: str) -> None:
        all_mappings = self._load_all()
        if plugin_id in all_mappings:
            del all_mappings[plugin_id]
            self._save_all(all_mappings)
