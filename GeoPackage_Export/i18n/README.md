# Internationalization (i18n)

This directory holds the translation files for the GeoPackage Export plugin.

Source language in the code is **English** (all `self.tr()` / `QCoreApplication.translate()`
arguments). Translations into other languages live in per-locale `.ts` / `.qm` files.

## Files

- `gpkg_export_de.ts` / `.qm` – German translation
- `gpkg_export_en.ts` / `.qm` – English (identity; source == translation, ensures `.qm`
  loads cleanly for `en_*` locales)
- `de_translations.json` – Canonical German translations, keyed by English source string.
  The CI workflow fills `gpkg_export_de.ts` from this file so the German UI is complete
  without manual Linguist work.

Filename convention: `gpkg_export_{locale}.ts` / `gpkg_export_{locale}.qm`. The locale is
read from the QGIS settings (e.g. `de_DE` → `de`). If no `.qm` file matches, Qt falls
back to the source strings, i.e. English.

## Updating translations after code changes

The CI workflow `.github/workflows/update-translations.yml` (manual dispatch) does this
automatically. Run it after changing any `tr()` source string.

### What it does

1. Runs `pylupdate5` on both `gpkg_export_de.ts` and `gpkg_export_en.ts`, extracting all
   source strings from the Python modules below.
2. Fills `gpkg_export_de.ts` translations from `de_translations.json`. Source strings
   that have no German translation yet get reported as workflow warnings.
3. Compiles both `.qm` files with `lrelease` and commits the result.

### Python modules scanned

```
GeoPackage_Export/plugin.py
GeoPackage_Export/gui/main_dialog.py
GeoPackage_Export/core/export_logic.py
GeoPackage_Export/core/style_utils.py
```

### Running it locally

```bash
# 1. Regenerate the .ts files from code
for locale in de en; do
  pylupdate5 \
    GeoPackage_Export/plugin.py \
    GeoPackage_Export/gui/main_dialog.py \
    GeoPackage_Export/core/export_logic.py \
    GeoPackage_Export/core/style_utils.py \
    -ts GeoPackage_Export/i18n/gpkg_export_${locale}.ts
done

# 2. Fill German translations from the JSON mapping.
#    There is no standalone script; copy the inline Python block from
#    .github/workflows/update-translations.yml (the "Fill DE translations
#    from de_translations.json" step) and run it from the repo root.

# 3. Compile .qm
for locale in de en; do
  lrelease GeoPackage_Export/i18n/gpkg_export_${locale}.ts \
    -qm GeoPackage_Export/i18n/gpkg_export_${locale}.qm
done
```

## Changing or adding a German translation

Edit `de_translations.json`. Keys must be byte-identical to the English source string in
the code (including punctuation, spaces, and newlines). Then rerun the workflow (or the
commands above) so `gpkg_export_de.ts` and `.qm` pick up the change.

## Adding a new language (e.g. French)

1. Add a new `.ts` target next to the `de`/`en` loop in `.github/workflows/update-translations.yml`.
2. Create `gpkg_export_fr.ts` via `pylupdate5` (same source list as above).
3. Translate it with Qt Linguist or any tool that understands the `.ts` format:

   ```bash
   linguist GeoPackage_Export/i18n/gpkg_export_fr.ts
   ```

4. Compile:

   ```bash
   lrelease GeoPackage_Export/i18n/gpkg_export_fr.ts -qm GeoPackage_Export/i18n/gpkg_export_fr.qm
   ```

Alternatively, mirror the German flow: add a `fr_translations.json` and extend the
workflow's fill-from-JSON step for the new locale.

## Notes

- `.ts` files are the authoritative source and belong in version control.
- `.qm` files are build artefacts but are checked in too, so end users don't need the
  Qt tools installed.
- Strings with format placeholders (`%s`, `%d`) must keep the same placeholders and
  ordering in every translation; Linguist warns on mismatches.
