#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATEN-REINIGER
==============
Bereinigt Rohdaten Schritt für Schritt:
  1. Spaltennamen normalisieren
  2. Datum konvertieren (mehrere Formate)
  3. Betrag bereinigen (deutsches Format: 1.234,56)
  4. Menge bereinigen
  5. Textfelder säubern
  6. Pflichtfelder prüfen → fehlerhafte Zeilen verwerfen
  7. Duplikate entfernen
  8. Hash für Duplikatserkennung berechnen
"""

import hashlib
import logging
import re
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DatenReiniger:

    def __init__(self, config: dict):
        """
        Args:
            config: etl.transformations aus etl_config.yaml
        """
        self.datum_formate    = config.get("date_formats", ["%d.%m.%Y", "%Y-%m-%d"])
        self.dezimal_trenner  = config.get("decimal_separator", ",")
        self.pflichtfelder    = config.get("required_columns", ["order_date", "customer", "product", "amount"])

    def bereinigen(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Führt die vollständige Bereinigungspipeline aus.

        Returns:
            Bereinigter DataFrame mit korrekten Datentypen
        """
        logger.info("🧹 Starte Datenbereinigung: %d Zeilen", len(df))
        original_count = len(df)

        df = df.copy()
        df = self._normalisiere_spalten(df)
        df = self._bereinige_datum(df)
        df = self._bereinige_betrag(df)
        df = self._bereinige_menge(df)
        df = self._bereinige_text(df, ["customer", "product"])
        df = self._entferne_ungueltige_zeilen(df)
        df = self._entferne_duplikate(df)
        df = self._berechne_hash(df)

        entfernt = original_count - len(df)
        logger.info(
            "✅ Bereinigung fertig: %d Zeilen behalten, %d entfernt",
            len(df), entfernt
        )
        return df.reset_index(drop=True)

    # ── SCHRITTE ─────────────────────────────────────────────────────────────

    def _normalisiere_spalten(self, df: pd.DataFrame) -> pd.DataFrame:
        """Einheitliche Spaltennamen: lowercase, keine Leerzeichen."""
        df.columns = (
            df.columns.str.strip()
                       .str.lower()
                       .str.replace(r"[\s\-]+", "_", regex=True)
        )
        return df

    def _bereinige_datum(self, df: pd.DataFrame) -> pd.DataFrame:
        """Konvertiert Datumsstrings in pd.Timestamp."""
        if "order_date" not in df.columns:
            return df

        original = df["order_date"].copy()
        df["order_date"] = pd.NaT

        for fmt in self.datum_formate:
            maske = df["order_date"].isna() & original.notna()
            if not maske.any():
                break
            df.loc[maske, "order_date"] = pd.to_datetime(
                original[maske], format=fmt, errors="coerce"
            )

        # Letzter Versuch: automatische Erkennung
        noch_leer = df["order_date"].isna() & original.notna()
        if noch_leer.any():
            df.loc[noch_leer, "order_date"] = pd.to_datetime(
                original[noch_leer], infer_datetime_format=True, errors="coerce"
            )

        invalid = df["order_date"].isna() & original.notna()
        if invalid.any():
            logger.warning(
                "   ⚠️ %d Zeilen: Datum konnte nicht konvertiert werden", invalid.sum()
            )

        return df

    def _bereinige_betrag(self, df: pd.DataFrame) -> pd.DataFrame:
        """Konvertiert Beträge in float (deutsches Format: 1.234,56 → 1234.56)."""
        if "amount" not in df.columns:
            return df

        def konvertiere(wert):
            if pd.isna(wert):
                return np.nan
            s = str(wert).strip()
            # Währungssymbole und Leerzeichen entfernen
            s = re.sub(r"[€$£\s]", "", s)
            if self.dezimal_trenner == ",":
                # 1.234,56 → 1234.56
                if "," in s and "." in s:
                    s = s.replace(".", "").replace(",", ".")
                elif "," in s:
                    s = s.replace(",", ".")
            try:
                wert_float = float(s)
                return wert_float if wert_float >= 0 else np.nan
            except ValueError:
                return np.nan

        original = df["amount"].copy()
        df["amount"] = df["amount"].apply(konvertiere)

        invalid = df["amount"].isna() & original.notna()
        if invalid.any():
            logger.warning("   ⚠️ %d ungültige Beträge", invalid.sum())

        return df

    def _bereinige_menge(self, df: pd.DataFrame) -> pd.DataFrame:
        """Konvertiert quantity zu positiver ganzer Zahl."""
        if "quantity" not in df.columns:
            df["quantity"] = 1
            return df

        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df["quantity"] = df["quantity"].fillna(1).clip(lower=1).astype(int)
        return df

    def _bereinige_text(self, df: pd.DataFrame, spalten: List[str]) -> pd.DataFrame:
        """Bereinigt Textfelder: strip, keine Mehrfach-Leerzeichen, None für leere."""
        for sp in spalten:
            if sp not in df.columns:
                continue
            df[sp] = (
                df[sp].astype(str)
                      .str.strip()
                      .str.replace(r"\s+", " ", regex=True)
            )
            df[sp] = df[sp].replace(["nan", "None", "NULL", "none", ""], np.nan)
        return df

    def _entferne_ungueltige_zeilen(self, df: pd.DataFrame) -> pd.DataFrame:
        """Entfernt Zeilen mit fehlenden Pflichtfeldern."""
        vorher = len(df)
        felder = [f for f in self.pflichtfelder if f in df.columns]
        df = df.dropna(subset=felder)
        entfernt = vorher - len(df)
        if entfernt:
            logger.info("   🗑️ %d Zeilen ohne Pflichtfelder entfernt", entfernt)
        return df

    def _entferne_duplikate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Entfernt doppelte Einträge (gleiche Datum + Kunde + Produkt + Betrag)."""
        vorher = len(df)
        dedup_spalten = [
            s for s in ["order_date", "customer", "product", "amount"]
            if s in df.columns
        ]
        df = df.drop_duplicates(subset=dedup_spalten, keep="last")
        entfernt = vorher - len(df)
        if entfernt:
            logger.info("   🗑️ %d Duplikate entfernt", entfernt)
        return df

    def _berechne_hash(self, df: pd.DataFrame) -> pd.DataFrame:
        """Berechnet MD5-Hash pro Zeile für spätere Duplikatserkennung in der DB."""
        felder = [f for f in ["order_date", "customer", "product", "amount"] if f in df.columns]

        def hash_zeile(row):
            inhalt = "|".join(str(row[f]) for f in felder)
            return hashlib.md5(inhalt.encode()).hexdigest()

        df["data_hash"] = df.apply(hash_zeile, axis=1)
        return df
