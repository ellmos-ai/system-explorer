# -*- coding: utf-8 -*-
"""Wacht darueber, dass die hiesigen Manifest-Regeln nicht vom kanonischen Schema abweichen.

Hintergrund: `ellmos.module.v2` wird an drei Stellen geprueft -- vom JSON-Schema in
`.MODULES/_templates/`, vom Katalogbau und von diesem Paket. Am 2026-08-23 wurde
nachgemessen, dass alle drei **identische** Enums, Muster und Pflichtfelder tragen; die
Redundanz ist also heute kein Drift, sondern ein Risiko. Genau dieses Risiko wird hier
sichtbar gemacht, statt es zu verwalten.

Warum nicht direkt das Schema laden? Weil dieses Paket bewusst ohne externe Pfad- oder
Netzabhaengigkeit arbeitet. Das kanonische Schema liegt heute in einem OneDrive-Verzeichnis;
es im Produktivcode zu lesen, wuerde das Paket an einen Hostpfad binden. Der saubere Weg --
das Schema als installierbares Paket auszuliefern -- ist ein eigener Schritt. Bis dahin
prueft der Test **wenn** das Schema erreichbar ist und ueberspringt sich sonst: Ein
uebersprungener Test ist ehrlicher als eine erzwungene Kopplung.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from system_explorer import manifests

KANDIDATEN = [
    Path(os.path.expanduser("~")) / "OneDrive" / ".TOPICS" / ".AI" / ".MODULES"
    / "_templates" / "ellmos.module.v2.schema.json",
]


def _schema() -> dict | None:
    for p in KANDIDATEN:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


class ManifestSchemaDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = _schema()
        if self.schema is None:
            self.skipTest("kanonisches ellmos.module.v2-Schema auf diesem Host nicht erreichbar")

    def _enum(self, *pfad: str) -> set[str]:
        knoten = self.schema["properties"]
        for teil in pfad[:-1]:
            knoten = knoten[teil]["properties"]
        letzter = knoten[pfad[-1]]
        return set(letzter.get("enum") or letzter.get("items", {}).get("enum") or [])

    def test_surfaces_stimmen_mit_dem_schema_ueberein(self) -> None:
        self.assertEqual(set(manifests.SURFACES), self._enum("surfaces"))

    def test_netzgrenzen_stimmen_ueberein(self) -> None:
        self.assertEqual(set(manifests.NETWORK_BOUNDARIES), self._enum("boundaries", "network"))

    def test_datengrenzen_stimmen_ueberein(self) -> None:
        self.assertEqual(set(manifests.DATA_BOUNDARIES), self._enum("boundaries", "data"))

    def test_plattformen_stimmen_ueberein(self) -> None:
        self.assertEqual(set(manifests.PLATFORMS), self._enum("boundaries", "platforms"))

    def test_pflichtfelder_stimmen_ueberein(self) -> None:
        self.assertEqual(set(manifests.MODULE_REQUIRED), set(self.schema["required"]))


if __name__ == "__main__":
    unittest.main()
