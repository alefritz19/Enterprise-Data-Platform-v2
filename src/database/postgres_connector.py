#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POSTGRESQL CONNECTOR
====================
Verbindung zur Datenbank mit automatischem Retry bei Fehlern.
Unterstützt sowohl pandas-Abfragen (engine) als auch
direkte SQL-Ausführung (connection).
"""

import logging
import time
import pandas as pd
import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


class PostgreSQLConnector:

    def __init__(self, config: dict):
        """
        Args:
            config: Dictionary aus database.yaml
                host, port, database, user, password,
                pool_size, pool_pre_ping, connect_timeout
        """
        self.config = config
        self.engine = None
        self._verbunden = False

    def verbinden(self, versuche: int = 3):
        """Stellt Verbindung her, bis zu `versuche` Mal."""
        host = self.config.get("host", "localhost")
        port = self.config.get("port", 5432)
        db   = self.config.get("database", "data_platform")
        user = self.config.get("user", "postgres")
        pw   = self.config.get("password", "")

        url = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"

        for versuch in range(1, versuche + 1):
            try:
                self.engine = create_engine(
                    url,
                    pool_size=self.config.get("pool_size", 5),
                    pool_pre_ping=self.config.get("pool_pre_ping", True),
                    pool_recycle=self.config.get("pool_recycle", 3600),
                    connect_args={
                        "connect_timeout": self.config.get("connect_timeout", 10)
                    },
                )
                # Verbindung sofort testen
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                self._verbunden = True
                logger.info("✅ PostgreSQL verbunden: %s:%s/%s", host, port, db)
                return

            except OperationalError as e:
                logger.warning(
                    "⚠️ Verbindungsversuch %d/%d fehlgeschlagen: %s",
                    versuch, versuche, e
                )
                if versuch < versuche:
                    time.sleep(2 ** versuch)   # 2s, 4s, 8s
                else:
                    raise

    def trennen(self):
        if self.engine:
            self.engine.dispose()
            self._verbunden = False
            logger.info("🔌 Datenbankverbindung getrennt")

    @property
    def ist_verbunden(self) -> bool:
        return self._verbunden

    def execute(self, sql: str, params: dict = None) -> list:
        """
        Führt SQL aus und gibt Liste von Row-Dicts zurück.
        Für INSERT/UPDATE/DELETE automatisch commit.
        """
        if not self._verbunden:
            raise RuntimeError("Keine Datenbankverbindung!")
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            try:
                return [dict(row._mapping) for row in result]
            except Exception:
                return []

    def query_df(self, sql: str, params: dict = None) -> pd.DataFrame:
        """Führt SELECT aus und gibt DataFrame zurück."""
        if not self._verbunden:
            raise RuntimeError("Keine Datenbankverbindung!")
        return pd.read_sql(text(sql), self.engine, params=params or {})

    def lade_df(
        self,
        df: pd.DataFrame,
        schema: str,
        tabelle: str,
        if_exists: str = "append",
        index: bool = False,
        chunksize: int = 1000,
    ) -> int:
        """
        Lädt einen DataFrame in PostgreSQL.

        Args:
            df: Daten
            schema: Ziel-Schema
            tabelle: Ziel-Tabelle
            if_exists: 'append' | 'replace' | 'fail'
            chunksize: Zeilen pro Batch

        Returns:
            Anzahl geladener Zeilen
        """
        if df.empty:
            logger.warning("⚠️ Leerer DataFrame – nichts geladen")
            return 0

        df.to_sql(
            name=tabelle,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=index,
            chunksize=chunksize,
            method="multi",
        )
        logger.info("💾 %d Zeilen → %s.%s (%s)", len(df), schema, tabelle, if_exists)
        return len(df)

    def schema_erstellen(self, schema: str):
        """Erstellt Schema falls nicht vorhanden."""
        self.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        logger.debug("Schema sichergestellt: %s", schema)

    def tabelle_existiert(self, schema: str, tabelle: str) -> bool:
        result = self.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :tabelle
            ) AS ex
            """,
            {"schema": schema, "tabelle": tabelle},
        )
        return result[0]["ex"] if result else False
