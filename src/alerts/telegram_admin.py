#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM – NUR FÜR DEN ADMIN
=============================
Sendet technische Benachrichtigungen ausschließlich an den Entwickler/Admin.
Kunden sehen KEINE Telegram-Nachrichten!

Konfiguration in .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_ADMIN_CHAT_ID=...
"""

import asyncio
import io
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramAdmin:
    """
    Telegram-Benachrichtigungen nur für den Admin.

    📱 Telegram → Admin (du)
    📧 E-Mail   → Kunden  (EmailKunde)
    """

    def __init__(self):
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
        self._bot    = None
        self.aktiv   = bool(self.token and self.chat_id)

        if self.aktiv:
            try:
                import telegram
                self._bot = telegram.Bot(token=self.token)
                logger.info("✅ Telegram-Admin bereit (Chat-ID: %s)", self.chat_id)
            except ImportError:
                logger.error("❌ python-telegram-bot fehlt → pip install python-telegram-bot")
                self.aktiv = False
        else:
            logger.warning("⚠️ Telegram deaktiviert – Token oder Chat-ID fehlt in .env")

    # ── SENDEN ───────────────────────────────────────────────────────────────

    def _async_run(self, coro):
        """Führt async-Code aus (kompatibel mit Jupyter und PyCharm)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result(timeout=15)
            return loop.run_until_complete(coro)
        except Exception:
            try:
                return asyncio.run(coro)
            except Exception as e:
                logger.error("❌ Async-Fehler: %s", e)

    def sende(self, text: str, parse_mode: str = "Markdown"):
        """Sendet eine Textnachricht an den Admin."""
        if not self.aktiv:
            return
        async def _s():
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
        try:
            self._async_run(_s())
        except Exception as e:
            logger.error("❌ Telegram-Fehler: %s", e)

    def sende_bild(self, bild: bytes, caption: str = ""):
        """Sendet ein Diagramm-Bild."""
        if not self.aktiv:
            return
        async def _s():
            await self._bot.send_photo(
                chat_id=self.chat_id,
                photo=bild,
                caption=caption
            )
        try:
            self._async_run(_s())
        except Exception as e:
            logger.error("❌ Telegram-Bild-Fehler: %s", e)

    # ── VORGEFERTIGTE NACHRICHTEN ─────────────────────────────────────────────

    def start(self, version: str = "2.0"):
        """Systemnachricht beim Start."""
        self.sende(
            f"🚀 *DATA PLATFORM v{version} GESTARTET*\n"
            f"🕐 `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`\n"
            f"📱 Telegram → nur Admin\n"
            f"📧 E-Mail   → nur Kunden"
        )

    def etl_ok(self, stats: dict):
        """ETL erfolgreich abgeschlossen."""
        text = (
            f"✅ *ETL ERFOLGREICH*\n"
            f"📊 `{stats.get('clean', 0):,}` Zeilen geladen\n"
            f"📁 `{stats.get('dateien', 0)}` Datei(en)\n"
            f"⚡ `{stats.get('dauer', 0):.1f}s`\n"
            f"🆔 `{str(stats.get('batch_id', ''))[:8]}`"
        )
        if stats.get("anomalien", 0):
            text += f"\n⚠️ `{stats['anomalien']}` Anomalie(n)"
        if stats.get("prognose_summe"):
            text += f"\n📈 Prognose: `{stats['prognose_summe']:,.0f} €`"
        self.sende(text)

    def etl_fehler(self, fehler: str, batch_id: str = ""):
        """Kritischer ETL-Fehler."""
        self.sende(
            f"❌ *ETL FEHLER*\n"
            f"🆔 `{batch_id[:8] if batch_id else 'N/A'}`\n"
            f"```\n{fehler[:400]}\n```"
        )

    def anomalie_kritisch(self, a: dict):
        """Sofort-Alarm bei kritischer Anomalie."""
        self.sende(
            f"🚨 *KRITISCHE ANOMALIE*\n"
            f"📅 `{a.get('datum', '?')}`\n"
            f"💰 Wert: `{a.get('wert', 0):,.2f} €`\n"
            f"📊 Erwartet: `{a.get('erwartet', 0):,.2f} €`\n"
            f"📈 Abw.: `{a.get('abweichung', 0):+.1f}%`\n"
            f"🔍 {a.get('grund', '')}"
        )

    def power_bi(self, ok: bool, info: str = ""):
        """Power BI Aktualisierungs-Status."""
        symbol = "✅" if ok else "❌"
        self.sende(f"📊 *Power BI* {symbol}\n{info[:200]}" if info else f"📊 *Power BI* {symbol}")

    def db_fehler(self, fehler: str):
        """Datenbankverbindungs-Fehler."""
        self.sende(f"🔴 *DATENBANK-FEHLER*\n```\n{fehler[:300]}\n```")

    def tagesbericht_admin(self, stats_etl: dict, stats_tag: dict):
        """
        Täglicher Admin-Bericht mit technischen Details.
        Kunden bekommen eine separate, schönere E-Mail.
        """
        heute = datetime.now().strftime("%d.%m.%Y")
        aend  = stats_tag.get("veraenderung", 0)
        sym   = "▲" if aend >= 0 else "▼"

        self.sende(
            f"📊 *ADMIN-TAGESBERICHT {heute}*\n\n"
            f"💰 Umsatz: `{stats_tag.get('heute', 0):,.0f} €` "
            f"({sym}{abs(aend):.1f}%)\n"
            f"📦 Bestellungen: `{stats_tag.get('bestellungen', 0)}`\n"
            f"👥 Kunden: `{stats_tag.get('aktive_kunden', 0)}`\n\n"
            f"⚙️ ETL-Läufe: `{stats_etl.get('etl_durchlaeufe', 0)}`\n"
            f"⚙️ Zeilen gesamt: `{stats_etl.get('verarbeitete_zeilen', 0):,}`\n"
            f"⚙️ Fehler: `{stats_etl.get('fehler', 0)}`\n\n"
            f"📧 _Kunden-E-Mail separat versendet_"
        )

    def health_check(self, bericht: str, kritische: int = 0):
        """System Health-Check Bericht."""
        header = "✅ *HEALTH-CHECK OK*" if kritische == 0 else f"⚠️ *HEALTH-CHECK: {kritische} FEHLER*"
        self.sende(f"{header}\n\n```\n{bericht[:3500]}\n```")

    def sende_diagramm(self, df, x: str, y: str, titel: str):
        """Sendet Umsatz-Diagramm als Bild."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(df[x], df[y], marker="o", linewidth=2, color="#1e3a5f", markersize=4)
            ax.set_title(titel, fontsize=13, fontweight="bold")
            ax.set_xlabel(x)
            ax.set_ylabel(y)
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
            buf.seek(0)
            plt.close(fig)

            self.sende_bild(buf.read(), caption=titel)
        except Exception as e:
            logger.error("❌ Diagramm-Fehler: %s", e)
