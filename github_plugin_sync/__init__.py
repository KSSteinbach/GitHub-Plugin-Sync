# -*- coding: utf-8 -*-
"""GitHub Plugin Sync - QGIS plugin entry point."""


def classFactory(iface):  # noqa: N802 (QGIS required name)
    from .plugin import GitHubPluginSyncPlugin
    return GitHubPluginSyncPlugin(iface)
