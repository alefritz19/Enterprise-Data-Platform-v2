#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SYNTHETISCHER B2B-TESTDATEN-GENERATOR
=====================================
Erzeugt ausschließlich synthetische B2B-Verkaufstransaktionen (keine personenbezogenen Daten)
über einen Zeitraum von 365 Tagen mit realistischer Wochentags- und Quartalssaisonalität
zur Evaluierung der ETL-Pipeline und des XGBoost-Prognosemodells.
"""

from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd


def generiere_testdaten() -> Path:
    np.random.seed(42)
    companies = [
        "Müller Maschinenbau GmbH",
        "Schmidt Logistik AG",
        "Bauer Elektrotechnik GmbH",
        "Fischer Automatisierung GmbH",
        "Weber & Partner KG",
        "Hoffmann Werkzeuge AG",
        "Wagner Präzisionsteile GmbH",
        "Becker Industriebedarf GmbH",
    ]
    products = [
        ("Industrie-Sensor X1", 1850.0),
        ("Hydraulik-Pumpe Pro", 4100.0),
        ("Kabelbaum Standard", 1150.0),
        ("Sicherheitsmodul S3", 2950.0),
        ("Steuerungseinheit Alpha", 4850.0),
    ]

    # 365 Tage Historie bis gestern für sauberes Zeitreihen-Training (80/20 Split)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    start_date = end_date - timedelta(days=364)
    dates = [start_date + timedelta(days=i) for i in range(365)]

    rows = []
    for idx, d in enumerate(dates):
        weekday = d.weekday()
        # Realistische B2B-Wochentagsstruktur (Mo-Do Kernwoche, Fr leicht reduziert, Sa/So Bereitschaft)
        if weekday in (0, 1, 2, 3):
            n_orders = 5
            day_factor = 1.08 if weekday in (1, 2) else 1.02
        elif weekday == 4:
            n_orders = 5
            day_factor = 0.92
        else:
            n_orders = 4
            day_factor = 0.82

        # Typischer B2B-Monatszyklus (Monatsendgeschäft ab dem 24. & Monatsanfangsbestellungen)
        if d.day >= 24:
            month_cycle = 1.24
        elif d.day <= 5:
            month_cycle = 1.12
        else:
            month_cycle = 0.96
        seasonal_factor = month_cycle

        for o_idx in range(n_orders):
            c = companies[(idx + o_idx) % len(companies)]
            p_name, base_price = products[(o_idx + (1 if weekday == 2 else 0)) % len(products)]
            noise = np.random.normal(1.0, 0.05)
            amt = round(max(250.0, base_price * day_factor * seasonal_factor * noise), 2)
            qty = int(max(1, round(amt / 850.0)))
            amt_str = f"{amt:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            rows.append(
                {
                    "order_date": d.strftime("%d.%m.%Y"),
                    "customer": c,
                    "product": p_name,
                    "amount": amt_str,
                    "quantity": qty,
                }
            )

    raw_dir = Path("data/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_file = raw_dir / "sales_b2b_365d.csv"

    df = pd.DataFrame(rows)
    df.to_csv(out_file, index=False, encoding="utf-8")
    print(f"✅ Erfolgreich generiert: {len(df)} synthetische B2B-Bestellungen (365 Tage) in {out_file}")
    return out_file


if __name__ == "__main__":
    generiere_testdaten()
