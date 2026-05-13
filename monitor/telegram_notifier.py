"""
Telegram alert sender for Midas Markets signal monitor.
Sends richly formatted messages with entry, SL, TP levels.
"""

import logging
import time
import requests

from signal_detector import Signal

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _fmt_price(price: float, symbol: str) -> str:
    """Format price with appropriate decimal places."""
    if symbol in ("BTCUSD",):
        return f"{price:,.1f}"
    if symbol in ("US30", "NAS100", "SPX500", "XAUUSD"):
        return f"{price:,.2f}"
    if price > 100:
        return f"{price:,.2f}"
    if price > 1:
        return f"{price:.4f}"
    return f"{price:.5f}"


def _direction_emoji(direction: str) -> str:
    return "📈" if direction == "BUY" else "📉"


def _bias_emoji(bias: str) -> str:
    mapping = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}
    return mapping.get(bias, "⚪")


def _strength_bar(strength: float) -> str:
    filled = int(strength / 10)
    bar    = "█" * filled + "░" * (10 - filled)
    return f"{bar} {strength:.0f}%"


def build_message(sig: Signal) -> str:
    d   = sig.direction
    sym = sig.symbol
    fp  = lambda p: _fmt_price(p, sym)

    direction_line = "🟢 BUY  — Long Entry" if d == "BUY" else "🔴 SELL — Short Entry"

    notes_text = "\n".join(f"   • {n}" for n in sig.notes) if sig.notes else "   • Momentum setup"

    msg = (
        f"⚡ *MIDAS SIGNAL ALERT* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{sym}*  |  {sig.full_name}\n"
        f"{direction_line}  {_direction_emoji(d)}\n"
        f"\n"
        f"🎯 *Entry Zone:* `{fp(sig.entry)}`\n"
        f"🛑 *Stop Loss:*  `{fp(sig.stop_loss)}`  ({sig.sl_pct}%)\n"
        f"✅ *Target 1:*   `{fp(sig.tp1)}`  (+{sig.tp1_pct}%)\n"
        f"✅ *Target 2:*   `{fp(sig.tp2)}`\n"
        f"✅ *Target 3:*   `{fp(sig.tp3)}`\n"
        f"\n"
        f"📐 *Setup:* {sig.signal_type}\n"
        f"⏱  *Timeframe:* {sig.timeframe}  |  RSI: {sig.rsi_m15}\n"
        f"🧭 *HTF Bias:* {_bias_emoji(sig.htf_bias)} {sig.htf_bias}  (H1)\n"
        f"⚖️ *Risk/Reward:* 1 : {sig.risk_reward}\n"
        f"💪 *Strength:* {_strength_bar(sig.strength)}\n"
        f"\n"
        f"📊 *Why this trade:*\n"
        f"{notes_text}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ *Act within 1–2 minutes* — signal is forming NOW\n"
        f"_Midas Markets · AI Signal Monitor_"
    )
    return msg


def send_telegram(token: str, chat_id: str, message: str, retries: int = 3) -> bool:
    url     = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    for attempt in range(retries):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                log.info("Telegram alert sent successfully.")
                return True
            log.warning("Telegram returned %d: %s", resp.status_code, resp.text[:200])
        except Exception as exc:
            log.warning("Telegram send error (attempt %d): %s", attempt + 1, exc)
        wait = 2 ** attempt
        time.sleep(wait)
    return False


def send_signal_alert(token: str, chat_id: str, sig: Signal) -> bool:
    if not token or not chat_id:
        log.error("Telegram credentials not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_VIP_CHAT_ID")
        return False
    message = build_message(sig)
    return send_telegram(token, chat_id, message)


def send_startup_message(token: str, chat_id: str, pair_count: int) -> None:
    msg = (
        f"🚀 *Midas Signal Monitor — ONLINE*\n"
        f"Watching *{pair_count} pairs* across M1 · M5 · M15 · H1\n"
        f"Strategy: EMA Cross · RSI Reversal · V-Reversal\n"
        f"Signals fire *1–2 minutes early* so you never miss the move.\n"
        f"_Midas Markets · AI Signal Monitor_"
    )
    send_telegram(token, chat_id, msg)
