#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LOGGING-MODUL
=============
Zentrales Logging für die gesamte Data Platform.
Schreibt gleichzeitig in Konsole und in Datei.
Log-Rotation: max. 10 MB pro Datei, 5 Backup-Dateien.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LoggerSetup:

    @staticmethod
    def initialisiere(
        log_level: str = "INFO",
        log_datei: str = "logs/data_platform.log",
    ):
        """
        Initialisiert das zentrale Logging-System.

        Args:
            log_level: DEBUG | INFO | WARNING | ERROR
            log_datei: Pfad zur Log-Datei
        """
        # Log-Verzeichnis erstellen
        Path(log_datei).parent.mkdir(parents=True, exist_ok=True)

        level = getattr(logging, log_level.upper(), logging.INFO)

        # Format
        fmt_datei    = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
        fmt_konsole  = "%(asctime)s | %(levelname)-8s | %(message)s"
        datefmt      = "%Y-%m-%d %H:%M:%S"

        root = logging.getLogger()
        root.setLevel(level)

        # Alte Handler entfernen (wichtig bei Jupyter re-run)
        root.handlers.clear()

        # ── Konsole ──────────────────────────────────────────────────────────
        konsole = logging.StreamHandler(sys.stdout)
        konsole.setLevel(level)
        konsole.setFormatter(logging.Formatter(fmt_konsole, datefmt))
        root.addHandler(konsole)

        # ── Datei (mit Rotation) ─────────────────────────────────────────────
        try:
            datei_handler = RotatingFileHandler(
                log_datei,
                maxBytes=10 * 1024 * 1024,   # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            datei_handler.setLevel(level)
            datei_handler.setFormatter(logging.Formatter(fmt_datei, datefmt))
            root.addHandler(datei_handler)
        except PermissionError:
            logging.warning("⚠️ Log-Datei konnte nicht geöffnet werden: %s", log_datei)

        # Externe Bibliotheken ruhigstellen
        for name in ("urllib3", "requests", "prophet", "cmdstanpy", "matplotlib"):
            logging.getLogger(name).setLevel(logging.WARNING)

        logging.info("✅ Logging initialisiert → %s (Level: %s)", log_datei, log_level)
