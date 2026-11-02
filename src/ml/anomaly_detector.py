#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANOMALIE-DETEKTOR
=================
Erkennt ungewöhnliche Abweichungen in Umsatzdaten.
Methode: IQR (Interquartile Range) + Z-Score kombiniert.
Markiert Anomalien als "kritisch" wenn Abweichung > 50%.
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AnomalieDetektor:

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.schwellenwert = cfg.get("anomaly_threshold", 0.20)   # 20%
        self.kritisch_ab   = 0.50                                   # 50% → kritisch

    def finde_anomalien(self, df: pd.DataFrame) -> List[dict]:
        """
        Findet Anomalien im DataFrame.

        Returns:
            Liste von Anomalie-Dicts:
            {
              'datum': str,
              'wert': float,
              'erwartet': float,
              'abweichung': float (%),
              'grund': str,
              'kritisch': bool
            }
        """
        taeglich = self._aggregiere_taeglich(df)
        if taeglich is None or len(taeglich) < 7:
            logger.debug("Zu wenige Daten für Anomalieerkennung")
            return []

        anomalien = self._iqr_methode(taeglich)
        logger.info(
            "🔍 Anomalieerkennung: %d von %d Tagen auffällig",
            len(anomalien), len(taeglich)
        )
        return anomalien

    def _aggregiere_taeglich(
        self, df: pd.DataFrame
    ) -> Optional[pd.DataFrame]:
        """Aggregiert auf tägliche Umsätze."""
        try:
            d = df.copy()
            d["datum"] = pd.to_datetime(d["order_date"], errors="coerce").dt.normalize()
            return (
                d.groupby("datum")["amount"]
                 .sum()
                 .reset_index()
                 .rename(columns={"amount": "umsatz"})
                 .sort_values("datum")
            )
        except Exception as e:
            logger.error("❌ Aggregation fehlgeschlagen: %s", e)
            return None

    def _iqr_methode(self, df: pd.DataFrame) -> List[dict]:
        """
        IQR-basierte Anomalieerkennung.
        Erwartet = rollender 7-Tage-Median.
        """
        df = df.copy()
        df["erwartet"] = (
            df["umsatz"]
              .rolling(window=7, min_periods=3, center=True)
              .median()
              .fillna(df["umsatz"].median())
        )

        # Abweichung berechnen
        df["abweichung"] = np.where(
            df["erwartet"] > 0,
            (df["umsatz"] - df["erwartet"]) / df["erwartet"],
            0.0
        )

        anomalien = []
        for _, row in df.iterrows():
            abw = float(row["abweichung"])
            if abs(abw) < self.schwellenwert:
                continue

            richtung = "hoch" if abw > 0 else "niedrig"
            grund = (
                f"Umsatz {abs(abw)*100:.0f}% zu {richtung} "
                f"(Median letzter 7 Tage: {row['erwartet']:,.0f} €)"
            )

            anomalien.append({
                "datum":      str(row["datum"])[:10],
                "wert":       round(float(row["umsatz"]), 2),
                "erwartet":   round(float(row["erwartet"]), 2),
                "abweichung": round(abw * 100, 1),
                "grund":      grund,
                "kritisch":   abs(abw) >= self.kritisch_ab,
            })

        return anomalien
