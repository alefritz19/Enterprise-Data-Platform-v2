#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POSTGRESQL LOADER
=================
Lädt bereinigte Daten in die Datenbank.
Schreibt zuerst Rohdaten (raw), dann bereinigte Daten (staging),
dann aggregiert nach mart.sales_daily.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

import pandas as pd

from src.database.postgres_connector import PostgreSQLConnector

logger = logging.getLogger(__name__)


class PostgreSQLLoader:

    def __init__(self, db: PostgreSQLConnector, config: dict):
        """
        Args:
            db: Aktiver PostgreSQLConnector
            config: etl.target aus etl_config.yaml
        """
        self.db     = db
        self.schema = config.get("schema", "staging")
        self.tabelle = config.get("table", "sales_clean")
        self.strategie = config.get("strategy", "append")

    def lade_komplett(
        self,
        roh_df: pd.DataFrame,
        clean_df: pd.DataFrame,
        batch_id: str,
    ) -> dict:
        """
        Vollständiger Lade-Prozess:
          1. Rohdaten → raw.sales_import
          2. Bereinigte Daten → staging.sales_clean
          3. Aggregation → mart.sales_daily

        Returns:
            {'roh': int, 'clean': int, 'mart': int}
        """
        stats = {"roh": 0, "clean": 0, "mart": 0}

        # ── 1. Rohdaten sichern ───────────────────────────────────────────────
        try:
            roh_export = roh_df.copy()
            roh_export["batch_id"] = batch_id
            roh_export["geladen_am"] = datetime.now()
            stats["roh"] = self.db.lade_df(
                roh_export, schema="raw", tabelle="sales_import", if_exists="append"
            )
        except Exception as e:
            logger.warning("⚠️ Rohdaten-Sicherung fehlgeschlagen: %s", e)

        # ── 2. Bereinigte Daten laden ─────────────────────────────────────────
        try:
            if not clean_df.empty:
                export = self._vorbereiten_fuer_staging(clean_df, batch_id)
                if_exists = "replace" if self.strategie == "replace" else "append"
                stats["clean"] = self.db.lade_df(
                    export, schema=self.schema, tabelle=self.tabelle, if_exists=if_exists
                )
        except Exception as e:
            logger.error("❌ Staging-Laden fehlgeschlagen: %s", e)
            raise

        # ── 3. Mart aggregieren ───────────────────────────────────────────────
        try:
            stats["mart"] = self._aktualisiere_mart()
        except Exception as e:
            logger.warning("⚠️ Mart-Aggregation fehlgeschlagen: %s", e)

        return stats

    def _vorbereiten_fuer_staging(self, df: pd.DataFrame, batch_id: str) -> pd.DataFrame:
        """Fügt Metadaten hinzu und wählt Staging-Spalten."""
        exp = df.copy()
        exp["batch_id"]   = batch_id
        exp["geladen_am"] = datetime.now()

        # Nur Spalten die in der Tabelle existieren
        erlaubt = [
            "order_date", "customer", "product", "amount", "quantity",
            "dateiname", "batch_id", "data_hash", "geladen_am"
        ]
        return exp[[s for s in erlaubt if s in exp.columns]]

    def _aktualisiere_mart(self) -> int:
        """Aggregiert staging → mart.sales_daily."""
        sql = """
        INSERT INTO mart.sales_daily (
            sale_date, total_orders, total_customers, total_revenue, avg_order_value, aktualisiert
        )
        SELECT
            order_date::date                    AS sale_date,
            COUNT(*)                            AS total_orders,
            COUNT(DISTINCT customer)            AS total_customers,
            SUM(amount)                         AS total_revenue,
            AVG(amount)                         AS avg_order_value,
            NOW()                               AS aktualisiert
        FROM staging.sales_clean
        WHERE order_date >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY order_date::date
        ON CONFLICT (sale_date) DO UPDATE SET
            total_orders    = EXCLUDED.total_orders,
            total_customers = EXCLUDED.total_customers,
            total_revenue   = EXCLUDED.total_revenue,
            avg_order_value = EXCLUDED.avg_order_value,
            aktualisiert    = NOW()
        """
        self.db.execute(sql)
        logger.info("   ✅ mart.sales_daily aktualisiert")
        return 1

    def protokolliere_etl(
        self,
        batch_id: str,
        status: str,
        stats: dict,
        fehler: Optional[str] = None,
        gestartet_am: Optional[datetime] = None,
    ):
        """Schreibt ETL-Lauf in metadata.etl_log."""
        try:
            self.db.execute(
                """
                INSERT INTO metadata.etl_log
                    (batch_id, status, dateien, zeilen_roh, zeilen_clean,
                     anomalien, dauer_sek, fehler_text, gestartet_am, beendet_am)
                VALUES
                    (:batch_id, :status, :dateien, :zeilen_roh, :zeilen_clean,
                     :anomalien, :dauer_sek, :fehler_text, :gestartet_am, NOW())
                """,
                {
                    "batch_id":    batch_id,
                    "status":      status,
                    "dateien":     stats.get("dateien", 0),
                    "zeilen_roh":  stats.get("roh", 0),
                    "zeilen_clean": stats.get("clean", 0),
                    "anomalien":   stats.get("anomalien", 0),
                    "dauer_sek":   stats.get("dauer", 0),
                    "fehler_text": fehler,
                    "gestartet_am": gestartet_am or datetime.now(),
                },
            )
        except Exception as e:
            logger.warning("⚠️ ETL-Log fehlgeschlagen: %s", e)
