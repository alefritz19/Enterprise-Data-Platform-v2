#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV EXTRACTOR
=============
Findet, liest und archiviert CSV-Dateien aus dem Eingangsverzeichnis.
Unterstützt UTF-8 und Latin-1 Kodierung automatisch.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


class CSVExtractor:

    def __init__(self, config: dict):
        """
        Args:
            config: etl.source aus etl_config.yaml
        """
        self.pfad          = Path(config.get("path", "data/raw"))
        self.muster        = config.get("pattern", "*.csv")
        self.encoding      = config.get("encoding", "utf-8")
        self.separator     = config.get("separator", ",")
        self.processed_pfad = Path(config.get("processed_path", "data/processed"))
        self.error_pfad    = Path(config.get("error_path", "data/errors"))

        # Verzeichnisse anlegen
        for p in [self.pfad, self.processed_pfad, self.error_pfad]:
            p.mkdir(parents=True, exist_ok=True)

    def finde_dateien(self) -> List[Path]:
        """Gibt alle CSV-Dateien im Eingangsverzeichnis zurück."""
        dateien = sorted(self.pfad.glob(self.muster))
        logger.info("📁 %d CSV-Datei(en) gefunden in: %s", len(dateien), self.pfad)
        return dateien

    def lese_csv(self, datei: Path) -> pd.DataFrame:
        """
        Liest eine CSV-Datei.
        Probiert zuerst die konfigurierte Kodierung, dann Latin-1.

        Returns:
            DataFrame mit Rohdaten (alle Spalten als String)
        """
        for enc in [self.encoding, "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(
                    datei,
                    encoding=enc,
                    sep=self.separator,
                    dtype=str,            # Alles als String – Bereinigung kommt später
                    skipinitialspace=True,
                    on_bad_lines="warn",
                )
                # Spaltennamen bereinigen
                df.columns = (
                    df.columns.str.strip()
                               .str.lower()
                               .str.replace(r"\s+", "_", regex=True)
                )
                logger.info(
                    "   📄 %s: %d Zeilen, %d Spalten (Kodierung: %s)",
                    datei.name, len(df), len(df.columns), enc
                )
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                raise RuntimeError(f"Fehler beim Lesen von {datei.name}: {e}") from e

        raise RuntimeError(f"Konnte {datei.name} mit keiner Kodierung lesen")

    def archiviere_datei(self, datei: Path):
        """Verschiebt verarbeitete Datei nach processed/."""
        ziel = self.processed_pfad / f"{datetime.now():%Y%m%d_%H%M%S}_{datei.name}"
        shutil.move(str(datei), str(ziel))
        logger.debug("   ✅ Archiviert: %s", ziel.name)

    def verschiebe_nach_error(self, datei: Path, fehler: str):
        """Verschiebt fehlerhafte Datei nach errors/."""
        ziel = self.error_pfad / f"{datetime.now():%Y%m%d_%H%M%S}_{datei.name}"
        shutil.move(str(datei), str(ziel))
        # Fehler-Log dazuschreiben
        (self.error_pfad / f"{ziel.stem}.txt").write_text(fehler, encoding="utf-8")
        logger.warning("   ⚠️ Fehlerhafte Datei verschoben: %s", ziel.name)
