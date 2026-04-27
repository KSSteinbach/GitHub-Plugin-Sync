# -*- coding: utf-8 -*-
"""Compare the metadata.txt of an installed plugin against the one in a
GitHub repository before performing a replacement.

The check surfaces issues that commonly break installed plugins after a
hot-swap (mismatched ``name``/folder, missing fields, downgraded QGIS
minimum version, different plugin identity, etc.) so the user can confirm
or abort.
"""

from __future__ import annotations

import configparser
import io
from dataclasses import dataclass, field
from typing import List, Optional


REQUIRED_FIELDS = ("name", "version", "qgisMinimumVersion", "description")


@dataclass
class MetadataIssue:
    severity: str       # "info" | "warning" | "error"
    message: str


@dataclass
class MetadataReport:
    installed: Optional[dict] = None
    incoming: Optional[dict] = None
    issues: List[MetadataIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)


def parse_metadata(text: str) -> dict:
    """Parse a metadata.txt string into a flat dict (``[general]`` section)."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # preserve original key casing (qgisMinimumVersion)
    try:
        parser.read_file(io.StringIO(text))
    except configparser.Error as exc:
        raise ValueError(f"Unable to parse metadata.txt: {exc}") from exc
    if not parser.has_section("general"):
        raise ValueError("metadata.txt is missing the [general] section")
    return {k: v.strip() for k, v in parser.items("general")}


def compare(installed_text: Optional[str],
            incoming_text: Optional[str],
            plugin_folder_name: str) -> MetadataReport:
    report = MetadataReport()

    if incoming_text is None:
        report.issues.append(MetadataIssue(
            "error",
            "The GitHub repository does not contain a metadata.txt file. "
            "Aborting is recommended – the plugin would be broken after "
            "replacement.",
        ))
        return report

    try:
        report.incoming = parse_metadata(incoming_text)
    except ValueError as exc:
        report.issues.append(MetadataIssue("error", str(exc)))
        return report

    if installed_text is not None:
        try:
            report.installed = parse_metadata(installed_text)
        except ValueError as exc:
            report.issues.append(MetadataIssue(
                "warning",
                f"Installed metadata.txt could not be parsed: {exc}",
            ))

    # Required fields present in the incoming metadata
    for field_name in REQUIRED_FIELDS:
        if not report.incoming.get(field_name):
            report.issues.append(MetadataIssue(
                "error",
                f"Incoming metadata.txt is missing required field '{field_name}'.",
            ))

    # Optional cross-check with installed metadata
    if report.installed is not None:
        if report.installed.get("name") != report.incoming.get("name"):
            report.issues.append(MetadataIssue(
                "warning",
                "Plugin 'name' differs between installed and incoming "
                "metadata.txt. This may point to the wrong repository.",
            ))

        inst_min = report.installed.get("qgisMinimumVersion", "")
        new_min = report.incoming.get("qgisMinimumVersion", "")
        if inst_min and new_min and _version_key(new_min) > _version_key(inst_min):
            report.issues.append(MetadataIssue(
                "warning",
                "Incoming plugin requires a higher qgisMinimumVersion "
                f"({new_min} vs {inst_min}). Make sure your QGIS is compatible.",
            ))

        inst_ver = report.installed.get("version", "")
        new_ver = report.incoming.get("version", "")
        if inst_ver and new_ver and _version_key(new_ver) < _version_key(inst_ver):
            report.issues.append(MetadataIssue(
                "info",
                f"Incoming version ({new_ver}) is lower than the installed "
                f"version ({inst_ver}).",
            ))

    # Heuristic: the plugin folder name should loosely match the incoming
    # 'name' or a likely module name, otherwise plugin discovery can break.
    incoming_name = report.incoming.get("name", "").lower().replace(" ", "_")
    if incoming_name and plugin_folder_name.lower() not in (
        incoming_name,
        incoming_name.replace("-", "_"),
    ):
        # Only a hint, not an error – many repos use different folder names.
        report.issues.append(MetadataIssue(
            "info",
            f"The target folder name '{plugin_folder_name}' does not obviously "
            f"match the plugin name '{report.incoming.get('name')}'. "
            "Verify you are replacing the right plugin.",
        ))

    return report


def _version_key(value: str):
    parts = []
    for chunk in value.replace("-", ".").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)
