# GitHub Plugin Sync – QGIS developer plugin

A QGIS plugin that streamlines testing different variants of another
QGIS plugin: it replaces all files of an installed plugin in the user
profile directory with the contents of a GitHub repository + branch.

## Features

- **Replace** an installed plugin *or* perform a **fresh installation**
  by typing a new folder name into the target selector.
- Access to public **and** private GitHub repositories (Personal Access
  Token authentication).
- Optional storage of credentials in QGIS's authentication database.
- Browse and select any branch of the chosen repository.
- Optional persistent mapping between an installed plugin and its
  GitHub source (repo, credential profile) for one-click pre-selection.
- Validates the incoming `metadata.txt` and warns about likely
  problems (missing fields, mismatching plugin name, higher
  `qgisMinimumVersion`, …) with the option to abort.
- Stores backups of the replaced plugin-data in
  `<qgisSettingsDirPath>/github_plugin_sync/<plugin>_<timestamp>/`
- Safely **unloads** the target plugin before replacing its files and
  creates a timestamped backup.
- Automatically **reloads** the plugin after replacement; prompts for a
  QGIS restart when a clean reload is not possible.
- All dialogs are in English and prepared for QGIS translations
  via `.ts` files in `github_plugin_sync/i18n/`.

## Installation

1. Copy the `github_plugin_sync/` directory into your QGIS Python
   plugins folder, e.g.
   `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   (Linux) or the equivalent on your platform.
2. Restart QGIS so it discovers the new plugin folder.
3. Enable **GitHub Plugin Sync** in the Plugin Manager.

## Layout

```
github_plugin_sync/
├── __init__.py              # QGIS entry point (classFactory)
├── plugin.py                # Menu/toolbar registration
├── metadata.txt             # Plugin metadata
├── icon.png                 # Toolbar/menu icon
├── core/
│   ├── cleanup.py           # Cleanup targets and uninstall hook
│   ├── credentials.py       # Credential storage (QgsAuthManager)
│   ├── github_client.py     # REST API + tarball download
│   ├── mappings.py          # Plugin ↔ repo persistence
│   ├── metadata_check.py    # metadata.txt validator
│   ├── paths.py             # Shared filesystem paths
│   └── plugin_replacer.py   # Unload/swap/reload logic
├── ui/
│   ├── main_dialog.py       # Central dialog
│   ├── credentials_dialog.py
│   ├── cleanup_dialog.py
│   └── help_dialog.py
└── i18n/
    └── github_plugin_sync_en.ts
```

## Notes

- Backups are written to
  `<qgisSettingsDirPath>/github_plugin_sync/<plugin>_<timestamp>/`
  and can be restored manually.

---

*Developed in my spare time. If you find it useful, consider [sponsoring on GitHub](https://github.com/sponsors/KSSteinbach) or [via PayPal](https://paypal.me/kssteinbach).* 
