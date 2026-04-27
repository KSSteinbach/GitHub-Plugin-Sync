# -*- coding: utf-8 -*-
"""Hilfsfunktionen rund um QGIS-Layer.

Alle Funktionen arbeiten auf dem aktuellen QGIS-Projekt (``QgsProject.instance()``)
und liefern Layer-Listen in der Reihenfolge, wie sie im Layer-Bedienfeld
erscheinen (Legenden-Reihenfolge, inkl. Gruppenhierarchie).

Ein „Vektor-Layer" ist ein Layer mit geometrischen Objekten (Punkte,
Linien, Polygone). „Raster" (Bilder) oder „Mesh" (3D-Gitter) werden
hier bewusst ausgeschlossen – dieses Plugin exportiert nur Vektordaten.
"""

from qgis.core import QgsProject, QgsVectorLayer

from .constants import PROVIDER_MEMORY, REMOTE_FEATURE_PROVIDERS


def layers_in_tree_order():
    """Gibt alle Layer des aktuellen Projekts in Legenden-Reihenfolge zurück.

    Reihenfolge: wie im Layer-Bedienfeld von oben nach unten, inklusive
    Gruppen. Ungültige Layer (``None``) werden übersprungen.

    Returns:
        Liste der ``QgsMapLayer``-Instanzen in Anzeige-Reihenfolge.
    """
    root = QgsProject.instance().layerTreeRoot()
    return [node.layer() for node in root.findLayers() if node.layer() is not None]


def get_temp_layers():
    """Liefert alle temporären Vektor-Layer des Projekts.

    „Temporär" bedeutet: der Layer lebt nur im Arbeitsspeicher
    (Provider ``memory``). Solche Layer gehen beim Schließen des Projekts
    verloren – genau die Kandidaten, die dieses Plugin gern persistent
    als GeoPackage sichert.

    Returns:
        Liste von ``QgsVectorLayer`` in Legenden-Reihenfolge.
    """
    return [
        layer
        for layer in layers_in_tree_order()
        if isinstance(layer, QgsVectorLayer)
        and layer.dataProvider() is not None
        and layer.dataProvider().name() == PROVIDER_MEMORY
    ]


def get_all_vector_layers():
    """Liefert alle Vektor-Layer des Projekts.

    Schließt ausdrücklich Raster-, Mesh- und sonstige Nicht-Vektor-Layer
    aus – die kann dieses Plugin nicht exportieren.

    Returns:
        Liste von ``QgsVectorLayer`` in Legenden-Reihenfolge.
    """
    return [
        layer
        for layer in layers_in_tree_order()
        if isinstance(layer, QgsVectorLayer)
    ]


def is_remote_feature_layer(layer) -> bool:
    """True, wenn der Layer seine Daten über das Netz bezieht.

    „Remote" heißt hier: WFS (Web Feature Service) oder OGC API –
    Features. Für solche Layer ist ein vollständiger Export potenziell
    teuer (alle Features müssen vom Server geladen werden), deshalb
    bekommt der Nutzer für sie eine zusätzliche Auswahlmöglichkeit im
    Dialog.

    Args:
        layer: Beliebiger QGIS-Layer (Vektor, Raster, …).

    Returns:
        True nur bei Vektor-Layern mit WFS- oder OAPIF-Provider.
    """
    if not isinstance(layer, QgsVectorLayer):
        return False
    provider = layer.dataProvider()
    return provider is not None and provider.name() in REMOTE_FEATURE_PROVIDERS
