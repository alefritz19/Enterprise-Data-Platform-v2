#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KONFIGURATIONS-MODUL
====================
Lädt YAML-Dateien und ersetzt ${ENV_VAR}-Platzhalter aus .env.
"""

import os
import re
import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Lädt und verwaltet alle Konfigurationsdateien."""

    def __init__(self, config_pfad: str = "config"):
        self.pfad = Path(config_pfad)
        self.database: dict = {}
        self.etl: dict = {}
        self._lade_alle()

    def _ersetze_env_vars(self, text: str) -> str:
        """Ersetzt ${VAR} durch Umgebungsvariablen."""
        def ersetzen(m):
            var = m.group(1)
            wert = os.getenv(var, "")
            if not wert:
                logger.warning("⚠️ Umgebungsvariable nicht gesetzt: %s", var)
            return wert
        return re.sub(r"\$\{(\w+)\}", ersetzen, text)

    def _lade_yaml(self, dateiname: str) -> dict:
        pfad = self.pfad / dateiname
        if not pfad.exists():
            logger.warning("⚠️ Konfigurationsdatei nicht gefunden: %s", pfad)
            return {}
        with open(pfad, "r", encoding="utf-8") as f:
            inhalt = self._ersetze_env_vars(f.read())
        return yaml.safe_load(inhalt) or {}

    def _lade_alle(self):
        self.database = self._lade_yaml("database.yaml")
        self.etl      = self._lade_yaml("etl_config.yaml")
        logger.debug("✅ Konfiguration geladen aus: %s", self.pfad)
