#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NAIVE BASELINE EVALUATION (7-TAGE-MUSTER)
=========================================
Berechnet den MAPE einer naiven 7-Tage-Baseline auf demselben chronologischen
80/20 Out-of-Time-Split wie das XGBoost-Modell als Referenzwert.
"""

import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")
db   = os.getenv("DB_NAME", "data_platform")
user = os.getenv("DB_USER", "postgres")
pw   = os.getenv("DB_PASSWORD", "postgres")

engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
df = pd.read_sql(
    "SELECT sale_date, total_revenue AS revenue FROM mart.sales_daily ORDER BY sale_date",
    engine,
)

split = int(len(df) * 0.8)  # gleicher chronologischer 80/20-Split wie XGBoost
test = df.iloc[split:].copy()

# Naive Baseline: letzte Trainingswoche wird zyklisch wiederholt
last_week = df["revenue"].iloc[split - 7 : split].to_numpy()
test["pred"] = np.resize(last_week, len(test))

mape = ((test["revenue"] - test["pred"]).abs() / test["revenue"]).mean() * 100
print(f"Baseline-MAPE: {mape:.2f} %")
