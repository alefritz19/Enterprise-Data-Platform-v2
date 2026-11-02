-- ════════════════════════════════════════════════════════
-- DATA PLATFORM – DATENBANK-INITIALISIERUNG
-- Ausführen: psql -h localhost -U postgres -d data_platform -f init_db.sql
-- ════════════════════════════════════════════════════════

-- ── Schemas ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS metadata;

-- ── raw.sales_import (Rohdaten – unverändert) ────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.sales_import (
    id          BIGSERIAL PRIMARY KEY,
    order_date  TEXT,
    customer    TEXT,
    product     TEXT,
    amount      TEXT,
    quantity    TEXT,
    dateiname   VARCHAR(500),
    batch_id    UUID,
    geladen_am  TIMESTAMPTZ DEFAULT NOW()
);

-- ── staging.sales_clean (bereinigte Daten) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.sales_clean (
    id           BIGSERIAL PRIMARY KEY,
    order_date   DATE        NOT NULL,
    customer     VARCHAR(255) NOT NULL,
    product      VARCHAR(255) NOT NULL,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    quantity     INTEGER       NOT NULL DEFAULT 1 CHECK (quantity > 0),
    raw_id       BIGINT REFERENCES raw.sales_import(id),
    batch_id     UUID,
    dateiname    VARCHAR(500),
    data_hash    VARCHAR(64),
    geladen_am   TIMESTAMPTZ DEFAULT NOW(),
    aktualisiert TIMESTAMPTZ DEFAULT NOW()
);

-- ── mart.sales_daily (tägliche Auswertung für Power BI) ─────────────────────
CREATE TABLE IF NOT EXISTS mart.sales_daily (
    sale_date        DATE PRIMARY KEY,
    total_orders     INTEGER       NOT NULL DEFAULT 0,
    total_customers  INTEGER       NOT NULL DEFAULT 0,
    total_revenue    NUMERIC(15,2) NOT NULL DEFAULT 0,
    avg_order_value  NUMERIC(10,2),
    aktualisiert     TIMESTAMPTZ DEFAULT NOW()
);

-- ── mart.sales_prognose (ML-Prognosen) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS mart.sales_prognose (
    datum        DATE PRIMARY KEY,
    prognose     NUMERIC(12,2) NOT NULL,
    tag          INTEGER,
    batch_id     UUID,
    erstellt_am  TIMESTAMPTZ DEFAULT NOW()
);

-- ── metadata.etl_log (ETL-Protokoll) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metadata.etl_log (
    id           BIGSERIAL PRIMARY KEY,
    batch_id     UUID,
    status       VARCHAR(20),   -- erfolg | fehler | keine_daten
    dateien      INTEGER DEFAULT 0,
    zeilen_roh   INTEGER DEFAULT 0,
    zeilen_clean INTEGER DEFAULT 0,
    anomalien    INTEGER DEFAULT 0,
    dauer_sek    NUMERIC(8,2),
    fehler_text  TEXT,
    gestartet_am TIMESTAMPTZ DEFAULT NOW(),
    beendet_am   TIMESTAMPTZ
);

-- ── Trigger: automatisches aktualisiert-Timestamp ────────────────────────────
CREATE OR REPLACE FUNCTION metadata.set_aktualisiert()
RETURNS TRIGGER AS $$
BEGIN
    NEW.aktualisiert = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sales_clean_aktualisiert'
    ) THEN
        CREATE TRIGGER trg_sales_clean_aktualisiert
        BEFORE UPDATE ON staging.sales_clean
        FOR EACH ROW EXECUTE FUNCTION metadata.set_aktualisiert();
    END IF;
END $$;

-- ── Indizes für Performance ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sales_clean_date     ON staging.sales_clean(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_clean_customer ON staging.sales_clean(customer);
CREATE INDEX IF NOT EXISTS idx_sales_clean_batch    ON staging.sales_clean(batch_id);
CREATE INDEX IF NOT EXISTS idx_etl_log_batch        ON metadata.etl_log(batch_id);
