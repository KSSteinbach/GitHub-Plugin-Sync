# -*- coding: utf-8 -*-

"""Dialog-Klasse für das GeoPackage-Export-Plugin.

Dieses Modul enthält ausschließlich Qt-Widget-Code – die eigentliche
Schreiblogik steckt in ``export_logic.py``. Wiederverwendbare Helfer
(Pfad-, Layer-, Dialog-Utilities) liegen in den jeweiligen
``*_utils``-Modulen.
"""

import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QMessageBox,
    QFrame,
    QCheckBox,
    QComboBox,
    QWidget,
)
from qgis.PyQt.QtCore import Qt, QCoreApplication, QSize
from qgis.PyQt.QtGui import QFont, QIcon

from ..core.constants import (
    EXPORT_MODE_BBOX,
    EXPORT_MODE_FULL,
    EXPORT_MODE_SELECTION,
    ICON_COL_WIDTH,
    ICON_PIXMAP_SIZE,
    MIN_ROW_HEIGHT,
    PROVIDER_MEMORY,
    TITLE_FONT_POINT_SIZE,
)
from ..core.export_logic import GpkgExporter, build_multi_paths
from ..core.layer_utils import (
    get_all_vector_layers,
    get_temp_layers,
    is_remote_feature_layer,
)
from ..core.logging_utils import push_bar_message
from ..core.path_utils import (
    default_start_dir,
    ensure_gpkg_extension,
    is_existing_directory,
    is_existing_file,
)
from .ui_dialogs import (
    ask_yes_no,
    pick_directory,
    pick_open_gpkg,
    pick_save_gpkg,
    show_warning,
)


# =============================================================================
# GEOPACKAGE-EXPORT-TOOL
# =============================================================================
# Dieses Tool speichert ausgewählte Layer des aktiven QGIS-Projekts als
# GeoPackage-Dateien auf der Festplatte.
#
# Standardmäßig werden nur temporäre Layer (Memory-Layer, erkennbar am
# Speicher-Symbol im Layer-Panel) angezeigt, weil die beim Schließen von
# QGIS sonst verloren gehen. Über eine Checkbox lassen sich aber auch alle
# anderen Vektor-Layer des Projekts aufnehmen (Datei-Layer, WFS, Datenbank-
# Layer etc.) – praktisch, um ein ganzes Projekt in ein GeoPackage zu
# konsolidieren.
#
# Drei Speichermodi stehen zur Verfügung:
#   1. Alle ausgewählten Layer in eine einzige GPKG-Datei
#   2. Jeden Layer in eine eigene GPKG-Datei
#   3. Ausgewählte Layer an ein bestehendes GPKG anhängen
#
# Stile (Farben, Symbologie) werden in allen drei Modi in die
# layer_styles-Tabelle des GeoPackage geschrieben und beim Wieder-Öffnen
# der Datei automatisch geladen.
#
# GeoPackage (.gpkg) ist ein modernes, offenes Dateiformat für Geodaten –
# eine SQLite-Datenbank, die mehrere Layer, Stile und Metadaten in einer
# einzigen Datei speichern kann.
# =============================================================================

def _geom_icon(layer) -> str:
    """Gibt ein Unicode-Zeichen für den Geometrie-Typ des Layers zurück.

    Wird als Textfallback verwendet, falls das passende Theme-Icon
    (SVG) in der QGIS-Installation fehlt.

    Args:
        layer: Vektor-Layer, dessen Geometrie inspiziert wird.

    Returns:
        Einzeln-Zeichen-String: Punkt, Linie, Polygon oder „sonst".
    """
    wkb = layer.wkbType()
    gtype = QgsWkbTypes.geometryType(wkb)
    if gtype == QgsWkbTypes.PointGeometry:
        return "⠮"
    if gtype == QgsWkbTypes.LineGeometry:
        return "〽"
    if gtype == QgsWkbTypes.PolygonGeometry:
        return "⏢"
    return "◈"


def _geom_theme_icon(layer) -> QIcon:
    """Liefert das QGIS-Theme-Icon für den Geometrie-Typ eines Layers.

    Args:
        layer: Vektor-Layer.

    Returns:
        Passendes ``QIcon`` (Punkt/Linie/Polygon) oder ein leeres
        ``QIcon``, wenn der Typ unbekannt ist.
    """
    gtype = QgsWkbTypes.geometryType(layer.wkbType())
    name = {
        QgsWkbTypes.PointGeometry: "mIconPointLayer.svg",
        QgsWkbTypes.LineGeometry: "mIconLineLayer.svg",
        QgsWkbTypes.PolygonGeometry: "mIconPolygonLayer.svg",
    }.get(gtype)
    return QgsApplication.getThemeIcon(f"/{name}") if name else QIcon()


def _remote_theme_icon() -> QIcon:
    """Liefert ein Wolken-Icon für WFS-/OAPIF-Layer.

    Probiert mehrere Icon-Namen der Reihe nach – bevorzugt das farbige
    Cloud-Connection-Symbol, sonst das flache Cloud-Layer-Icon. Falls
    in der QGIS-Installation keines davon verfügbar ist, wird ein
    leeres ``QIcon`` zurückgegeben (Aufrufer zeigt dann einen
    Text-Fallback an).
    """
    for name in ("mIconCloudLayer.svg",
                 "mIconCloud.svg",
                 "mIconCloudConnection.svg"):
        icon = QgsApplication.getThemeIcon(f"/{name}")
        if not icon.isNull():
            return icon
    return QIcon()


def _temp_theme_icon() -> QIcon:
    """Liefert das Uhrzeit-Icon für temporäre (Memory-)Layer."""
    return QgsApplication.getThemeIcon("/mIconTemporary.svg")


def _bold_font() -> QFont:
    """Gibt einen fetten ``QFont`` zurück (für GroupBox-Titel)."""
    f = QFont()
    f.setBold(True)
    return f


# =============================================================================
# DIALOG-KLASSE
# =============================================================================

class GpkgExportDialog(QDialog):
    """Haupt-Dialog für den GeoPackage-Export.

    Steuert die drei Speichermodi (einzeln, mehrere, anhängen), die
    Layer-Auswahl und die Export-Strategie für Remote-Layer. Startet
    den eigentlichen Export über einen :class:`GpkgExportTask` im
    Hintergrund, damit die QGIS-Oberfläche reagibel bleibt.
    """

    def tr(self, message: str) -> str:
        """Übersetzt ``message`` im Qt-Kontext dieses Dialogs."""
        return QCoreApplication.translate("GpkgExportDialog", message)

    def __init__(self, iface, parent=None):
        """Baut und initialisiert den Dialog.

        Args:
            iface: QGIS-``iface`` – wird an den ``GpkgExporter``
                weitergereicht und für die Meldungs-Leiste genutzt.
            parent: Übergeordnetes Fenster (Standard: Hauptfenster).
        """
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        # Pro WFS/OAPIF-Layer merken wir uns die Modus-Combobox, um
        # die Auswahl beim Speichern wieder auszulesen.
        self._remote_mode_combos = {}
        self._exporter = GpkgExporter(iface)
        self.setWindowTitle(self.tr("Save Layers as GeoPackage"))
        self.setMinimumWidth(650)
        self.setMinimumHeight(700)
        self._build_ui()
        self._populate_layers()

    def _build_ui(self):
        """Baut die gesamte Oberfläche des Dialogs zusammen.

        Struktur von oben nach unten:

        1. Titel + Trennlinie
        2. Layer-Auswahl (Gruppe 1): Checkbox „nur temporär", Liste,
           Info-Zeile zu WFS, Auswahl-Buttons.
        3. Speichermodus (Gruppe 2): drei Radio-Buttons.
        4. Speicherort (Gruppe 3): drei umschaltbare Varianten
           (Single-Datei, Multi-Verzeichnis, Append-Datei).
        5. Ersatz-Checkbox + Speichern-/Abbrechen-Buttons.
        """
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(12, 9, 12, 12)

        title = QLabel(self.tr("Layers → GeoPackage"))
        font = QFont()
        font.setPointSize(TITLE_FONT_POINT_SIZE)
        font.setBold(True)
        title.setFont(font)
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        self.grp_layers = QGroupBox(self.tr("1  Select temporary layers"))
        self.grp_layers.setFont(_bold_font())
        vl = QVBoxLayout(self.grp_layers)

        self.chk_only_temp = QCheckBox(
            self.tr("Show only temporary layers")
        )
        self.chk_only_temp.setChecked(False)
        self.chk_only_temp.setToolTip(
            self.tr(
                "If enabled, only temporary layers (memory provider) are shown.\n"
                "By default, all vector layers in the project are listed –\n"
                "including file layers (ogr), WFS layers, database layers, etc.\n"
                "Temporary layers are marked with a ⏱ symbol."
            )
        )
        self.chk_only_temp.stateChanged.connect(self._populate_layers)
        vl.addWidget(self.chk_only_temp)

        hint = QLabel(self.tr("Multi-select with Ctrl+Click or Shift+Click."))
        hint.setStyleSheet("color: grey; font-size: 10px;")
        vl.addWidget(hint)

        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.layer_list.setAlternatingRowColors(True)
        self.layer_list.setMinimumHeight(120)
        # Selektionsfarbe auch bei fehlendem Fokus beibehalten, damit
        # ausgewaehlte Layer nicht mit den alternierenden Zeilenfarben
        # verschwimmen.
        self.layer_list.setStyleSheet(
            "QListWidget::item:selected {"
            " background-color: #005eae;"
            " color: white;"
            "}"
            "QListWidget::item:selected:!active {"
            " background-color: #005eae;"
            " color: white;"
            "}"
        )
        vl.addWidget(self.layer_list)

        self.remote_info_label = QLabel(
            self.tr(
                "☁ WFS or OGC API layers detected: with the \"Full\" filter the ENTIRE dataset is downloaded from the server. "
                "Select \"Map canvas extent\" or \"Selected features only\" per layer above to avoid this."
            )
        )
        self.remote_info_label.setWordWrap(True)
        self.remote_info_label.setStyleSheet("color: #005eae; font-size: 11px;")
        self.remote_info_label.setVisible(False)
        vl.addWidget(self.remote_info_label)

        btn_row  = QHBoxLayout()
        btn_all  = QPushButton(self.tr("Select all"))
        btn_none = QPushButton(self.tr("Clear selection"))
        btn_all.clicked.connect(self.layer_list.selectAll)
        btn_none.clicked.connect(self.layer_list.clearSelection)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        vl.addLayout(btn_row)

        root.addWidget(self.grp_layers)

        grp_mode = QGroupBox(self.tr("2  Save mode"))
        grp_mode.setFont(_bold_font())
        vl2 = QVBoxLayout(grp_mode)

        self.radio_single = QRadioButton(self.tr("Save all selected layers into a single GeoPackage"))
        self.radio_multi  = QRadioButton(self.tr("Save each layer into its own GeoPackage"))
        self.radio_append = QRadioButton(self.tr("Add layers to an existing GeoPackage"))
        self.radio_single.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_single)
        self.mode_group.addButton(self.radio_multi)
        self.mode_group.addButton(self.radio_append)
        self.radio_single.toggled.connect(self._on_mode_changed)
        self.radio_multi.toggled.connect(self._on_mode_changed)
        self.radio_append.toggled.connect(self._on_mode_changed)

        vl2.addWidget(self.radio_single)
        vl2.addWidget(self.radio_multi)
        vl2.addWidget(self.radio_append)
        root.addWidget(grp_mode)

        self.grp_file = QGroupBox(self.tr("3  Location & filename"))
        self.grp_file.setFont(_bold_font())
        fl = QVBoxLayout(self.grp_file)

        self.single_widget = QWidget()
        single_layout = QVBoxLayout(self.single_widget)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_hint = QLabel(
            self.tr(
                "Enter the target GeoPackage path or choose \"Save as …\"."
            )
        )
        single_hint.setStyleSheet("color: grey; font-size: 10px;")
        single_layout.addWidget(single_hint)

        single_row = QHBoxLayout()
        self.single_path_edit = QLineEdit()
        self.single_path_edit.setPlaceholderText(self.tr("Path to .gpkg file …"))
        btn_single = QPushButton(self.tr("Save as …"))
        btn_single.clicked.connect(self._pick_single_save_path)
        single_row.addWidget(QLabel(self.tr("File:")))
        single_row.addWidget(self.single_path_edit, 1)
        single_row.addWidget(btn_single)
        single_layout.addLayout(single_row)
        fl.addWidget(self.single_widget)

        self.multi_widget = QWidget()
        multi_layout = QVBoxLayout(self.multi_widget)
        multi_layout.setContentsMargins(0, 0, 0, 0)

        dir_row  = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText(self.tr("Choose target directory …"))
        btn_dir  = QPushButton(self.tr("Browse …"))
        btn_dir.clicked.connect(self._pick_directory)
        dir_row.addWidget(QLabel(self.tr("Directory:")))
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(btn_dir)
        multi_layout.addLayout(dir_row)

        name_row          = QHBoxLayout()
        self.name_label   = QLabel(self.tr("Filename prefix:"))
        self.name_edit    = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("e.g.  export_"))
        name_row.addWidget(self.name_label)
        name_row.addWidget(self.name_edit, 1)
        multi_layout.addLayout(name_row)

        self.name_hint = QLabel(
            self.tr("Filename = prefix + layer name + .gpkg  (e.g. \"export_Counties.gpkg\")")
        )
        self.name_hint.setStyleSheet("color: grey; font-size: 10px;")
        multi_layout.addWidget(self.name_hint)
        fl.addWidget(self.multi_widget)

        self.append_widget = QWidget()
        append_layout = QVBoxLayout(self.append_widget)
        append_layout.setContentsMargins(0, 0, 0, 0)
        append_hint = QLabel(
            self.tr(
                "The selected layers will be written as new data into an existing\n"
                "GeoPackage file. Existing data in the GeoPackage is preserved."
            )
        )
        append_hint.setStyleSheet("color: grey; font-size: 10px;")
        append_layout.addWidget(append_hint)

        gpkg_row          = QHBoxLayout()
        self.gpkg_edit    = QLineEdit()
        self.gpkg_edit.setPlaceholderText(self.tr("Path to existing .gpkg file …"))
        btn_gpkg          = QPushButton(self.tr("Browse …"))
        btn_gpkg.clicked.connect(self._pick_existing_gpkg)
        gpkg_row.addWidget(QLabel(self.tr("GeoPackage:")))
        gpkg_row.addWidget(self.gpkg_edit, 1)
        gpkg_row.addWidget(btn_gpkg)
        append_layout.addLayout(gpkg_row)
        fl.addWidget(self.append_widget)

        root.addWidget(self.grp_file)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep2)

        self.chk_replace = QCheckBox(
            self.tr("Replace saved layers in the project with GeoPackage layers")
        )
        self.chk_replace.setChecked(True)
        self.chk_replace.setToolTip(
            self.tr(
                "After saving, each layer is removed from the project\n"
                "and replaced with the corresponding saved GeoPackage layer.\n"
                "Style (colors, symbols), layer name and panel position are preserved.\n"
                "Applies to all layer types: temporary, file layers, WFS layers, etc."
            )
        )
        root.addWidget(self.chk_replace)

        btn_row2          = QHBoxLayout()
        btn_row2.addStretch()
        btn_cancel        = QPushButton(self.tr("Cancel"))
        self.btn_save     = QPushButton(self.tr("🖫 Save"))
        self.btn_save.setDefault(True)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #005eae; color: white;"
            "  padding: 3px 20px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)
        btn_row2.addWidget(btn_cancel)
        btn_row2.addWidget(self.btn_save)
        root.addLayout(btn_row2)

        self._on_mode_changed()

    def _populate_layers(self):
        """Füllt die Layer-Liste je nach „Nur temporär"-Checkbox.

        Wird beim Öffnen des Dialogs und bei jedem Umschalten der
        Checkbox aufgerufen. Sorgt für:

        * passenden GroupBox-Titel,
        * Hinweiszeile, wenn gar nichts gefunden wird,
        * einheitliche Zeilenhöhe (sonst „springen" die Einträge mit
          und ohne Combo-Box),
        * Anzeige des WFS-Hinweises oberhalb der Liste.
        """
        only_temp = self.chk_only_temp.isChecked()

        self.grp_layers.setTitle(
            self.tr("1  Select temporary layers")
            if only_temp
            else self.tr("1  Select vector layers")
        )

        layers = get_temp_layers() if only_temp else get_all_vector_layers()
        self.layer_list.clear()
        self._remote_mode_combos = {}

        if not layers:
            msg = (
                self.tr("⚠  No temporary layers found in the project.")
                if only_temp
                else self.tr("⚠  No vector layers found in the project.")
            )
            item = QListWidgetItem(msg)
            item.setFlags(Qt.NoItemFlags)
            self.layer_list.addItem(item)
            self.btn_save.setEnabled(False)
            self.remote_info_label.setVisible(False)
            return

        self.btn_save.setEnabled(True)

        has_remote = any(is_remote_feature_layer(layer) for layer in layers)

        row_widgets = []
        for layer in layers:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, layer)
            self.layer_list.addItem(item)
            row_widget = self._make_layer_row_widget(layer)
            self.layer_list.setItemWidget(item, row_widget)
            row_widgets.append((item, row_widget))

        # Einheitliche Zeilenhöhe = größte natürliche Höhe der Zeilen-
        # Widgets (berücksichtigt Combo + Icons + Margins), mit einer
        # Untergrenze, damit selbst eine Liste ohne Remote-Zeile nicht
        # auf die Text-Default-Höhe zurückfällt.
        uniform_h = max(
            MIN_ROW_HEIGHT,
            max(w.sizeHint().height() for _, w in row_widgets),
        )
        for it, w in row_widgets:
            # ``QSize(-1, h)`` wäre invalid und würde von Qt ignoriert,
            # deshalb hier eine positive Minimalbreite erzwingen.
            it.setSizeHint(QSize(max(1, w.sizeHint().width()), uniform_h))

        self.remote_info_label.setVisible(has_remote)
        self.layer_list.selectAll()

    def _make_layer_row_widget(self, layer):
        """Baut das Zeilen-Widget für einen einzelnen Layer.

        Spaltenstruktur (feste Breiten, damit Status-, Geometrie- und
        Layername-Spalten zeilenübergreifend bündig stehen):

        .. code-block:: text

            [status] [geom]  Layername (provider)        [Combo?]

        Die Status-Spalte zeigt entweder die Stoppuhr (temporär) **oder**
        die Wolke (WFS/OGC-API) – beides zusammen kann es nicht geben.
        Die Combo-Box erscheint nur bei Remote-Layern.

        Args:
            layer: Zu darstellender Vektor-Layer.

        Returns:
            Das fertige ``QWidget`` für ``QListWidget.setItemWidget``.
        """
        is_temp = layer.dataProvider().name() == PROVIDER_MEMORY
        is_remote = is_remote_feature_layer(layer)

        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(2, 1, 2, 1)
        hl.setSpacing(6)

        def icon_cell(icon: QIcon, fallback_text: str = "") -> QLabel:
            """Eine einzelne Icon-Zelle mit fester Breite bauen."""
            lbl = QLabel()
            lbl.setFixedWidth(ICON_COL_WIDTH)
            lbl.setAlignment(Qt.AlignCenter)
            if not icon.isNull():
                lbl.setPixmap(icon.pixmap(ICON_PIXMAP_SIZE, ICON_PIXMAP_SIZE))
            elif fallback_text:
                lbl.setText(fallback_text)
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            return lbl

        if is_temp:
            status_icon, status_fallback = _temp_theme_icon(), "⏱"
        elif is_remote:
            status_icon, status_fallback = _remote_theme_icon(), "☁"
        else:
            status_icon, status_fallback = QIcon(), ""
        hl.addWidget(icon_cell(status_icon, status_fallback))
        hl.addWidget(icon_cell(_geom_theme_icon(layer), _geom_icon(layer)))

        provider_name = layer.dataProvider().name()
        name_lbl = QLabel(f"{layer.name()}  ({provider_name})")
        name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        hl.addWidget(name_lbl, 1)

        if is_remote:
            combo = self._build_remote_combo(layer)
            hl.addWidget(combo)
            self._remote_mode_combos[layer.id()] = combo

        return row

    def _build_remote_combo(self, layer) -> QComboBox:
        """Baut die Export-Strategie-Combo für einen WFS-/OGC-API-Layer.

        Einträge:
        „Bildschirmausschnitt", „Nur gewählte Objekte", „Vollständig".
        Der Eintrag „Nur gewählte Objekte" wird deaktiviert, wenn der
        Layer aktuell keine Selektion hat.

        Args:
            layer: Remote-Layer (WFS oder OAPIF).

        Returns:
            Eine vorkonfigurierte ``QComboBox``.
        """
        combo = QComboBox()
        f = combo.font()
        f.setPointSize(max(1, f.pointSize() - 1))
        combo.setFont(f)
        combo.addItem(self.tr("Map canvas extent"), EXPORT_MODE_BBOX)
        combo.addItem(self.tr("Selected features only"), EXPORT_MODE_SELECTION)
        combo.addItem(self.tr("Full (⚠ feature count)"), EXPORT_MODE_FULL)

        if layer.selectedFeatureCount() == 0:
            sel_idx = combo.findData(EXPORT_MODE_SELECTION)
            combo.model().item(sel_idx).setEnabled(False)
            combo.setItemData(
                sel_idx,
                self.tr("No features are currently selected in this layer."),
                Qt.ToolTipRole,
            )

        full_idx = combo.findData(EXPORT_MODE_FULL)
        combo.setItemData(
            full_idx,
            self.tr("⚠ Warning: Large WFS services will load all features from the server."),
            Qt.ToolTipRole,
        )

        combo.setToolTip(
            self.tr(
                "Choose the export strategy for this WFS or OGC API layer.\n"
                "\"Map canvas extent\" loads only features in the current map view,\n"
                "\"Selected features only\" exports only marked features,\n"
                "\"Full\" loads the entire service (⚠ risky for large feature sets)."
            )
        )
        return combo

    def _on_mode_changed(self):
        """Blendet das passende Eingabefeld-Panel für den gewählten Modus ein.

        Single-Modus zeigt einen Dateipfad, Multi-Modus zeigt
        Verzeichnis + Präfix, Append-Modus zeigt eine bestehende GPKG.
        Zusätzlich passt sich der Titel der Gruppe 3 an.
        """
        is_single = self.radio_single.isChecked()
        is_multi = self.radio_multi.isChecked()
        is_append = self.radio_append.isChecked()

        self.single_widget.setVisible(is_single)
        self.multi_widget.setVisible(is_multi)
        self.append_widget.setVisible(is_append)

        if is_single:
            self.grp_file.setTitle(self.tr("3  Target GeoPackage"))
        elif is_multi:
            self.grp_file.setTitle(self.tr("3  Location and filename prefix"))
        else:
            self.grp_file.setTitle(self.tr("3  Select existing GeoPackage"))

    def _pick_directory(self):
        """Öffnet den „Verzeichnis wählen"-Dialog für den Multi-Modus."""
        start = self.dir_edit.text() or default_start_dir()
        path = pick_directory(self, self.tr("Choose target directory"), start)
        if path:
            self.dir_edit.setText(path)

    def _pick_single_save_path(self):
        """Öffnet den „Speichern unter …"-Dialog für den Single-Modus."""
        start = self.single_path_edit.text() or default_start_dir()
        path = pick_save_gpkg(self, self.tr("Save GeoPackage as"), start)
        if path:
            self.single_path_edit.setText(path)

    def _pick_existing_gpkg(self):
        """Öffnet den „Datei öffnen"-Dialog für den Append-Modus."""
        start = self.gpkg_edit.text() or default_start_dir()
        path = pick_open_gpkg(
            self, self.tr("Select existing GeoPackage"), start
        )
        if path:
            self.gpkg_edit.setText(path)

    def _on_save(self):
        """Hauptablauf nach Klick auf „Speichern".

        Phasen:

        1. Eingabe-Validierung je nach Speichermodus.
        2. Veraltete Layer-Referenzen rausfiltern (könnte z. B. sein,
           dass der Nutzer einen Layer im Projekt-Fenster gelöscht hat,
           während der Dialog offen war).
        3. Namens-Konflikte auflösen (siehe :meth:`_resolve_name_conflicts`).
        4. Überschreib-Rückfragen je nach Modus.
        5. Jobs vorbereiten und Hintergrund-Task starten.
        """
        selected_items = self.layer_list.selectedItems()
        if not selected_items:
            show_warning(
                self,
                self.tr("Missing input"),
                self.tr("Please select at least one layer."),
            )
            return

        if self.radio_single.isChecked():
            single_path = self.single_path_edit.text().strip()
            if not single_path:
                show_warning(
                    self,
                    self.tr("Missing input"),
                    self.tr("Please provide a path for the GeoPackage file."),
                )
                return
            single_path = ensure_gpkg_extension(single_path)
            parent_dir = os.path.dirname(single_path)
            if not is_existing_directory(parent_dir):
                show_warning(
                    self,
                    self.tr("Missing input"),
                    self.tr("The target directory does not exist:\n%s") % parent_dir,
                )
                return
        elif self.radio_multi.isChecked():
            out_dir = self.dir_edit.text().strip()
            name_val = self.name_edit.text().strip()
            if not is_existing_directory(out_dir):
                show_warning(
                    self,
                    self.tr("Missing input"),
                    self.tr("Please provide a valid target directory."),
                )
                return
            if not name_val:
                show_warning(
                    self,
                    self.tr("Missing input"),
                    self.tr("Please enter a prefix."),
                )
                return

        # In der Zwischenzeit gelöschte Layer werfen beim Zugriff eine
        # RuntimeError – raus damit, statt später im Worker zu crashen.
        raw_layers = [item.data(Qt.UserRole) for item in selected_items]
        layers = []
        for layer in raw_layers:
            try:
                _ = layer.name()
                layers.append(layer)
            except (RuntimeError, AttributeError):
                continue

        if not layers:
            show_warning(
                self,
                self.tr("No valid layers"),
                self.tr(
                    "The selected layers are no longer available.\n"
                    "Please close the dialog and reopen it."
                ),
            )
            return

        name_map = self._resolve_name_conflicts(layers)
        if name_map is None:
            return

        remote_modes = {layer.id(): self._export_mode_for(layer) for layer in layers}

        if self.radio_single.isChecked():
            mode, path, prefix = "single", single_path, ""
            if not self._confirm_overwrite_single(path):
                return
        elif self.radio_multi.isChecked():
            mode, path, prefix = "multi", out_dir, name_val
            if not self._confirm_overwrite_multi(layers, path, prefix, name_map):
                return
        else:
            gpkg_path = self.gpkg_edit.text().strip()
            if not is_existing_file(gpkg_path):
                show_warning(
                    self,
                    self.tr("Missing input"),
                    self.tr("Please choose a valid existing GeoPackage file."),
                )
                return
            mode, path, prefix = "append", gpkg_path, ""
            if not self._confirm_overwrite_append(layers, path, name_map):
                return

        jobs, pre_errors = self._exporter.prepare_jobs(
            layers, name_map, remote_modes, mode, path, prefix,
        )
        if not jobs:
            show_warning(
                self,
                self.tr("No exportable layers"),
                self.tr("No layers remain for export:\n\n") + "\n".join(pre_errors),
            )
            return

        replace_after = self.chk_replace.isChecked()
        task = self._exporter.create_task(
            self.tr("GeoPackage Export"),
            jobs,
            lambda errors: self._on_task_completed(errors, pre_errors, jobs, replace_after),
        )
        # Werden Quell-Layer während des Exports gelöscht, soll der
        # Worker das mitbekommen und den Job überspringen.
        for layer in layers:
            try:
                layer.destroyed.connect(
                    lambda _=None, lid=layer.id(), t=task: t.mark_layer_deleted(lid)
                )
            except (RuntimeError, AttributeError):
                continue

        QgsApplication.taskManager().addTask(task)
        push_bar_message(
            self.iface,
            self.tr("GeoPackage Export"),
            self.tr("Export running in background (%d layers) …") % len(jobs),
            Qgis.Info,
            duration=3,
        )
        self.accept()

    def _on_task_completed(self, errors, pre_errors, jobs, replace_after):
        """Callback des Hintergrund-Tasks – läuft im Main-Thread.

        Zeigt in der Meldungs-Leiste eine Zusammenfassung und ersetzt
        auf Wunsch die Original-Layer im Projekt durch die geschriebenen
        GeoPackage-Layer.

        Args:
            errors: Fehlermeldungen aus dem Worker.
            pre_errors: Fehlermeldungen aus :meth:`prepare_jobs`.
            jobs: Liste der erfolgreich geschriebenen Jobs.
            replace_after: Ist True, werden die Quell-Layer im Projekt
                ersetzt (siehe Checkbox im Dialog).
        """
        all_errors = list(pre_errors) + list(errors)
        if all_errors:
            preview = "\n".join(all_errors[:5])
            if len(all_errors) > 5:
                preview += self.tr("\n… and %d more") % (len(all_errors) - 5)
            push_bar_message(
                self.iface,
                self.tr("GeoPackage Export"),
                self.tr("Completed with errors:\n%s") % preview,
                Qgis.Warning,
                duration=10,
            )
            return

        if replace_after:
            replaced, failed = self._exporter.replace_layers_from_jobs(jobs)
            msg = self.tr("✅  %d layers saved") % len(jobs)
            if replaced:
                msg += self.tr(" · %d replaced in project") % replaced
            if failed:
                msg += self.tr(" · ⚠ %d not replaced") % failed
            push_bar_message(self.iface, self.tr("Done"), msg, Qgis.Info, duration=5)
        else:
            push_bar_message(
                self.iface,
                self.tr("Done"),
                self.tr("✅  %d layers saved as GeoPackage") % len(jobs),
                Qgis.Info,
                duration=5,
            )

    def _confirm_overwrite_single(self, gpkg_path) -> bool:
        """Fragt beim Überschreiben einer bestehenden GPKG nach (Single-Modus).

        Args:
            gpkg_path: Zielpfad.

        Returns:
            True, wenn der Nutzer überschreiben möchte (oder die Datei
            noch gar nicht existiert).
        """
        if not is_existing_file(gpkg_path):
            return True
        return ask_yes_no(
            self,
            self.tr("File already exists"),
            self.tr(
                "The file\n%s\nalready exists.\n\n"
                "Overwriting will remove ALL existing data in this file "
                "and replace it with the selected layers.\n\n"
                "If you only want to add individual layers, use the "
                "\"Add layers to an existing GeoPackage\" mode instead.\n\n"
                "Replace the entire file now?"
            ) % gpkg_path,
        )

    def _confirm_overwrite_multi(self, layers, out_dir, prefix, name_map) -> bool:
        """Fragt nach, wenn im Multi-Modus bereits Dateien existieren.

        Returns:
            True, wenn der Nutzer überschreiben möchte (oder nichts
            kollidiert).
        """
        paths = build_multi_paths(layers, out_dir, prefix, name_map)
        existing = [p for p in paths.values() if is_existing_file(p)]
        if not existing:
            return True
        names_preview = "\n".join(os.path.basename(p) for p in existing[:5])
        if len(existing) > 5:
            names_preview += self.tr("\n… and %d more") % (len(existing) - 5)
        return ask_yes_no(
            self,
            self.tr("Files already exist"),
            self.tr("%d file(s) already exist:\n\n%s\n\nOverwrite all?")
            % (len(existing), names_preview),
        )

    def _confirm_overwrite_append(self, layers, gpkg_path, name_map) -> bool:
        """Fragt beim Anhängen nach, wenn Tabellennamen schon vergeben sind.

        Returns:
            True, wenn der Nutzer überschreiben möchte (oder nichts
            kollidiert).
        """
        existing_names = self._exporter.get_existing_gpkg_layers(gpkg_path)
        conflicts = [
            name_map[layer.id()]
            for layer in layers
            if name_map[layer.id()] in existing_names
        ]
        if not conflicts:
            return True
        preview = "\n".join(f"• {n}" for n in conflicts[:8])
        if len(conflicts) > 8:
            preview += self.tr("\n… and %d more") % (len(conflicts) - 8)
        return ask_yes_no(
            self,
            self.tr("Tables already exist"),
            self.tr("The following data already exist in the GeoPackage:\n\n%s\n\nOverwrite data?")
            % preview,
        )

    def _export_mode_for(self, layer) -> str:
        """Liefert den vom Nutzer gewählten Export-Modus für einen Layer.

        Für Remote-Layer (WFS/OAPIF) wird der aktuelle Wert der
        zugehörigen Combobox ausgelesen. Für lokale Layer
        (``ogr``/``memory``/``postgres`` …) gibt es keine Wahl –
        sie liefern immer ``EXPORT_MODE_FULL``.

        Args:
            layer: Der zu inspizierende Vektor-Layer.

        Returns:
            Einer der Werte ``EXPORT_MODE_FULL``/``BBOX``/``SELECTION``.
        """
        if not is_remote_feature_layer(layer):
            return EXPORT_MODE_FULL
        combo = self._remote_mode_combos.get(layer.id())
        if combo is None:
            return EXPORT_MODE_FULL
        data = combo.currentData()
        return data or EXPORT_MODE_FULL

    def _resolve_name_conflicts(self, layers):
        """Baut die Abbildung ``{layer.id(): export_name}`` mit Konflikt-Auflösung.

        Wenn mehrere ausgewählte Layer denselben Namen haben, würden
        sie sich in der GeoPackage gegenseitig überschreiben. In dem
        Fall fragt der Dialog den Nutzer, ob er automatisch mit
        ``_2``, ``_3`` … indizieren möchte – oder abbricht, um im
        Projekt manuell umzubenennen.

        Args:
            layers: Die ausgewählten Layer.

        Returns:
            ``{layer.id(): effektiver Exportname}`` oder ``None``, wenn
            der Nutzer abgebrochen hat.
        """
        def effective_name(layer):
            """Name des Layers, mit sinnvollem Fallback bei Leer-Namen."""
            name = (layer.name() or "").strip()
            return name or f"unnamed_{layer.id()}"

        counts = {}
        for layer in layers:
            counts[effective_name(layer)] = counts.get(effective_name(layer), 0) + 1
        duplicates = {name: n for name, n in counts.items() if n > 1}

        if not duplicates:
            return {layer.id(): effective_name(layer) for layer in layers}

        preview = "\n".join(f"• {n}  ({count}×)" for n, count in list(duplicates.items())[:8])
        if len(duplicates) > 8:
            preview += self.tr("\n… and %d more") % (len(duplicates) - 8)

        box = QMessageBox(self)
        box.setWindowTitle(self.tr("Layers with identical names found"))
        box.setIcon(QMessageBox.Warning)
        box.setText(
            self.tr(
                "The selection contains %d layer names that appear multiple times:\n\n%s\n\n"
                "On export, layers with identical names would overwrite each other."
            ) % (len(duplicates), preview)
        )
        box.setInformativeText(
            self.tr(
                "How do you want to proceed?\n\n"
                "• Auto-index:  names are extended with _2, _3 …\n"
                "• Cancel:  the dialog stays open, layers can be renamed manually in the project"
            )
        )
        btn_index  = box.addButton(self.tr("Auto-index"), QMessageBox.AcceptRole)
        btn_cancel = box.addButton(self.tr("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_index)
        box.exec_()

        if box.clickedButton() is btn_cancel:
            return None

        used_names = set()
        name_map   = {}
        occurrence = {}

        for layer in layers:
            base = effective_name(layer)
            if counts[base] == 1:
                name_map[layer.id()] = base
                used_names.add(base)
                continue

            n = occurrence.get(base, 0) + 1
            occurrence[base] = n
            if n == 1:
                candidate = base
            else:
                candidate = f"{base}_{n}"
                while candidate in used_names:
                    n += 1
                    candidate = f"{base}_{n}"
                occurrence[base] = n

            name_map[layer.id()] = candidate
            used_names.add(candidate)

        return name_map
