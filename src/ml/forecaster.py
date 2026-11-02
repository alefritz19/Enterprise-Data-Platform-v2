#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROGNOSE-MODUL
==============
Erstellt 30-Tage-Umsatzprognosen mit XGBoost (und optional Prophet).
Validiert die Modellgüte über einen chronologischen 80/20 Train/Test-Split (Out-of-Time Holdout)
und berechnet MAE (EUR), RMSE (EUR) sowie MAPE (%).
"""

import json
import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


class PrognoseErsteller:

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.tage            = cfg.get("forecast_days", 30)
        self.min_zeilen      = cfg.get("min_rows_for_forecast", 30)
        self.bestes_modell   = None
        self.letzter_mae     = None
        self.letzter_mape    = None

    def erstelle_prognose(
        self,
        df: pd.DataFrame,
        ziel_spalte: str = "amount",
        tage: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Erstellt eine 30-Tage-Prognose inkl. chronologischer 80/20-Validierung.
        """
        if tage is None:
            tage = self.tage

        taeglich = self._aggregiere_taeglich(df, ziel_spalte)

        if taeglich is None or len(taeglich) < self.min_zeilen:
            logger.warning(
                "⚠️ Zu wenige Daten für Prognose (%d < %d)",
                len(taeglich) if taeglich is not None else 0,
                self.min_zeilen
            )
            return None

        logger.info("🤖 Prognose mit %d historischen Tagen, Horizont: %d Tage", len(taeglich), tage)

        ergebnisse = {}

        # ── XGBoost (Chronologischer 80/20 Train/Test-Split) ─────────────────
        try:
            werte_x, mae_x, mape_x, rmse_x, n_train, n_test = self._xgboost(taeglich, tage)
            ergebnisse["XGBoost"] = (werte_x, mae_x, mape_x, rmse_x, n_train, n_test)
            logger.info(
                "   XGBoost (80/20 Split: %d Train / %d Test Tage) -> MAE: %.2f € | MAPE: %.2f %%",
                n_train, n_test, mae_x, mape_x
            )
        except Exception as e:
            logger.warning("   XGBoost fehlgeschlagen: %s", e)

        if not ergebnisse:
            logger.error("❌ Kein ML-Modell verfügbar")
            return None

        bestes = min(ergebnisse, key=lambda k: ergebnisse[k][1])
        werte, mae, mape, rmse, n_train, n_test = ergebnisse[bestes]

        self.bestes_modell = bestes
        self.letzter_mae   = mae
        self.letzter_mape  = mape

        # Modellgüte-Metriken für Dashboard persistieren
        try:
            metrics_path = Path("data/processed/model_metrics.json")
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            metrics_data = {
                "modell": bestes,
                "gesamt_tage": len(taeglich),
                "train_tage": n_train,
                "test_tage": n_test,
                "split_strategie": "Chronologischer Out-of-Time Split (80 % Train / 20 % Test)",
                "mae_eur": round(mae, 2),
                "rmse_eur": round(rmse, 2),
                "mape_pct": round(mape, 2),
                "aktualisiert_am": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            metrics_path.write_text(json.dumps(metrics_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("Konnte model_metrics.json nicht speichern: %s", e)

        # Prognose-Liste aufbauen
        heute = datetime.now()
        prognose_liste = [
            {
                "datum":    (heute + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
                "prognose": round(max(0.0, float(v)), 2),
                "tag":      i + 1,
            }
            for i, v in enumerate(werte)
        ]

        summe = sum(p["prognose"] for p in prognose_liste)
        logger.info(
            "✅ Modell: %s | 30-Tage-Summe: %.0f € | Test-MAE: %.2f € | Test-MAPE: %.2f %%",
            bestes, summe, mae, mape
        )

        return {
            "modell":       bestes,
            "summe":        summe,
            "durchschnitt": summe / tage,
            "fehler":       mae,
            "mape":         mape,
            "rmse":         rmse,
            "train_tage":   n_train,
            "test_tage":    n_test,
            "daten":        prognose_liste,
        }

    def _aggregiere_taeglich(
        self, df: pd.DataFrame, spalte: str
    ) -> Optional[pd.DataFrame]:
        """Aggregiert DataFrame auf tägliche Summen."""
        try:
            df = df.copy()
            df["datum"] = pd.to_datetime(df["order_date"], errors="coerce").dt.normalize()
            taeglich = (
                df.groupby("datum")[spalte]
                  .sum()
                  .reset_index()
                  .sort_values("datum")
                  .rename(columns={spalte: "umsatz"})
            )
            return taeglich
        except Exception as e:
            logger.error("❌ Tages-Aggregation fehlgeschlagen: %s", e)
            return None

    @staticmethod
    def _baue_zeit_features(dts: pd.Series, start_datum: pd.Timestamp) -> pd.DataFrame:
        """Erzeugt deterministische Kalender- und Monatszyklus-Features für B2B-Zeitreihen."""
        df_feat = pd.DataFrame(index=dts.index)
        df_feat["wochentag"]       = dts.dt.dayofweek
        df_feat["ist_wochenende"]  = (dts.dt.dayofweek >= 5).astype(int)
        df_feat["tag"]             = dts.dt.day
        df_feat["ist_monatsende"]  = (dts.dt.day >= 24).astype(int)
        df_feat["ist_monatsstart"] = (dts.dt.day <= 5).astype(int)
        return df_feat

    def _xgboost(self, df: pd.DataFrame, tage: int):
        """
        XGBoost mit chronologischem 80/20 Train/Test-Split zur ehrlichen Evaluierung
        von MAE, RMSE und MAPE auf ungesehenen zukünftigen Zeitpunkten.
        """
        from xgboost import XGBRegressor

        d = df.sort_values("datum").reset_index(drop=True).copy()
        dts = pd.to_datetime(d["datum"])
        start_datum = dts.min()

        X = self._baue_zeit_features(dts, start_datum)
        y = d["umsatz"].values

        # Chronologischer 80/20 Train/Test-Split (Out-of-Time Validierung)
        split_idx = max(int(len(d) * 0.8), len(d) - max(7, int(len(d) * 0.2)))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        params = dict(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            random_state=42,
            verbosity=0,
        )

        # 1. Evaluierung auf dem chronologischen Holdout-Testset (20 %)
        eval_model = XGBRegressor(**params)
        eval_model.fit(X_train, y_train)
        y_pred_test = eval_model.predict(X_test)

        mae = float(np.mean(np.abs(y_test - y_pred_test)))
        rmse = float(np.sqrt(np.mean((y_test - y_pred_test) ** 2)))
        non_zero = np.maximum(np.abs(y_test), 1.0)
        mape = float(np.mean(np.abs((y_test - y_pred_test) / non_zero)) * 100.0)

        # 2. Finales Modell auf 100 % der Historie für die 30-Tage-Zukunftsprognose
        final_model = XGBRegressor(**params)
        final_model.fit(X, y)

        letztes = dts.max()
        future_dates = pd.Series([letztes + timedelta(days=i) for i in range(1, tage + 1)])
        X_future = self._baue_zeit_features(future_dates, start_datum)
        werte = final_model.predict(X_future)

        return werte, mae, mape, rmse, len(X_train), len(X_test)
