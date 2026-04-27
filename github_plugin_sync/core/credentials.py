# -*- coding: utf-8 -*-
"""GitHub credential storage backed by QGIS's authentication database.

Credentials are stored as ``Basic`` auth configurations inside
``QgsAuthManager``. QGIS encrypts them with the user's master password
and keeps the encryption key outside of this plugin's purview – no key
file is written next to the ciphertext and there is no silent
obfuscation-only fallback.

Profiles created by earlier releases (``credentials.json`` +
``cred.key``) are imported into the auth database on first use and the
legacy files are renamed to ``*.migrated`` afterwards.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Dict, List, Optional

from . import paths


_NAME_PREFIX = "GitHubPluginSync/"
_METHOD = "Basic"

# Legacy storage markers – only relevant for one-time migration.
_LEGACY_ENCRYPTED_PREFIX = "ENC1:"
_LEGACY_OBFUSCATION_PREFIX = "OBF1:"


def _auth_manager():
    """Return QGIS's auth manager instance or ``None`` outside QGIS."""
    try:
        from qgis.core import QgsApplication
    except Exception:  # noqa: BLE001 - PyQGIS not importable (e.g. tests)
        return None
    try:
        return QgsApplication.authManager()
    except Exception:  # noqa: BLE001
        return None


def _ensure_master_password(auth_manager) -> bool:
    """Make sure the QGIS master password is unlocked for this session.

    Returns ``True`` when the password is available. Prompts the user if
    it is not yet set and returns ``False`` if they cancel.
    """
    if auth_manager is None:
        return False
    try:
        if auth_manager.masterPasswordIsSet():
            return True
        return bool(auth_manager.setMasterPassword(True))
    except Exception:  # noqa: BLE001
        return False


class CredentialManager:
    """Persist GitHub credentials inside QGIS's authentication database."""

    def __init__(self):
        self._am = _auth_manager()
        self._migrated = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def encryption_available(self) -> bool:
        return self._get_am() is not None

    def list_profiles(self) -> List[str]:
        self._maybe_migrate()
        return sorted(self._configs_by_profile().keys())

    def save(self, profile: str, username: str, token: str,
             encrypt: bool = True) -> None:
        """Store or update ``profile``.

        ``encrypt`` is accepted for backward compatibility and ignored:
        QgsAuthManager always encrypts stored secrets with the master
        password.
        """
        del encrypt  # kept for API compatibility
        if not profile:
            return
        am = self._get_am()
        if am is None:
            raise RuntimeError(
                "QGIS authentication manager is not available; "
                "credentials cannot be stored."
            )
        if not _ensure_master_password(am):
            raise RuntimeError(
                "QGIS master password was not provided; "
                "credentials cannot be stored."
            )

        from qgis.core import QgsAuthMethodConfig

        existing = self._configs_by_profile().get(profile)
        cfg = QgsAuthMethodConfig()
        if existing is not None:
            cfg.setId(existing.id())
        cfg.setName(_NAME_PREFIX + profile)
        cfg.setMethod(_METHOD)
        cfg.setUri("")
        cfg.setConfig("username", username or "")
        cfg.setConfig("password", token or "")
        cfg.setConfig("realm", "")

        if existing is not None:
            am.updateAuthenticationConfig(cfg)
        else:
            am.storeAuthenticationConfig(cfg)

    def load(self, profile: str) -> Optional[Dict[str, str]]:
        self._maybe_migrate()
        am = self._get_am()
        if am is None:
            return None
        short = self._configs_by_profile().get(profile)
        if short is None:
            return None
        if not _ensure_master_password(am):
            return None

        from qgis.core import QgsAuthMethodConfig

        full = QgsAuthMethodConfig()
        if not am.loadAuthenticationConfig(short.id(), full, True):
            return None
        return {
            "username": full.config("username", ""),
            "token": full.config("password", ""),
            "encrypted": True,
        }

    def delete(self, profile: str) -> None:
        am = self._get_am()
        if am is None:
            return
        existing = self._configs_by_profile().get(profile)
        if existing is None:
            return
        am.removeAuthenticationConfig(existing.id())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _get_am(self):
        if self._am is None:
            self._am = _auth_manager()
        return self._am

    def _configs_by_profile(self) -> Dict[str, object]:
        am = self._get_am()
        if am is None:
            return {}
        try:
            all_configs = am.availableAuthMethodConfigs()
        except Exception:  # noqa: BLE001
            return {}
        result: Dict[str, object] = {}
        for cfg in all_configs.values():
            name = cfg.name() or ""
            if not name.startswith(_NAME_PREFIX):
                continue
            result[name[len(_NAME_PREFIX):]] = cfg
        return result

    # ------------------------------------------------------------------
    # One-time migration from credentials.json + cred.key
    # ------------------------------------------------------------------
    def _maybe_migrate(self) -> None:
        if self._migrated:
            return
        am = self._get_am()
        if am is None:
            return
        legacy_file = paths.legacy_credentials_path()
        if not os.path.exists(legacy_file):
            self._migrated = True
            return

        try:
            with open(legacy_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            # Corrupt legacy file – archive it and move on.
            self._archive_legacy()
            self._migrated = True
            return

        if not isinstance(data, dict) or not data:
            self._archive_legacy()
            self._migrated = True
            return

        if not _ensure_master_password(am):
            # Retry on next operation so the user can unlock later.
            return

        existing = self._configs_by_profile()
        for profile, payload in data.items():
            if not isinstance(payload, dict):
                continue
            if str(profile) in existing:
                continue
            token = _legacy_decode_token(str(payload.get("token", "")))
            if token is None:
                continue
            try:
                self.save(
                    str(profile),
                    str(payload.get("username", "")),
                    token,
                )
            except Exception:  # noqa: BLE001 - best-effort migration
                continue

        self._archive_legacy()
        self._migrated = True

    @staticmethod
    def _archive_legacy() -> None:
        for src in (paths.legacy_credentials_path(), paths.legacy_key_path()):
            if not os.path.exists(src):
                continue
            dst = src + ".migrated"
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
            except OSError:
                pass


# ----------------------------------------------------------------------
# Legacy decoding – used only while migrating old files
# ----------------------------------------------------------------------
def _legacy_decode_token(stored: str) -> Optional[str]:
    if not stored:
        return ""
    if stored.startswith(_LEGACY_ENCRYPTED_PREFIX):
        key = _legacy_load_key()
        if key is None:
            return None
        try:
            from cryptography.fernet import Fernet, InvalidToken
        except Exception:  # noqa: BLE001
            return None
        try:
            cipher = Fernet(key)
            return cipher.decrypt(
                stored[len(_LEGACY_ENCRYPTED_PREFIX):].encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, ValueError):
            return None
    if stored.startswith(_LEGACY_OBFUSCATION_PREFIX):
        try:
            payload = stored[len(_LEGACY_OBFUSCATION_PREFIX):]
            return base64.b64decode(payload.encode("ascii")).decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    return stored


def _legacy_load_key() -> Optional[bytes]:
    path = paths.legacy_key_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read().strip()
    except OSError:
        return None
