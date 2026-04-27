# -*- coding: utf-8 -*-
"""Versionstolerante QGIS-Stil-Helfer.

Die Signatur von ``QgsVectorLayer.exportNamedStyle()`` und
``importNamedStyle()`` hat sich in QGIS 3.40 geändert (neuer Pflicht-
parameter ``QgsReadWriteContext``). Die Funktionen in diesem Modul
kapseln beide API-Varianten, damit der Rest des Plugins sich nicht um
QGIS-Versionen kümmern muss.

Hintergrund: Ein „Stil" ist in QGIS die visuelle Symbolisierung eines
Layers (Farben, Linienstärken, Kategorien, Beschriftungen …). Stile
werden als XML-Dokumente (``QDomDocument``) zwischen Layern portiert
und in der ``layer_styles``-Tabelle einer GeoPackage abgelegt.
"""

from qgis.core import Qgis, QgsReadWriteContext
from qgis.PyQt.QtCore import QCoreApplication

from .logging_utils import log_message


def _tr(text: str) -> str:
    """Übersetzt einen Text im Kontext dieses Moduls (Qt-Translation)."""
    return QCoreApplication.translate("StyleUtils", text)


def export_layer_style(layer, style_doc) -> bool:
    """Exportiert den Stil eines Layers in ein ``QDomDocument``.

    Unterstützt beide QGIS-API-Varianten:

    * QGIS ≤ 3.38: ``exportNamedStyle(doc)`` → ``errorMsg`` (str)
    * QGIS ≥ 3.40: ``exportNamedStyle(doc, readWriteContext)`` → ``(bool, str)``

    Fehler werden ins QGIS-Log geschrieben und dürfen den Export-Lauf
    nicht abbrechen – ein fehlender Stil ist weniger schlimm als keine
    Daten.

    Args:
        layer: Quell-``QgsVectorLayer``, dessen Stil exportiert wird.
        style_doc: Ziel-``QDomDocument``, das gefüllt wird.

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    try:
        result = layer.exportNamedStyle(style_doc, QgsReadWriteContext())
        if isinstance(result, tuple):
            success = result[0]
            err = result[1] if len(result) > 1 else ""
            if not success:
                log_message(
                    _tr("Style export for '%s' failed: %s") % (layer.name(), err),
                    Qgis.Warning,
                )
                return False
            return True
        if isinstance(result, str) and result:
            log_message(
                _tr("Style export for '%s' reported a warning: %s") % (layer.name(), result),
                Qgis.Warning,
            )
        return True
    except TypeError:
        # Alte API (QGIS ≤ 3.38): nur ein Argument.
        try:
            layer.exportNamedStyle(style_doc)
            return True
        except Exception as e:
            log_message(
                _tr("Style export for '%s' failed (legacy API): %s") % (layer.name(), str(e)),
                Qgis.Warning,
            )
            return False


def import_layer_style(layer, style_doc) -> bool:
    """Importiert einen Stil aus einem ``QDomDocument`` in einen Layer.

    Analog zu :func:`export_layer_style`: kompatibel zu QGIS ≤ 3.38 und
    ≥ 3.40.

    Args:
        layer: Ziel-``QgsVectorLayer``, der den Stil übernimmt.
        style_doc: Quell-``QDomDocument`` mit der Symbologie.

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    try:
        result = layer.importNamedStyle(style_doc, QgsReadWriteContext())
        if isinstance(result, tuple):
            success = result[0]
            err = result[1] if len(result) > 1 else ""
            if not success:
                log_message(
                    _tr("Style import for '%s' failed: %s") % (layer.name(), err),
                    Qgis.Warning,
                )
                return False
        return True
    except TypeError:
        try:
            layer.importNamedStyle(style_doc)
            return True
        except Exception as e:
            log_message(
                _tr("Style import for '%s' failed (legacy API): %s") % (layer.name(), str(e)),
                Qgis.Warning,
            )
            return False
