#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUPT-ORCHESTRATOR – DATA PLATFORM v2.0
========================================
Steuert den gesamten ETL-Prozess von A bis Z.

BENACHRICHTIGUNGEN:
    📱 Telegram → NUR du (Admin) – technische Details, Fehler, Status
    📧 E-Mail   → NUR Kunden (täglich 08:00) – schöner Tagesbericht

VERWENDUNG in PyCharm:
    Rechtsklick auf orchestrator.py → Run 'orchestrator'

VERWENDUNG in Jupyter:
    from orchestrator import Orchestrator
    o = Orchestrator()
    o.start()
    ergebnis = o.etl()
    print(ergebnis)

DAUERBETRIEB (jede Stunde ETL + täglich 08:00 Bericht):
    o.starte_zeitgesteuert()
"""

import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import schedule
from dotenv import load_dotenv

load_dotenv()

from src.utils.logger import LoggerSetup
from src.utils.config import Config
from src.database.postgres_connector import PostgreSQLConnector
from src.extract.csv_extractor import CSVExtractor
from src.transform.data_cleaner import DatenReiniger
from src.load.postgres_loader import PostgreSQLLoader
from src.ml.forecaster import PrognoseErsteller
from src.ml.anomaly_detector import AnomalieDetektor
from src.alerts.telegram_admin import TelegramAdmin   # ← nur Admin
from src.alerts.email_kunde import EmailKunde          # ← nur Kunden

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Zentrale Steuerklasse der Data Platform.

    Kanaltrennung:
        self.telegram → Admin (immer, alle technischen Infos)
        self.email    → Kunden (täglich, konfigurierbar)
    """

    VERSION = "2.0"

    def __init__(self, config_pfad: str = "config"):
        # Konfiguration laden
        self.cfg = Config(config_pfad)

        # Komponenten (werden in start() initialisiert)
        self.db:        Optional[PostgreSQLConnector] = None
        self.extractor: Optional[CSVExtractor]        = None
        self.reiniger:  Optional[DatenReiniger]        = None
        self.loader:    Optional[PostgreSQLLoader]     = None
        self.prognose:  Optional[PrognoseErsteller]   = None
        self.detektor:  Optional[AnomalieDetektor]    = None

        # Benachrichtigungen (getrennte Kanäle!)
        self.telegram = TelegramAdmin()   # Admin
        self.email    = EmailKunde()      # Kunden

        # Laufzeit-Statistiken
        self.stats = {
            "etl_durchlaeufe":    0,
            "verarbeitete_zeilen": 0,
            "fehler":             0,
            "prognosen":          0,
        }

        self._laeuft = False
        logger.info("✅ Orchestrator v%s bereit", self.VERSION)

    def start(self) -> bool:
        """
        Initialisiert alle Komponenten und verbindet zur Datenbank.
        Muss vor etl() aufgerufen werden.

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        logger.info("🔧 Initialisiere Komponenten...")
        try:
            # Datenbank
            self.db = PostgreSQLConnector(self.cfg.database)
            self.db.verbinden()

            # ETL-Komponenten
            self.extractor = CSVExtractor(self.cfg.etl.get("source", {}))
            self.reiniger  = DatenReiniger(self.cfg.etl.get("transformations", {}))
            self.loader    = PostgreSQLLoader(self.db, self.cfg.etl.get("target", {}))

            # ML
            ml_cfg = self.cfg.etl.get("ml", {})
            self.prognose = PrognoseErsteller(ml_cfg)
            self.detektor = AnomalieDetektor(ml_cfg)

            logger.info("✅ Alle Komponenten bereit")
            self.telegram.start(self.VERSION)
            return True

        except Exception as e:
            logger.error("❌ Initialisierung fehlgeschlagen: %s", e)
            self.telegram.db_fehler(str(e))
            return False

    def etl(self) -> dict:
        """
        Führt einen vollständigen ETL-Lauf durch:
          Extract → Transform → Load → ML → Alert

        Returns:
            Ergebnis-Dict mit status, batch_id, zeilen, dauer, anomalien
        """
        start_zeit = datetime.now()
        batch_id   = str(uuid.uuid4())
        logger.info("=" * 55)
        logger.info("🔄 ETL START  Batch: %s", batch_id[:8])
        logger.info("=" * 55)

        try:
            # ── 1. EXTRACT ────────────────────────────────────────────────────
            dateien = self.extractor.finde_dateien()
            if not dateien:
                logger.info("ℹ️ Keine neuen CSV-Dateien – ETL beendet")
                return {"status": "keine_daten", "batch_id": batch_id}

            roh_teile  = []
            ok_dateien = 0

            for datei in dateien:
                try:
                    df = self.extractor.lese_csv(datei)
                    df["dateiname"] = datei.name
                    roh_teile.append(df)
                    self.extractor.archiviere_datei(datei)
                    ok_dateien += 1
                except Exception as e:
                    logger.error("❌ Datei-Fehler [%s]: %s", datei.name, e)
                    self.extractor.verschiebe_nach_error(datei, str(e))
                    self.stats["fehler"] += 1

            if not roh_teile:
                self.telegram.etl_fehler("Keine Datei konnte gelesen werden", batch_id)
                return {"status": "fehler", "batch_id": batch_id}

            roh_df = pd.concat(roh_teile, ignore_index=True)
            logger.info("📥 Rohdaten: %d Zeilen aus %d Datei(en)", len(roh_df), ok_dateien)

            # ── 2. TRANSFORM ──────────────────────────────────────────────────
            clean_df = self.reiniger.bereinigen(roh_df)
            logger.info(
                "🧹 Bereinigt: %d → %d Zeilen",
                len(roh_df), len(clean_df)
            )

            if clean_df.empty:
                self.telegram.etl_fehler("Nach Bereinigung keine Zeilen übrig", batch_id)
                return {"status": "fehler", "batch_id": batch_id}

            # ── 3. LOAD ───────────────────────────────────────────────────────
            lade_stats = self.loader.lade_komplett(roh_df, clean_df, batch_id)
            logger.info(
                "💾 Geladen → roh: %d | clean: %d | mart: aktualisiert",
                lade_stats.get("roh", 0), lade_stats.get("clean", 0)
            )

            # ── 4. ML: PROGNOSE ───────────────────────────────────────────────
            prognose = None
            if len(clean_df) >= self.prognose.min_zeilen:
                prognose = self.prognose.erstelle_prognose(clean_df)
                if prognose:
                    self._speichere_prognose(prognose, batch_id)
                    self.stats["prognosen"] += 1

            # ── 5. ML: ANOMALIEN ──────────────────────────────────────────────
            anomalien      = self.detektor.finde_anomalien(clean_df)
            anomalien_count = len(anomalien)

            # Kritische Anomalien → sofort Admin-Alarm
            for a in [x for x in anomalien if x.get("kritisch")]:
                self.telegram.anomalie_kritisch(a)

            # ── 6. POWER BI ───────────────────────────────────────────────────
            pbi_ok = self._power_bi_aktualisieren(clean_df, batch_id)
            self.telegram.power_bi(pbi_ok)

            # ── 7. BENACHRICHTIGUNGEN ─────────────────────────────────────────
            dauer = (datetime.now() - start_zeit).total_seconds()

            # Admin: Telegram (immer)
            self.telegram.etl_ok({
                "batch_id":     batch_id,
                "clean":        len(clean_df),
                "dateien":      ok_dateien,
                "dauer":        dauer,
                "anomalien":    anomalien_count,
                "prognose_summe": prognose.get("summe") if prognose else None,
            })

            # Kunden: E-Mail (täglich 08:00, nicht nach jedem ETL)
            # → wird von starte_zeitgesteuert() separat geplant

            # ── 8. ETL-LOG ────────────────────────────────────────────────────
            self.loader.protokolliere_etl(
                batch_id=batch_id,
                status="erfolg",
                stats={
                    "dateien":  ok_dateien,
                    "roh":      len(roh_df),
                    "clean":    len(clean_df),
                    "anomalien": anomalien_count,
                    "dauer":    dauer,
                },
                gestartet_am=start_zeit,
            )

            # Statistiken aktualisieren
            self.stats["etl_durchlaeufe"]     += 1
            self.stats["verarbeitete_zeilen"] += len(clean_df)

            logger.info("✅ ETL FERTIG  Dauer: %.1fs", dauer)

            return {
                "status":    "erfolg",
                "batch_id":  batch_id,
                "dauer":     round(dauer, 1),
                "dateien":   ok_dateien,
                "zeilen":    len(clean_df),
                "anomalien": anomalien_count,
                "prognose":  prognose,
            }

        except Exception as e:
            logger.error("❌ KRITISCHER ETL-FEHLER: %s", e, exc_info=True)
            self.stats["fehler"] += 1
            self.telegram.etl_fehler(str(e), batch_id)
            self.loader.protokolliere_etl(
                batch_id=batch_id,
                status="fehler",
                stats={},
                fehler=str(e),
                gestartet_am=start_zeit,
            )
            return {"status": "fehler", "batch_id": batch_id, "fehler": str(e)}

    def sende_tagesbericht(self):
        """
        Erstellt und sendet den täglichen Bericht.
        Admin → Telegram, Kunde → E-Mail.
        Wird täglich um 08:00 von starte_zeitgesteuert() aufgerufen.
        """
        logger.info("📊 Erstelle Tagesbericht...")

        try:
            umsatz    = self._lade_tagesstatistiken()
            prognose  = self._lade_letzte_prognose()
            anomalien = self._lade_heutige_anomalien()

            # Admin bekommt technischen Bericht per Telegram
            self.telegram.tagesbericht_admin(self.stats, umsatz)

            # Kunde bekommt schönen HTML-Bericht per E-Mail
            self.email.tagesbericht(umsatz, anomalien, prognose)

        except Exception as e:
            logger.error("❌ Tagesbericht-Fehler: %s", e)
            self.telegram.etl_fehler(f"Tagesbericht: {e}")

    def starte_zeitgesteuert(self):
        """
        Startet die Plattform im Dauerbetrieb:
        - ETL jede Stunde
        - Tagesbericht täglich um 08:00
        """
        intervall = self.cfg.etl.get("schedule", {}).get("etl_interval_minutes", 60)
        uhrzeit   = self.cfg.etl.get("schedule", {}).get("daily_report_time", "08:00")

        logger.info("⏰ Zeitgesteuert: ETL alle %d Min | Bericht um %s", intervall, uhrzeit)

        # Sofort einmal starten
        self.etl()

        schedule.every(intervall).minutes.do(self.etl)
        schedule.every().day.at(uhrzeit).do(self.sende_tagesbericht)

        self._laeuft = True
        logger.info("🟢 Platform läuft. Stoppen: Strg+C")

        try:
            while self._laeuft:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Stopp durch Benutzer")
            self.stop()

    def stop(self):
        """Stoppt die Plattform sauber."""
        self._laeuft = False
        if self.db:
            self.db.trennen()
        logger.info("✅ Platform gestoppt | Statistiken: %s", self.stats)

    # ── HILFSMETHODEN ─────────────────────────────────────────────────────────

    def _speichere_prognose(self, prognose: dict, batch_id: str):
        """Speichert ML-Prognose in mart.sales_prognose."""
        try:
            df = pd.DataFrame(prognose["daten"])
            df["batch_id"]   = batch_id
            df["erstellt_am"] = datetime.now()
            self.db.lade_df(df, schema="mart", tabelle="sales_prognose", if_exists="replace")
            logger.info("   ✅ Prognose gespeichert (%d Einträge)", len(df))
        except Exception as e:
            logger.warning("⚠️ Prognose speichern fehlgeschlagen: %s", e)

    def _power_bi_aktualisieren(self, df: pd.DataFrame, batch_id: str) -> bool:
        """
        Versucht Power BI über REST-API zu aktualisieren.
        Fallback: CSV-Export.
        """
        tenant = os.getenv("POWER_BI_TENANT_ID")
        client = os.getenv("POWER_BI_CLIENT_ID")
        secret = os.getenv("POWER_BI_CLIENT_SECRET")
        dataset = os.getenv("POWER_BI_DATASET_ID")
        group   = os.getenv("POWER_BI_GROUP_ID")

        # ── Power BI REST API ─────────────────────────────────────────────────
        if all([tenant, client, secret, dataset, group]):
            try:
                import msal
                import requests as req

                app = msal.ConfidentialClientApplication(
                    client_id=client,
                    client_credential=secret,
                    authority=f"https://login.microsoftonline.com/{tenant}",
                )
                token = app.acquire_token_for_client(
                    scopes=["https://analysis.windows.net/powerbi/api/.default"]
                )
                if "access_token" not in token:
                    raise RuntimeError("Kein Power BI Token")

                url = (
                    f"https://api.powerbi.com/v1.0/myorg/groups/{group}"
                    f"/datasets/{dataset}/refreshes"
                )
                r = req.post(
                    url,
                    headers={"Authorization": f"Bearer {token['access_token']}"},
                    timeout=30,
                )
                if r.status_code == 202:
                    logger.info("   ✅ Power BI API-Aktualisierung gestartet")
                    return True
                else:
                    logger.error("   ❌ Power BI HTTP %s", r.status_code)
                    return False

            except Exception as e:
                logger.error("   ❌ Power BI API Fehler: %s", e)
                return False

        # ── Fallback: CSV-Export ──────────────────────────────────────────────
        try:
            export_dir = Path("power_bi_export")
            export_dir.mkdir(exist_ok=True)
            datei = export_dir / f"daten_{datetime.now():%Y%m%d_%H%M}.csv"
            df.to_csv(datei, index=False, encoding="utf-8")
            logger.info("   📄 CSV-Export: %s", datei.name)
            return True
        except Exception as e:
            logger.error("   ❌ CSV-Export Fehler: %s", e)
            return False

    def _lade_tagesstatistiken(self) -> dict:
        """Lädt Tagesstatistiken aus der Datenbank."""
        try:
            result = self.db.execute(
                """
                SELECT
                    SUM(CASE WHEN order_date::date = CURRENT_DATE
                        THEN amount ELSE 0 END)                         AS heute,
                    SUM(CASE WHEN order_date::date = CURRENT_DATE - 1
                        THEN amount ELSE 0 END)                         AS gestern,
                    COUNT(CASE WHEN order_date::date = CURRENT_DATE
                        THEN 1 END)                                      AS bestellungen,
                    AVG(CASE WHEN order_date::date = CURRENT_DATE
                        THEN amount END)                                 AS durchschnitt,
                    COUNT(DISTINCT CASE WHEN order_date::date = CURRENT_DATE
                        THEN customer END)                               AS aktive_kunden,
                    SUM(CASE WHEN DATE_TRUNC('month', order_date) =
                        DATE_TRUNC('month', CURRENT_DATE)
                        THEN amount ELSE 0 END)                         AS monat_gesamt
                FROM staging.sales_clean
                WHERE order_date >= CURRENT_DATE - INTERVAL '1 month'
                """
            )
            if not result:
                return {}

            row = result[0]
            heute   = float(row.get("heute") or 0)
            gestern = float(row.get("gestern") or 0)
            return {
                "heute":         heute,
                "gestern":       gestern,
                "veraenderung":  ((heute - gestern) / gestern * 100) if gestern else 0,
                "bestellungen":  int(row.get("bestellungen") or 0),
                "durchschnitt":  float(row.get("durchschnitt") or 0),
                "aktive_kunden": int(row.get("aktive_kunden") or 0),
                "neukunden":     0,
                "monat_gesamt":  float(row.get("monat_gesamt") or 0),
            }
        except Exception as e:
            logger.error("❌ Tagesstatistiken: %s", e)
            return {}

    def _lade_letzte_prognose(self) -> Optional[dict]:
        """Lädt die aktuellste ML-Prognose aus der Datenbank."""
        try:
            result = self.db.execute(
                """
                SELECT SUM(prognose) AS summe, AVG(prognose) AS durchschnitt
                FROM mart.sales_prognose
                WHERE erstellt_am >= NOW() - INTERVAL '25 hours'
                """
            )
            if result and result[0]["summe"]:
                return {
                    "summe":       float(result[0]["summe"]),
                    "durchschnitt": float(result[0]["durchschnitt"]),
                    "modell":      "Prophet/XGBoost",
                    "fehler":      5.0,
                }
        except Exception:
            pass
        return None

    def _lade_heutige_anomalien(self) -> list:
        """
        Führt Anomalieerkennung auf heutigen Daten durch.
        Gibt leere Liste zurück wenn keine Daten vorhanden.
        """
        try:
            df = self.db.query_df(
                """
                SELECT order_date, amount
                FROM staging.sales_clean
                WHERE order_date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY order_date
                """
            )
            if not df.empty:
                return self.detektor.finde_anomalien(df)
        except Exception as e:
            logger.warning("⚠️ Anomalie-Laden: %s", e)
        return []


# ── EINSTIEGSPUNKT ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Logging initialisieren
    LoggerSetup.initialisiere(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_datei=os.getenv("LOG_FILE", "logs/data_platform.log"),
    )

    logger.info("═" * 55)
    logger.info("  DATA PLATFORM v%s", Orchestrator.VERSION)
    logger.info("  %s", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    logger.info("  📱 Telegram → Admin | 📧 E-Mail → Kunden")
    logger.info("═" * 55)

    o = Orchestrator("config")

    if not o.start():
        logger.error("❌ Start fehlgeschlagen – bitte .env prüfen")
        sys.exit(1)

    # ── Einmaliger Lauf (Test / Jupyter) ─────────────────────────────────────
    ergebnis = o.etl()
    logger.info("📋 Ergebnis: %s", ergebnis)

    # ── Dauerbetrieb (Kommentar entfernen für Produktion) ────────────────────
    # o.starte_zeitgesteuert()
