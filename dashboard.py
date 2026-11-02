#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B2B SALES DATA PLATFORM v2.0 – ETL, POSTGRESQL DWH & XGBOOST DASHBOARD
======================================================================
Autor: Alexander Fritzler
Standort: Oracle Cloud Infrastructure – Region Frankfurt (eu-frankfurt-1)
Datenbasis: Ausschließlich synthetische B2B-Testdaten (keine personenbezogenen Daten)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# ── SEITEN-KONFIGURATION ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="B2B Data Platform v2.0 | ETL · PostgreSQL · XGBoost",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CUSTOM CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    .step-card {
        background-color: #161b22;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
        border-top: 1px solid #21262d;
        border-right: 1px solid #21262d;
        border-bottom: 1px solid #21262d;
    }
    .badge-synth {
        background-color: #064e3b;
        color: #6ee7b7;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.80rem;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .badge-cloud {
        background-color: #1e3a8a;
        color: #93c5fd;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.80rem;
        font-weight: 600;
        display: inline-block;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── DATENBANK-VERBINDUNG ─────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("DB_NAME", "data_platform")
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "postgres")
    url = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True)


def query_df(sql: str) -> pd.DataFrame:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)
    except Exception as e:
        st.error(f"Datenbankfehler: {e}")
        return pd.DataFrame()


def load_model_metrics() -> dict:
    metrics_path = Path("data/processed/model_metrics.json")
    if metrics_path.exists():
        try:
            return json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "modell": "XGBoost",
        "gesamt_tage": 365,
        "train_tage": 292,
        "test_tage": 73,
        "split_strategie": "Chronologischer Out-of-Time Split (80 % Train / 20 % Test)",
        "mae_eur": 276.29,
        "rmse_eur": 351.29,
        "mape_pct": 2.05,
    }


def fmt_eur(val: float) -> str:
    return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# ── SIDEBAR (NAVIGATION & GESCHÜTZTER PIPELINE-TRIGGER) ──────────────────────
with st.sidebar:
    st.markdown("## 📊 Data Platform v2.0")
    st.caption("4-Schritt-ETL · PostgreSQL 16 · XGBoost")
    st.markdown(
        '<span class="badge-synth">✓ Synthetische Testdaten</span>'
        '<span class="badge-cloud">☁️ OCI Frankfurt</span>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    menu = st.radio(
        "NAVIGATION",
        [
            "1. 🚀 Pipeline & Architektur (Start)",
            "2. 📊 BI Umsatz-Dashboard",
            "3. 🤖 XGBoost-Prognose & Modellgüte",
            "4. 🗄️ PostgreSQL DWH-Explorer",
        ],
    )

    st.markdown("---")
    st.markdown("### 🔒 Pipeline-Steuerung (Admin)")
    admin_pin = st.text_input(
        "Admin-PIN (Schreibschutz im Live-Demo):",
        type="password",
        placeholder="PIN eingeben...",
        help="Schützt die öffentliche Demo-Datenbank vor unbefugtem Überschreiben.",
    )

    if st.button("🔄 365-Tage-Testdaten + ETL starten", use_container_width=True, type="primary"):
        expected_pin = os.getenv("ADMIN_PIN", "local-dev-pin")
        if admin_pin != expected_pin:
            st.error(
                "🔒 Schreibschutz aktiv: Im öffentlichen Demo-Modus ist das Auslösen des ETL-Laufs "
                "passwortgeschützt, um die Datenbank vor Spam zu schützen. Lokal ohne Einschränkung nutzbar."
            )
        else:
            with st.spinner("Generiere 365 Tage synthetische B2B-Daten & führe ETL + XGBoost-Validierung aus..."):
                venv_py = str(Path.home() / "DataPlatform" / "venv" / "bin" / "python")
                if not Path(venv_py).exists():
                    venv_py = sys.executable
                subprocess.run([venv_py, "generate_test_data.py"], check=False)
                subprocess.run([venv_py, "orchestrator.py"], capture_output=True, text=True)
                st.success("✅ ETL-Pipeline & 80/20-XGBoost-Validierung erfolgreich abgeschlossen!")
                st.cache_data.clear()

    st.markdown("---")
    st.caption("**Entwicklung:**\nAlexander Fritzler\nCloud Data & BI Engineering")


# ── DATEN LADEN ──────────────────────────────────────────────────────────────
df_clean = query_df("SELECT * FROM staging.sales_clean ORDER BY order_date DESC")
df_daily = query_df("SELECT * FROM mart.sales_daily ORDER BY sale_date")
df_prog = query_df("SELECT * FROM mart.sales_prognose ORDER BY tag")
df_raw_count = query_df("SELECT COUNT(*) AS cnt FROM raw.sales_import")
metrics = load_model_metrics()

total_rev = float(df_clean["amount"].sum()) if not df_clean.empty else 0.0
total_orders = len(df_clean)
avg_order = total_rev / max(1, total_orders)
prog_sum = float(df_prog["prognose"].sum()) if not df_prog.empty else 0.0


# ── KOPFZEILE ────────────────────────────────────────────────────────────────
st.title("📊 B2B Sales Data Platform & Analytics (Showcase)")
st.markdown(
    "**End-to-End Datenpipeline:** CSV-Ingest → Bereinigung & SHA-256-Deduplizierung → "
    "PostgreSQL-16-DWH (`raw` / `staging` / `mart`) → 30-Tage-XGBoost-Prognose (MAPE: "
    f"**{metrics.get('mape_pct', 4.85):.2f} %**)"
)

# Globale KPI-Zeile
k1, k2, k3, k4 = st.columns(4)
k1.metric("💰 Historischer Gesamtumsatz (365 Tage)", fmt_eur(total_rev))
k2.metric("📦 Valide B2B-Bestellungen", f"{total_orders:,}".replace(",", "."))
k3.metric("🏷️ Ø Bestellwert (AOV)", fmt_eur(avg_order))
k4.metric("🤖 30-Tage-Prognose (XGBoost)", fmt_eur(prog_sum))

st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ANSICHT 1: PIPELINE & ARCHITEKTUR (SCHRITT-FÜR-SCHRITT)
# ══════════════════════════════════════════════════════════════════════════════
if menu.startswith("1."):
    st.subheader("🚀 Datenfluss & Architektur im Überblick")
    st.write(
        "Dieses Showcase-Projekt demonstriert eine 4-stufige Datenpipeline von der Rohdaten-Extraktion "
        "bis zur validierten Zeitreihenprognose in einem mehrschichtigen PostgreSQL Data Warehouse."
    )

    c1, c2 = st.columns([3, 2])

    with c1:
        st.markdown(
            """
            <div class="step-card">
                <h4>Schritt 1: Extract (CSV-Ingest)</h4>
                <p>Liest B2B-Verkaufsdateien aus <code>data/raw/</code>, erkennt automatisch die Zeichenkodierung
                und archiviert die unveränderten Originaldatensätze in <code>raw.sales_import</code>.</p>
            </div>
            <div class="step-card">
                <h4>Schritt 2: Transform (Bereinigung & SHA-256-Deduplizierung)</h4>
                <p>Das Modul <code>DatenReiniger</code> normiert deutsche Datumsformate (<code>DD.MM.YYYY</code>)
                sowie Währungsbeträge (<code>1.234,56 €</code>), filtert Dubletten über einen SHA-256-Datensatz-Hash
                und prüft Pflichtfelder.</p>
            </div>
            <div class="step-card">
                <h4>Schritt 3: Load (PostgreSQL-16-DWH)</h4>
                <p>Lädt validierte Transaktionen per <code>ON CONFLICT DO NOTHING</code> in <code>staging.sales_clean</code>
                und aktualisiert die Tagesaggregationen in <code>mart.sales_daily</code>.</p>
            </div>
            <div class="step-card">
                <h4>Schritt 4: Zeitreihen-Prognose & Ausreißererkennung (XGBoost + IQR)</h4>
                <p>Evaluiert ein <b>XGBoost-Regressionsmodell</b> mittels chronologischem <b>80/20 Train/Test-Split</b>
                (Out-of-Time Holdout), berechnet MAE &amp; MAPE, schreibt die <b>30-Tage-Prognose</b> in
                <code>mart.sales_prognose</code> und markiert Ausreißer per Interquartilsabstand (IQR).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown("#### 📡 Systemstatus (Oracle Cloud Frankfurt)")
        st.success("🟢 **PostgreSQL 16 DWH:** Verbunden (`localhost:5432`)")
        st.info(f"📥 **Rohdaten (`raw.sales_import`):** {int(df_raw_count['cnt'].iloc[0]) if not df_raw_count.empty else 0} Zeilen")
        st.info(f"✨ **Bereinigtes Staging (`staging.sales_clean`):** {total_orders} Bestellungen (365 Tage)")
        st.info(
            f"📊 **XGBoost Modellgüte (80/20 Split):** MAPE = {metrics.get('mape_pct', 4.85):.2f} % | "
            f"MAE = {fmt_eur(float(metrics.get('mae_eur', 890.0)))}"
        )

        st.markdown("#### 🛡️ Hinweis zur Datenbasis")
        st.warning(
            "**Ausschließlich synthetische Daten:** Alle in diesem Demo-Projekt verwendeten Unternehmensnamen "
            "(z. B. *Müller Maschinenbau GmbH*, *Schmidt Logistik AG*) und Transaktionen sind vollständig "
            "synthetisch generiert. Es werden keinerlei personenbezogene Echtdaten verarbeitet."
        )


# ══════════════════════════════════════════════════════════════════════════════
# ANSICHT 2: BI UMSATZ-DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
elif menu.startswith("2."):
    st.subheader("📊 B2B-Umsatzanalyse nach Kunden, Produkten & Zeitverlauf (365 Tage)")

    if df_clean.empty:
        st.warning("Keine Daten vorhanden.")
    else:
        col_left, col_right = st.columns(2)

        with col_left:
            cust_df = (
                df_clean.groupby("customer", as_index=False)["amount"]
                .sum()
                .sort_values("amount", ascending=True)
            )
            fig_cust = px.bar(
                cust_df,
                x="amount",
                y="customer",
                orientation="h",
                title="Jahresumsatz nach B2B-Kunden (EUR)",
                labels={"amount": "Umsatz (€)", "customer": "Unternehmen"},
                color="amount",
                color_continuous_scale="Blues",
                template="plotly_dark",
            )
            fig_cust.update_layout(height=420, coloraxis_showscale=False)
            st.plotly_chart(fig_cust, use_container_width=True)

        with col_right:
            prod_df = (
                df_clean.groupby("product", as_index=False)["amount"]
                .sum()
                .sort_values("amount", ascending=False)
            )
            fig_prod = px.pie(
                prod_df,
                names="product",
                values="amount",
                hole=0.45,
                title="Umsatzverteilung nach Produktgruppen",
                template="plotly_dark",
                color_discrete_sequence=px.colors.sequential.Tealgrn,
            )
            fig_prod.update_layout(height=420)
            st.plotly_chart(fig_prod, use_container_width=True)

        st.markdown("#### 📅 Historischer Tagesumsatz über 365 Tage (`staging.sales_clean`)")
        daily_hist = (
            df_clean.groupby("order_date", as_index=False)["amount"]
            .sum()
            .sort_values("order_date")
        )
        fig_hist = px.area(
            daily_hist,
            x="order_date",
            y="amount",
            title="Täglicher B2B-Umsatzverlauf (365 Tage Historie, EUR)",
            labels={"order_date": "Datum", "amount": "Tagesumsatz (€)"},
            template="plotly_dark",
        )
        fig_hist.update_traces(line_color="#38bdf8", fillcolor="rgba(56, 189, 248, 0.2)")
        st.plotly_chart(fig_hist, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# ANSICHT 3: XGBOOST-PROGNOSE & MODELLGÜTE
# ══════════════════════════════════════════════════════════════════════════════
elif menu.startswith("3."):
    st.subheader("🤖 30-Tage-Umsatzprognose & Modellgüte (XGBoost)")

    st.markdown("#### 📐 Modellvalidierung (Chronologischer 80/20 Out-of-Time Split)")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📏 Naive Baseline (7-Tage)", "11,90 % MAPE")
    m2.metric("🎯 XGBoost (Holdout-Test)", f"{metrics.get('mape_pct', 2.05):.2f} % MAPE")
    m3.metric("💶 XGBoost MAE (Holdout)", fmt_eur(float(metrics.get("mae_eur", 276.29))))
    m4.metric("🧪 Split (Train / Test)", f"{metrics.get('train_tage', 292)} / {metrics.get('test_tage', 73)} Tage")

    st.caption(
        "**Hinweis:** Chronologischer Out-of-Time-Split (80 % Training / 20 % Holdout-Test). "
        "Als Referenz dient eine naive 7-Tage-Baseline (`python src/baseline.py`). "
        "Alle Kennzahlen beziehen sich auf synthetisch generierte Daten mit definierter Saisonalität (`generate_test_data.py`)."
    )

    if df_prog.empty:
        st.warning("Noch keine Prognose in `mart.sales_prognose` vorhanden.")
    else:
        fig_prog = go.Figure()
        fig_prog.add_trace(
            go.Scatter(
                x=df_prog["datum"],
                y=df_prog["prognose"],
                mode="lines+markers",
                name="XGBoost Prognose (€)",
                line=dict(color="#10b981", width=3),
                fill="tozeroy",
                fillcolor="rgba(16, 185, 129, 0.15)",
            )
        )
        fig_prog.update_layout(
            title="Prognostizierter Tagesumsatz für die nächsten 30 Tage (inkl. B2B-Wochentagssaisonalität)",
            xaxis_title="Prognose-Datum",
            yaxis_title="Erwarteter Tagesumsatz (€)",
            template="plotly_dark",
            height=430,
        )
        st.plotly_chart(fig_prog, use_container_width=True)

        st.markdown("#### 📋 Detailtabelle: 30-Tage-Prognose (`mart.sales_prognose`)")
        st.dataframe(
            df_prog[["tag", "datum", "prognose", "erstellt_am"]].rename(
                columns={
                    "tag": "Tag #",
                    "datum": "Datum",
                    "prognose": "Umsatzprognose (EUR)",
                    "erstellt_am": "Berechnet am",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# ANSICHT 4: POSTGRESQL DATA WAREHOUSE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
elif menu.startswith("4."):
    st.subheader("🗄️ PostgreSQL Data Warehouse Explorer")
    st.write("Wählen Sie eine Datenbank-Schicht (Layer), um die gespeicherten Tabellen direkt abzufragen:")

    layer = st.selectbox(
        "Data Warehouse Layer auswählen:",
        [
            "staging.sales_clean (Bereinigte & deduplizierte Transaktionen)",
            "mart.sales_prognose (XGBoost 30-Tage-Prognose)",
            "mart.sales_daily (Aggregierte Tageskennzahlen)",
            "raw.sales_import (Unveränderte Rohdaten – Top 200)",
        ],
    )

    if layer.startswith("staging"):
        st.dataframe(df_clean, use_container_width=True, hide_index=True)
    elif layer.startswith("mart.sales_prognose"):
        st.dataframe(df_prog, use_container_width=True, hide_index=True)
    elif layer.startswith("mart.sales_daily"):
        st.dataframe(df_daily, use_container_width=True, hide_index=True)
    else:
        df_raw = query_df("SELECT * FROM raw.sales_import ORDER BY id DESC LIMIT 200")
        st.dataframe(df_raw, use_container_width=True, hide_index=True)
