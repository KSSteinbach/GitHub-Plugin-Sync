# -*- coding: utf-8 -*-

"""Reine GeoPackage-Export-Logik ohne Qt-Widget-Abhängigkeiten.

Dieses Modul kapselt das Schreiben von QGIS-Layern in GeoPackage-
Dateien (einzeln, gesammelt oder angehängt), die Stil-Übernahme sowie
das Ersetzen der Original-Layer im Projekt.

Bewusste Trennung: Hier passieren **keine** Benutzer-Rückfragen und
**keine** Widget-Zugriffe – die gehören in den Dialog-Code
(``gui/main_dialog.py``). So lässt sich die Export-Logik später
wiederverwenden oder separat testen.

Die eigentliche Schreibarbeit läuft in einem Hintergrund-Thread
(``GpkgExportTask``, siehe unten), damit die QGIS-Oberfläche reagibel
bleibt.
"""

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from qgis.core import (
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsLayerTreeLayer,
    QgsLayerTreeNode,
    QgsProject,
    QgsTask,
    QgsVectorFileWriter,
    QgsVectorLayer,
    Qgis,
)
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtXml import QDomDocument

# Konstanten und Hilfsmodule werden zentral importiert und unten
# re-exportiert, damit bisherige Aufrufer (``from .export_logic import
# EXPORT_MODE_FULL, is_remote_feature_layer, safe_filename, …``)
# unverändert weiterlaufen.
from .constants import (
    DRIVER_GPKG,
    EXPORT_MODE_BBOX,
    EXPORT_MODE_FULL,
    EXPORT_MODE_SELECTION,
    FILE_EXT_GPKG,
    PROVIDER_OGR,
    REMOTE_FEATURE_PROVIDERS,
    SQLITE_LOCK_BASE_DELAY_S,
    SQLITE_LOCK_RETRY_ATTEMPTS,
)
from .layer_utils import is_remote_feature_layer
from .logging_utils import log_message
from .path_utils import is_existing_file, safe_filename
from .style_utils import export_layer_style, import_layer_style

# Rückwärtskompatible Aliase: frühere Versionen exportierten diese Namen
# direkt aus diesem Modul.
WFS_PROVIDER = "WFS"
OAPIF_PROVIDER = "OAPIF"


@dataclass
class LayerJob:
    """Thread-sicherer Snapshot eines Layers für den Export-Worker.

    Ein ``LayerJob`` bündelt alle Informationen, die der Worker-Thread
    zum Schreiben eines einzelnen Layers benötigt – so muss der Worker
    nicht mehr auf veränderliche Main-Thread-Objekte (z. B. den
    Layer-Baum) zugreifen.

    Wird ausschließlich im Main-Thread befüllt. Der Worker liest nur
    Kopien bzw. primitive Werte oder Objekte, die für sich thread-sicher
    sind (``QDomDocument``, ``SaveVectorOptions``).

    Attributes:
        layer_id: QGIS-interne ID des Quell-Layers (für Ersetzen später).
        export_name: Name, unter dem der Layer in der GPKG landet.
        layer: Referenz auf den Quell-``QgsVectorLayer``.
        style_doc: XML-Snapshot der Symbologie (Stil-Übertragung).
        options: Vorbereitete ``SaveVectorOptions`` für den OGR-Writer.
        gpkg_path: Ziel-Dateipfad der GeoPackage.
        tree_parent: Eltern-Knoten im Layer-Baum (für Ersetzen).
        tree_index: Position unterhalb ``tree_parent`` (für Ersetzen).
    """
    layer_id: str
    export_name: str
    layer: QgsVectorLayer
    style_doc: QDomDocument
    options: QgsVectorFileWriter.SaveVectorOptions
    gpkg_path: str
    tree_parent: Optional[QgsLayerTreeNode]
    tree_index: int


def build_multi_paths(layers, out_dir, prefix, name_map):
    """Liefert ``{layer.id(): Dateipfad}`` für den Multi-File-Export.

    Im Multi-Modus bekommt jeder Layer seine eigene GPKG-Datei.
    Da :func:`safe_filename` unterschiedliche Layernamen auf denselben
    String abbilden kann (z. B. „Layer/A" und „Layer#A" beide →
    ``Layer_A``), werden kollidierende Dateinamen automatisch mit
    ``_2``, ``_3`` … indiziert, damit sich die Exporte nicht
    gegenseitig überschreiben.

    Args:
        layers: Liste der zu exportierenden Vektor-Layer.
        out_dir: Zielverzeichnis.
        prefix: Vom Nutzer gewählter Dateinamen-Präfix.
        name_map: ``{layer.id(): export_name}`` aus der Namens-
            konflikt-Auflösung des Dialogs.

    Returns:
        Dict ``{layer.id(): absoluter Pfad zur .gpkg-Datei}``.
    """
    safe_prefix = safe_filename(prefix)
    paths = {}
    used = set()
    for layer in layers:
        base = f"{safe_prefix}{safe_filename(name_map[layer.id()])}"
        candidate = base
        n = 1
        while candidate.lower() in used:
            n += 1
            candidate = f"{base}_{n}"
        used.add(candidate.lower())
        paths[layer.id()] = os.path.join(out_dir, f"{candidate}{FILE_EXT_GPKG}")
    return paths


class GpkgExporter:
    """Kapselt die eigentliche GeoPackage-Schreiblogik.

    Der Exporter liest keine Qt-Widgets. Alle variablen Eingaben kommen
    als Argumente herein, Benutzer-Rückfragen bleiben im Dialog. Der
    eigentliche Schreibvorgang läuft in einem
    :class:`GpkgExportTask` im Hintergrund-Thread.

    Die ``iface``-Referenz wird nur für Kartenausschnitt-Abfragen (BBox-
    Modus) benötigt – nicht für UI-Ausgaben.
    """

    def __init__(self, iface):
        """Erzeugt einen Exporter.

        Args:
            iface: QGIS-``iface``. Wird nur für ``mapCanvas()``
                (BBox-Extent) gelesen – keine UI-Ausgaben hier.
        """
        self.iface = iface

    def tr(self, message: str) -> str:
        """Übersetzt ``message`` im Qt-Kontext dieses Moduls."""
        return QCoreApplication.translate("GpkgExporter", message)

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def prepare_jobs(
        self,
        layers,
        name_map,
        remote_modes,
        mode: str,
        out_path: str,
        prefix: str = "",
    ) -> Tuple[List[LayerJob], List[str]]:
        """Baut die Job-Liste für den asynchronen Export auf dem Main-Thread.

        Hier passiert alles, was noch Zugriff auf Main-Thread-Objekte
        braucht: Stil-Snapshot, Tree-Position merken, WFS-/BBox-Filter
        vorbereiten. Der Worker-Thread bekommt anschließend nur noch
        fertige ``LayerJob``-Instanzen.

        Args:
            layers: Zu exportierende Vektor-Layer.
            name_map: ``{layer.id(): export_name}`` (Namenskonflikte
                sind bereits aufgelöst).
            remote_modes: ``{layer.id(): EXPORT_MODE_*}`` für Remote-
                Layer; lokale Layer dürfen fehlen (Default: ``FULL``).
            mode: ``"single"``, ``"multi"`` oder ``"append"``.
            out_path: Einzel-/Anhängen-Modus: GPKG-Pfad. Multi-Modus:
                Zielverzeichnis.
            prefix: Dateinamen-Präfix (nur Multi-Modus).

        Returns:
            Tupel ``(jobs, pre_errors)``. ``pre_errors`` sammelt
            Fehler, die schon im Main-Thread feststehen (z. B. leere
            WFS-Selektion), und werden später gemeinsam mit Worker-
            Fehlern angezeigt.
        """
        jobs: List[LayerJob] = []
        pre_errors: List[str] = []
        multi_paths = build_multi_paths(layers, out_path, prefix, name_map) if mode == "multi" else {}
        root = QgsProject.instance().layerTreeRoot()

        for i, layer in enumerate(layers):
            export_name = name_map[layer.id()]

            if mode == "multi":
                gpkg_path = multi_paths[layer.id()]
                action = QgsVectorFileWriter.CreateOrOverwriteFile
            elif mode == "single":
                gpkg_path = out_path
                action = (
                    QgsVectorFileWriter.CreateOrOverwriteFile if i == 0
                    else QgsVectorFileWriter.CreateOrOverwriteLayer
                )
            else:  # append
                gpkg_path = out_path
                action = QgsVectorFileWriter.CreateOrOverwriteLayer

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = DRIVER_GPKG
            options.layerName = export_name
            options.actionOnExistingFile = action
            layer_options = self._layer_options_for(layer)
            if layer_options:
                options.layerOptions = layer_options

            filter_err = self._apply_wfs_filter(
                layer, options, remote_modes.get(layer.id(), EXPORT_MODE_FULL)
            )
            if filter_err:
                pre_errors.append(self.tr("• %s: %s") % (export_name, filter_err))
                continue

            tree_node = root.findLayer(layer.id())
            if tree_node is not None:
                tree_parent = tree_node.parent()
                tree_index = tree_parent.children().index(tree_node)
            else:
                tree_parent = None
                tree_index = 0

            jobs.append(LayerJob(
                layer_id=layer.id(),
                export_name=export_name,
                layer=layer,
                style_doc=self._snapshot_style(layer),
                options=options,
                gpkg_path=gpkg_path,
                tree_parent=tree_parent,
                tree_index=tree_index,
            ))

        return jobs, pre_errors

    def get_existing_gpkg_layers(self, gpkg_path):
        """Liest die Liste der bereits in einer GPKG enthaltenen Layernamen.

        Öffnet die Datei als Probe-Layer und liest die Unter-Layer
        (``provider.subLayers()``). Das Ergebnis wird für die
        Überschreib-Bestätigung im „Anhängen"-Modus benötigt.

        Args:
            gpkg_path: Pfad zur bestehenden GeoPackage.

        Returns:
            Menge (``set``) der in der Datei enthaltenen Layernamen.
            Leeres ``set``, wenn die Datei nicht lesbar ist.
        """
        probe = QgsVectorLayer(gpkg_path, "_probe_", PROVIDER_OGR)
        if not probe.isValid():
            return set()
        provider = probe.dataProvider()
        if provider is None:
            return set()
        names = set()
        for sub in provider.subLayers():
            parts = sub.split("!!::!!")
            if len(parts) >= 2:
                names.add(parts[1])
        return names

    def create_task(
        self,
        description: str,
        jobs: List[LayerJob],
        on_finished_cb: Callable[[List[str]], None],
    ) -> "GpkgExportTask":
        """Baut einen Hintergrund-Task für den eigentlichen Export.

        Args:
            description: Anzeigetext im QGIS-Task-Manager.
            jobs: Fertige Job-Liste aus :meth:`prepare_jobs`.
            on_finished_cb: Wird im Main-Thread mit der Fehlerliste
                aufgerufen, sobald der Export abgeschlossen ist.

        Returns:
            Den noch nicht gestarteten ``GpkgExportTask``.
        """
        return GpkgExportTask(description, jobs, self, on_finished_cb)

    def replace_layers_from_jobs(self, jobs: List[LayerJob]) -> Tuple[int, int]:
        """Ersetzt Original-Layer im Projekt durch die geschriebenen GPKG-Layer.

        Nutzt die im ``LayerJob`` gespeicherte Tree-Position und den
        Stil-Snapshot, damit Layer-Verschiebungen oder Umgruppierungen
        während des Exports erhalten bleiben. Robust gegenüber
        gelöschten Layern und verschwundenen Gruppen – in solchen Fällen
        landet der Ersatzlayer unter dem Projekt-Root.

        Args:
            jobs: Liste der erfolgreich geschriebenen Jobs.

        Returns:
            Tupel ``(replaced, failed)`` – Anzahl erfolgreich ersetzter
            bzw. nicht ersetzbarer Layer.
        """
        replaced = 0
        failed = 0
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        for job in jobs:
            if sip.isdeleted(job.layer):
                failed += 1
                continue
            try:
                layer_id = job.layer.id()
            except RuntimeError:
                failed += 1
                continue

            if not is_existing_file(job.gpkg_path):
                failed += 1
                continue

            uri = f"{job.gpkg_path}|layername={job.export_name}"
            new_layer = QgsVectorLayer(uri, job.export_name, PROVIDER_OGR)
            if not new_layer.isValid():
                failed += 1
                continue

            if job.tree_parent is not None and not sip.isdeleted(job.tree_parent):
                parent = job.tree_parent
                idx = min(job.tree_index, len(parent.children()))
            else:
                parent = root
                idx = len(root.children())

            new_layer.loadDefaultStyle()
            if not job.style_doc.isNull():
                import_layer_style(new_layer, job.style_doc)

            project.addMapLayer(new_layer, False)
            parent.insertChildNode(idx, QgsLayerTreeLayer(new_layer))
            project.removeMapLayer(layer_id)
            replaced += 1

        return replaced, failed

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _layer_options_for(self, layer) -> list:
        """Liefert GPKG-layerOptions für den OGR-Treiber.

        Hintergrund: Liefert ein Layer (typisch bei WFS/GML/GeoJSON) ein Feld
        namens 'fid' mit non-Integer-Typ (z.B. double), versucht der GPKG-
        Treiber, diese Spalte als Primärschlüssel zu verwenden, und scheitert
        mit "Wrong field type for FID". Dadurch wird die Tabelle leer
        exportiert. Wir geben dem Treiber deshalb einen kollisionsfreien
        FID-Namen, sodass eine frische Integer-Spalte erzeugt wird.
        """
        fields = getattr(layer, "fields", lambda: None)()
        if fields is None:
            return []
        integer_types = (
            QVariant.Int, QVariant.UInt, QVariant.LongLong, QVariant.ULongLong
        )
        names_lower = {f.name().lower() for f in fields}
        conflict = any(
            f.name().lower() == "fid" and f.type() not in integer_types
            for f in fields
        )
        if not conflict:
            return []
        candidate = "auto_fid"
        n = 1
        while candidate.lower() in names_lower:
            n += 1
            candidate = f"auto_fid_{n}"
        return [f"FID={candidate}"]

    def _apply_wfs_filter(self, layer, options, mode):
        """Schränkt die exportierten Features eines Remote-Layers ein.

        Je nach ``mode`` werden ``options.filterExtent`` (Bildschirm-
        ausschnitt) oder ``options.onlySelectedFeatures`` gesetzt. Bei
        BBox-Modus wird der Ausschnitt bei Bedarf in das Layer-CRS
        („Koordinatenreferenzsystem") transformiert.

        Args:
            layer: Quell-Layer (nur WFS/OAPIF relevant).
            options: ``SaveVectorOptions``, die der Writer bekommt.
            mode: Einer von ``EXPORT_MODE_FULL/BBOX/SELECTION``.

        Returns:
            ``None`` bei Erfolg; sonst eine Fehlermeldung als String
            (wird vom Aufrufer in die ``pre_errors``-Liste aufgenommen).
        """
        if not is_remote_feature_layer(layer):
            return None

        if mode == EXPORT_MODE_FULL:
            return None

        if mode == EXPORT_MODE_SELECTION:
            if layer.selectedFeatureCount() == 0:
                return self.tr("No features selected – layer skipped.")
            options.onlySelectedFeatures = True
            return None

        if mode == EXPORT_MODE_BBOX:
            canvas = self.iface.mapCanvas()
            extent = canvas.extent()
            if extent.isEmpty():
                return self.tr("Map canvas extent is empty – BBox filter not possible.")
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            if canvas_crs != layer_crs:
                if not canvas_crs.isValid() or not layer_crs.isValid():
                    return self.tr("CRS of canvas or layer is invalid – BBox filter not possible.")
                try:
                    xform = QgsCoordinateTransform(
                        canvas_crs, layer_crs, QgsProject.instance()
                    )
                    extent = xform.transformBoundingBox(extent)
                except Exception as exc:
                    return self.tr("BBox transformation failed (%s → %s): %s") % (
                        canvas_crs.authid() or "?", layer_crs.authid() or "?", exc,
                    )
                if extent.isEmpty():
                    return self.tr("Transformed map canvas extent is empty – BBox filter not possible.")
            options.filterExtent = extent
            return None

        return None

    def _snapshot_style(self, source_layer) -> QDomDocument:
        """Erzeugt eine thread-sichere Kopie der Layer-Symbologie (Main-Thread).

        Hintergrund: Der Worker-Thread darf nicht direkt auf den
        Quell-Layer zugreifen (Qt-Objekte sind nicht thread-sicher).
        Deshalb serialisieren wir den Stil hier im Main-Thread in ein
        ``QDomDocument`` – das kann anschließend gefahrlos kopiert und
        im Worker ausgewertet werden.

        Args:
            source_layer: Quell-``QgsVectorLayer``.

        Returns:
            ``QDomDocument`` mit dem Stil-Snapshot (ggf. leer, wenn der
            Export fehlschlug – Fehler sind geloggt).
        """
        style_doc = QDomDocument()
        export_layer_style(source_layer, style_doc)
        return style_doc

    def _save_style_from_snapshot(
        self,
        style_doc: QDomDocument,
        gpkg_path: str,
        export_name: str,
    ) -> bool:
        """Schreibt einen vorab gemachten Stil-Snapshot in die GPKG.

        Darf im Worker-Thread laufen: liest nur das ``QDomDocument``,
        öffnet die GPKG als frischen OGR-Layer und speichert den Stil
        in der ``layer_styles``-Tabelle.

        Args:
            style_doc: Stil-Snapshot (siehe :meth:`_snapshot_style`).
            gpkg_path: Pfad der geschriebenen GeoPackage.
            export_name: Tabellenname innerhalb der GPKG.

        Returns:
            True bei Erfolg, False bei Fehler (Meldung landet im Log).
        """
        uri = f"{gpkg_path}|layername={export_name}"
        gpkg_layer = QgsVectorLayer(uri, export_name, PROVIDER_OGR)
        if not gpkg_layer.isValid():
            log_message(
                self.tr("Skipped style save for '%s': layer could not be loaded from GeoPackage.") % export_name,
                Qgis.Warning,
            )
            return False

        if not style_doc.isNull():
            import_layer_style(gpkg_layer, style_doc)

        err_msg = gpkg_layer.saveStyleToDatabase(export_name, "", True, "")
        if err_msg:
            log_message(
                self.tr("Style could not be written to GeoPackage ('%s'): %s") % (export_name, err_msg),
                Qgis.Warning,
            )
            return False
        return True

    def _fix_layer_styles_table(self, gpkg_path, written):
        """Räumt Inkonsistenzen in der ``layer_styles``-Tabelle auf.

        Umgeht einen bekannten QGIS-Core-Bug: ``saveStyleToDatabase()``
        kann in ``layer_styles`` Zeilen mit falschem ``f_table_name`` /
        ``f_geometry_column`` oder veraltete Duplikate hinterlassen
        (insbesondere beim Überschreiben). Folge: Beim Wieder-Öffnen der
        GPKG wird der falsche oder gar kein Stil geladen.

        Fehler hier dürfen einen erfolgreichen Export **niemals** kippen
        – der Stil ist ein Extra, die Daten stehen bereits sicher.

        Args:
            gpkg_path: Pfad zur betroffenen GeoPackage.
            written: Liste der in diesem Lauf neu geschriebenen
                Layernamen – nur für die wird aufgeräumt.
        """
        if not written:
            return

        last_err = None
        for attempt in range(SQLITE_LOCK_RETRY_ATTEMPTS):
            conn = None
            try:
                conn = sqlite3.connect(gpkg_path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='layer_styles'"
                )
                if cur.fetchone() is None:
                    return

                for export_name in written:
                    cur.execute(
                        "SELECT column_name FROM gpkg_geometry_columns "
                        "WHERE table_name=?",
                        (export_name,),
                    )
                    row = cur.fetchone()
                    geom_col = row[0] if row and row[0] else "geom"

                    cur.execute(
                        "UPDATE layer_styles "
                        "SET f_table_name=?, f_geometry_column=? "
                        "WHERE styleName=? OR f_table_name=?",
                        (export_name, geom_col, export_name, export_name),
                    )
                    cur.execute(
                        "DELETE FROM layer_styles "
                        "WHERE f_table_name=? AND id < "
                        "(SELECT MAX(id) FROM layer_styles WHERE f_table_name=?)",
                        (export_name, export_name),
                    )
                    cur.execute(
                        "UPDATE layer_styles SET useAsDefault=0 WHERE f_table_name=?",
                        (export_name,),
                    )
                    cur.execute(
                        "UPDATE layer_styles SET useAsDefault=1 "
                        "WHERE id=(SELECT MAX(id) FROM layer_styles WHERE f_table_name=?)",
                        (export_name,),
                    )

                conn.commit()
                return
            except sqlite3.OperationalError as exc:
                last_err = exc
                if "locked" in str(exc).lower():
                    # Exponentiell ansteigende Wartezeit, damit die GPKG
                    # ggf. wieder frei wird (QGIS hält sie manchmal noch
                    # einen Moment gelockt nach dem Writer-Schreibvorgang).
                    time.sleep(SQLITE_LOCK_BASE_DELAY_S * (attempt + 1))
                    continue
                break
            except sqlite3.Error as exc:
                last_err = exc
                break
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass

        if last_err is not None:
            log_message(
                self.tr("layer_styles fix-up in '%s' failed: %s")
                % (gpkg_path, last_err),
                Qgis.Warning,
            )


class GpkgExportTask(QgsTask):
    """Hintergrund-Task, der die LayerJobs in GeoPackages schreibt.

    QgsTask.run() läuft im Worker-Thread, finished() ruft QGIS im Main-Thread.
    Das Ergebnis wird per Callback (on_finished_cb) an den Aufrufer gemeldet
    — keine eigenen pyqtSignals, um Thread-Probleme zu vermeiden.
    """

    def __init__(
        self,
        description: str,
        jobs: List[LayerJob],
        exporter: "GpkgExporter",
        on_finished_cb: Callable[[List[str]], None],
    ):
        super().__init__(description, QgsTask.CanCancel)
        self._jobs = jobs
        self._exporter = exporter
        self._on_finished_cb = on_finished_cb
        self._errors: List[str] = []
        self._written: List[Tuple[str, str]] = []  # (export_name, gpkg_path)
        self._deleted_ids: set = set()
        self._lock = threading.Lock()

    def tr(self, message: str) -> str:
        """Übersetzt ``message`` im Qt-Kontext dieses Tasks."""
        return QCoreApplication.translate("GpkgExportTask", message)

    def mark_layer_deleted(self, layer_id: str) -> None:
        """Vom Main-Thread aufgerufen, wenn während des Exports ein Layer gelöscht wird.

        Sorgt dafür, dass der Worker beim nächsten Job-Schritt den
        gelöschten Layer erkennt und sauber überspringt, statt auf ein
        ungültiges C++-Objekt zuzugreifen.
        """
        with self._lock:
            self._deleted_ids.add(layer_id)

    def run(self) -> bool:
        total = len(self._jobs) or 1
        for i, job in enumerate(self._jobs):
            if self.isCanceled():
                self._errors.append(self.tr("• Cancelled by user – not all layers were saved."))
                return False

            with self._lock:
                deleted = job.layer_id in self._deleted_ids
            if deleted or sip.isdeleted(job.layer):
                self._errors.append(
                    self.tr("• %s: layer deleted during export.") % job.export_name
                )
                self.setProgress((i + 1) / total * 100)
                continue

            err_code, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                job.layer, job.gpkg_path, QgsCoordinateTransformContext(), job.options
            )
            if err_code != QgsVectorFileWriter.NoError:
                self._errors.append(
                    self.tr("• %s: %s") % (job.export_name, err_msg)
                )
                self.setProgress((i + 1) / total * 100)
                continue

            if not self._exporter._save_style_from_snapshot(
                job.style_doc, job.gpkg_path, job.export_name
            ):
                self._errors.append(
                    self.tr("• %s: style could not be written to the GPKG.")
                    % job.export_name
                )
            else:
                self._written.append((job.export_name, job.gpkg_path))

            log_message(
                f"Exported: {job.export_name} → {job.gpkg_path}",
                Qgis.Info,
            )
            self.setProgress((i + 1) / total * 100)

        # SQLite-Fixup pro Ziel-GPKG (Stil-Tabelle aufräumen).
        by_path: dict = {}
        for export_name, gpkg_path in self._written:
            by_path.setdefault(gpkg_path, []).append(export_name)
        for gpkg_path, names in by_path.items():
            self._exporter._fix_layer_styles_table(gpkg_path, names)

        return len(self._errors) == 0

    def finished(self, result: bool) -> None:
        """Wird von QGIS im Main-Thread aufgerufen, wenn :meth:`run` fertig ist.

        Ruft den beim Erzeugen übergebenen Callback mit der Fehlerliste
        auf. Exceptions aus dem Callback werden abgefangen und geloggt,
        damit QGIS nicht deswegen abstürzt.

        Args:
            result: Rückgabewert von :meth:`run` (hier nicht benötigt,
                die Fehlerliste ist feingranularer).
        """
        try:
            self._on_finished_cb(list(self._errors))
        except Exception as exc:  # noqa: BLE001
            log_message(f"on_finished_cb exception: {exc}", Qgis.Warning)
