#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-MAIL – NUR FÜR KUNDEN
========================
Sendet EINMAL TÄGLICH um 08:00 Uhr einen vollständigen
Tagesbericht auf DEUTSCH an den Kunden.

Inhalt (4 Blöcke):
    1. 📈 Tagesumsatz (KPI-Karten)
    2. ⚠️  Anomalien / ✅ Alles OK
    3. 🤖 KI-Prognose nächste 30 Tage
    4. 📊 Power BI Dashboard-Link

Konfiguration in .env:
    EMAIL_ENABLED=true
    EMAIL_SMTP_HOST=smtp.gmail.com
    EMAIL_SMTP_PORT=587
    EMAIL_SENDER=dein@gmail.com
    EMAIL_SENDER_PASSWORD=app_passwort
    CLIENT_EMAIL=kunde@firma.de
    CLIENT_NAME=Herr Müller
    POWERBI_REPORT_URL=https://app.powerbi.com/view?r=...
"""

import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailKunde:
    """
    Täglicher Kunden-Bericht per E-Mail.

    📱 Telegram → Admin    (TelegramAdmin)
    📧 E-Mail   → Kunden   (diese Klasse)
    """

    def __init__(self):
        self.aktiv    = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

        if not self.aktiv:
            logger.info("📧 Kunden-E-Mail deaktiviert (EMAIL_ENABLED=false)")
            return

        # SMTP
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.absender  = os.getenv("EMAIL_SENDER", "")
        self.passwort  = os.getenv("EMAIL_SENDER_PASSWORD", "")

        # Kunde
        self.empfaenger    = os.getenv("CLIENT_EMAIL", "")
        self.name          = os.getenv("CLIENT_NAME", "Sehr geehrter Kunde")
        self.powerbi_url   = os.getenv("POWERBI_REPORT_URL", "")

        ok = bool(self.absender and self.passwort and self.empfaenger)
        if not ok:
            logger.warning("⚠️ E-Mail: Konfiguration unvollständig (prüfe .env)")

        logger.info("✅ Kunden-E-Mail bereit → %s", self.empfaenger)

    # ── VERSAND ───────────────────────────────────────────────────────────────

    def _bereit(self) -> bool:
        return self.aktiv and bool(self.absender and self.passwort and self.empfaenger)

    def _sende(self, betreff: str, html: str, text: str):
        if not self._bereit():
            logger.debug("📧 Versand übersprungen")
            return
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = betreff
            msg["From"]    = f"Data Platform <{self.absender}>"
            msg["To"]      = self.empfaenger
            msg.attach(MIMEText(text, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))

            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.login(self.absender, self.passwort)
                srv.sendmail(self.absender, self.empfaenger, msg.as_string())

            logger.info("✅ E-Mail gesendet → %s", self.empfaenger)

        except smtplib.SMTPAuthenticationError:
            logger.error("❌ SMTP Auth fehlgeschlagen – App-Passwort prüfen!")
        except smtplib.SMTPException as e:
            logger.error("❌ SMTP Fehler: %s", e)
        except Exception as e:
            logger.error("❌ E-Mail Fehler: %s", e)

    # ── HAUPT-METHODE ─────────────────────────────────────────────────────────

    def tagesbericht(
        self,
        umsatz: dict,
        anomalien: Optional[List[dict]] = None,
        prognose: Optional[dict] = None,
    ):
        """
        Sendet den kompletten Tagesbericht.
        Wird vom Orchestrator täglich um 08:00 aufgerufen.

        Args:
            umsatz:
                heute        float   Umsatz heute in €
                gestern      float   Umsatz gestern in €
                veraenderung float   Änderung in %
                bestellungen int     Anzahl Bestellungen
                durchschnitt float   Ø Bestellwert in €
                aktive_kunden int    Anzahl aktiver Kunden
                neukunden    int     Neukunden heute
                monat_gesamt float   (optional) Monatsumsatz

            anomalien: [{'datum', 'wert', 'erwartet', 'abweichung', 'grund'}, ...]
            prognose:  {'summe', 'durchschnitt', 'modell', 'fehler'}
        """
        heute = datetime.now().strftime("%d.%m.%Y")
        aend  = umsatz.get("veraenderung", 0)
        pfeil = "▲" if aend >= 0 else "▼"
        farbe = "#27ae60" if aend >= 0 else "#e74c3c"

        betreff = f"📊 Ihr Tagesbericht – {heute}"

        html = (
            self._kopf()
            + self._anrede(heute)
            + self._block_umsatz(umsatz, pfeil, farbe, aend)
            + self._block_anomalien(anomalien)
            + self._block_prognose(prognose)
            + self._block_powerbi()
            + self._fuss()
        )

        text = self._plaintext(heute, umsatz, pfeil, aend, anomalien, prognose)
        self._sende(betreff, html, text)

    # ── HTML-BLÖCKE ──────────────────────────────────────────────────────────

    def _kopf(self) -> str:
        return """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;
             font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 10px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:10px;overflow:hidden;
              box-shadow:0 4px 20px rgba(0,0,0,0.12);">

<!-- HEADER -->
<tr>
  <td style="background:linear-gradient(135deg,#1e3a5f 0%,#2d6a9f 100%);
             padding:30px 36px;text-align:center;">
    <div style="font-size:32px;margin-bottom:8px;">📊</div>
    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:bold;">
      Data Platform
    </h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.7);font-size:13px;">
      Automatisierter Tagesbericht
    </p>
  </td>
</tr>

<!-- INHALT -->
<tr><td style="padding:32px 36px;">
"""

    def _fuss(self) -> str:
        return f"""
</td></tr>

<!-- FOOTER -->
<tr>
  <td style="background:#f8f9fa;padding:18px 36px;
             border-top:1px solid #e8e8e8;text-align:center;">
    <p style="margin:0;font-size:11px;color:#aaa;line-height:1.7;">
      Automatisch generiert von Ihrer Data Platform.<br>
      Bei Fragen antworten Sie einfach auf diese E-Mail.<br>
      © {datetime.now().year} Data Platform
    </p>
  </td>
</tr>

</table>
</td></tr></table>
</body></html>
"""

    def _anrede(self, datum: str) -> str:
        return f"""
<p style="color:#444;font-size:15px;margin:0 0 6px;">
  Guten Morgen, {self.name},
</p>
<p style="color:#666;font-size:14px;margin:0 0 28px;line-height:1.6;">
  anbei Ihr automatischer Tagesbericht vom <strong>{datum}</strong>.
</p>
"""

    def _trennlinie(self, emoji: str, titel: str, farbe: str = "#1e3a5f") -> str:
        return f"""
<h3 style="margin:0 0 16px;color:{farbe};font-size:16px;
           border-bottom:2px solid {farbe};padding-bottom:8px;">
  {emoji}&nbsp; {titel}
</h3>
"""

    def _karte(
        self, emoji: str, label: str, wert: str,
        sub: str = "", rand: str = "#1e3a5f"
    ) -> str:
        sub_html = f'<div style="font-size:12px;color:#888;margin-top:5px;">{sub}</div>' if sub else ""
        return f"""
<td width="50%" style="padding:6px;vertical-align:top;">
  <div style="background:#f8f9fa;border-left:4px solid {rand};
              padding:16px 18px;border-radius:6px;">
    <div style="font-size:11px;color:#999;text-transform:uppercase;
                letter-spacing:0.5px;margin-bottom:6px;">
      {emoji}&nbsp; {label}
    </div>
    <div style="font-size:22px;font-weight:bold;color:#1e3a5f;">
      {wert}
    </div>
    {sub_html}
  </div>
</td>
"""

    def _block_umsatz(
        self, u: dict, pfeil: str, farbe: str, aend: float
    ) -> str:
        def e(v): return f"{v:,.0f}&nbsp;€".replace(",", ".")

        html = self._trennlinie("📈", "Tagesumsatz")
        html += f"""
<table width="100%" cellpadding="0" cellspacing="0">
<tr>
  {self._karte("💶", "Umsatz heute",
    e(u.get('heute', 0)),
    f'<span style="color:{farbe};">{pfeil} {abs(aend):.1f}% zum Vortag</span>',
    "#1e3a5f")}
  {self._karte("📦", "Bestellungen",
    str(u.get('bestellungen', 0)),
    f"Ø&nbsp; {e(u.get('durchschnitt', 0))} / Bestellung",
    "#27ae60")}
</tr>
<tr style="height:10px;"><td colspan="2"></td></tr>
<tr>
  {self._karte("👥", "Aktive Kunden",
    str(u.get('aktive_kunden', 0)),
    f"{u.get('neukunden', 0)} Neukunden",
    "#8e44ad")}
  {self._karte("📅", "Umsatz gestern",
    e(u.get('gestern', 0)),
    "",
    "#e67e22")}
</tr>
</table>
"""
        if u.get("monat_gesamt"):
            html += f"""
<div style="background:#e8f4f8;border:1px solid #b8d9ed;
            padding:12px 18px;border-radius:6px;margin-top:8px;">
  📆 <strong>Monatsumsatz bisher:</strong>
  <span style="font-size:18px;font-weight:bold;color:#1e3a5f;margin-left:8px;">
    {u.get('monat_gesamt', 0):,.0f}&nbsp;€
  </span>
</div>
"""
        html += "<div style='height:30px;'></div>\n"
        return html

    def _block_anomalien(self, anomalien: Optional[List[dict]]) -> str:
        html = self._trennlinie("⚠️", "Anomalien", "#c0392b")

        if not anomalien:
            return html + """
<div style="background:#e8f5e9;border:1px solid #a5d6a7;
            padding:14px 20px;border-radius:6px;margin-bottom:28px;">
  ✅&nbsp; <strong style="color:#2e7d32;">Keine Anomalien erkannt</strong>
  – alle Werte liegen im Normalbereich.
</div>
"""
        html += f"""
<div style="background:#fff8e1;border:1px solid #ffe082;
            border-radius:6px;overflow:hidden;margin-bottom:12px;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-collapse:collapse;font-size:13px;">
  <tr style="background:#fff3cd;">
    <th style="padding:10px 14px;text-align:left;color:#666;width:22%;">Datum</th>
    <th style="padding:10px 14px;text-align:right;color:#666;width:20%;">Wert</th>
    <th style="padding:10px 14px;text-align:right;color:#666;width:20%;">Erwartet</th>
    <th style="padding:10px 14px;text-align:right;color:#666;width:15%;">Abw.</th>
    <th style="padding:10px 14px;text-align:left;color:#666;">Bemerkung</th>
  </tr>
"""
        for i, a in enumerate(anomalien[:6]):
            bg  = "#fffde7" if i % 2 == 0 else "#fff"
            abw = float(a.get("abweichung", 0))
            af  = "#c62828" if abw > 0 else "#2e7d32"
            html += f"""
  <tr style="background:{bg};">
    <td style="padding:10px 14px;">{a.get('datum','–')}</td>
    <td style="padding:10px 14px;text-align:right;font-weight:bold;">
      {float(a.get('wert',0)):,.2f}&nbsp;€
    </td>
    <td style="padding:10px 14px;text-align:right;color:#666;">
      {float(a.get('erwartet',0)):,.2f}&nbsp;€
    </td>
    <td style="padding:10px 14px;text-align:right;font-weight:bold;color:{af};">
      {abw:+.1f}%
    </td>
    <td style="padding:10px 14px;font-size:12px;color:#555;">
      {a.get('grund','–')}
    </td>
  </tr>
"""
        if len(anomalien) > 6:
            html += f"""
  <tr><td colspan="5" style="padding:8px 14px;color:#999;font-size:12px;font-style:italic;">
    + {len(anomalien)-6} weitere – bitte prüfen Sie das Dashboard.
  </td></tr>
"""
        html += "</table></div><div style='height:28px;'></div>\n"
        return html

    def _block_prognose(self, prognose: Optional[dict]) -> str:
        html = self._trennlinie("🤖", "KI-Prognose – Nächste 30 Tage")

        if not prognose:
            return html + """
<div style="background:#f8f9fa;border:1px solid #ddd;
            padding:14px 20px;border-radius:6px;color:#999;
            font-style:italic;margin-bottom:28px;">
  Für die Prognose sind derzeit nicht genügend historische Daten vorhanden.
</div>
"""
        genauigkeit = max(0.0, 100.0 - float(prognose.get("fehler", 5)))
        balken      = min(int(genauigkeit), 100)

        return html + f"""
<div style="background:#e8f5e9;border:1px solid #a5d6a7;
            padding:22px 24px;border-radius:8px;text-align:center;margin-bottom:14px;">
  <div style="font-size:12px;color:#555;text-transform:uppercase;
              letter-spacing:0.5px;margin-bottom:8px;">
    Erwarteter Gesamtumsatz
  </div>
  <div style="font-size:38px;font-weight:bold;color:#1b5e20;">
    {prognose.get('summe', 0):,.0f}&nbsp;€
  </div>
  <div style="font-size:14px;color:#555;margin-top:6px;">
    Ø&nbsp; {prognose.get('durchschnitt', 0):,.0f}&nbsp;€ pro Tag
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:18px;text-align:left;">
  <tr><td style="font-size:12px;color:#555;padding-bottom:5px;">
    Genauigkeit: <strong>{genauigkeit:.1f}%</strong>
    &nbsp;|&nbsp; Modell: <strong>{prognose.get('modell','Prophet')}</strong>
  </td></tr>
  <tr><td>
    <div style="background:#c8e6c9;border-radius:4px;height:8px;overflow:hidden;">
      <div style="background:#2e7d32;height:8px;width:{balken}%;border-radius:4px;"></div>
    </div>
  </td></tr>
  </table>
</div>
<p style="font-size:11px;color:#bbb;margin:0 0 28px;font-style:italic;">
  * Prognose basiert auf historischen Daten. Abweichungen sind möglich.
</p>
"""

    def _block_powerbi(self) -> str:
        if not self.powerbi_url:
            return ""
        return f"""
<div style="text-align:center;background:#f0f4f8;padding:22px;border-radius:8px;">
  <p style="margin:0 0 14px;font-size:14px;color:#555;">
    Alle Details finden Sie in Ihrem interaktiven Dashboard:
  </p>
  <a href="{self.powerbi_url}"
     style="display:inline-block;background:#1e3a5f;color:#fff;
            padding:13px 34px;border-radius:6px;text-decoration:none;
            font-weight:bold;font-size:14px;">
    📊&nbsp; Power BI Dashboard öffnen
  </a>
</div>
"""

    # ── PLAINTEXT ─────────────────────────────────────────────────────────────

    def _plaintext(
        self, datum, u, pfeil, aend, anomalien, prognose
    ) -> str:
        def e(v): return f"{v:,.0f} EUR"
        z = [
            f"TAGESBERICHT – {datum}",
            "=" * 44, "",
            "1. TAGESUMSATZ",
            f"   Heute:         {e(u.get('heute',0)):>14}  ({pfeil}{abs(aend):.1f}%)",
            f"   Gestern:       {e(u.get('gestern',0)):>14}",
            f"   Bestellungen:  {u.get('bestellungen',0):>14}",
            f"   Durchschnitt:  {e(u.get('durchschnitt',0)):>14}",
            f"   Aktive Kunden: {u.get('aktive_kunden',0):>14}",
            f"   Neukunden:     {u.get('neukunden',0):>14}",
            "", "2. ANOMALIEN",
        ]
        if anomalien:
            for a in anomalien[:6]:
                z.append(
                    f"   {a.get('datum','?')}  "
                    f"{float(a.get('wert',0)):,.2f} EUR  "
                    f"(erw. {float(a.get('erwartet',0)):,.2f}  "
                    f"Abw. {float(a.get('abweichung',0)):+.1f}%)"
                )
        else:
            z.append("   Keine Anomalien – alles im Normalbereich.")

        z += ["", "3. KI-PROGNOSE – NAECHSTE 30 TAGE"]
        if prognose:
            z += [
                f"   Erwartet:   {e(prognose.get('summe',0)):>14}",
                f"   Oe pro Tag: {e(prognose.get('durchschnitt',0)):>14}",
                f"   Modell:     {prognose.get('modell','Prophet'):>14}",
            ]
        else:
            z.append("   Nicht genug Daten fuer Prognose.")

        z += ["", "4. POWER BI DASHBOARD"]
        z.append(f"   {self.powerbi_url}" if self.powerbi_url else "   (kein Link konfiguriert)")

        z += ["", "=" * 44,
              "Automatisch generiert von Data Platform.",
              "Bei Fragen antworten Sie auf diese E-Mail."]
        return "\n".join(z)
