#!/usr/bin/env python3
"""
Midas Markets — Multi-Timeframe Trading Signal Monitor
======================================================
Watches 20 pairs across M1/M5/M15/H1.
Fires Telegram alerts 1-2 minutes before a signal is fully confirmed
so you can enter early and catch the full move.

Usage:
    python3 main.py

Environment variables required (set in ../.env.local or ../.env):
    TELEGRAM_BOT_TOKEN=<your bot token>
    TELEGRAM_VIP_CHAT_ID=<your chat or group ID>
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

import config as cfg
from data_fetcher import fetch_all_timeframes
from signal_detector import detect_signal
from telegram_notifier import send_signal_alert, send_startup_message

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "monitor.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────
# Tracks when the last alert was sent per pair to avoid spam
last_alerted: dict[str, float] = {}


def is_on_cooldown(symbol: str) -> bool:
    last = last_alerted.get(symbol, 0)
    return (time.time() - last) < cfg.COOLDOWN_SECONDS


def mark_alerted(symbol: str) -> None:
    last_alerted[symbol] = time.time()


# ── Main scan loop ────────────────────────────────────────────────────────────

def scan_once() -> int:
    """Scan all pairs once. Returns number of signals fired."""
    signals_fired = 0
    intervals = [tf[0] for tf in cfg.TIMEFRAMES]

    for (ticker, symbol, full_name, pip_factor) in cfg.PAIRS:
        if is_on_cooldown(symbol):
            log.debug("%-10s  skipped (cooldown)", symbol)
            continue

        log.info("Scanning %-10s  (%s)", symbol, ticker)
        tf_data = fetch_all_timeframes(ticker, intervals)

        if not tf_data:
            log.warning("No data returned for %s", symbol)
            continue

        signal = detect_signal(ticker, symbol, full_name, pip_factor, tf_data)

        if signal is None:
            log.info("  → No signal  (RSI/EMA conditions not met)")
            continue

        log.info(
            "  → SIGNAL  %s  %s  strength=%.0f%%  entry=%s  sl=%s  tp1=%s",
            signal.direction,
            signal.signal_type,
            signal.strength,
            signal.entry,
            signal.stop_loss,
            signal.tp1,
        )

        sent = send_signal_alert(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID, signal)
        if sent:
            mark_alerted(symbol)
            signals_fired += 1
        else:
            log.warning("Failed to send Telegram alert for %s", symbol)

    return signals_fired


def run() -> None:
    log.info("=" * 60)
    log.info("  MIDAS MARKETS — Signal Monitor STARTING")
    log.info("  Pairs: %d | Scan interval: %ds", len(cfg.PAIRS), cfg.SCAN_INTERVAL)
    log.info("  Bot token set: %s", bool(cfg.TELEGRAM_BOT_TOKEN))
    log.info("  Chat ID set:   %s", bool(cfg.TELEGRAM_CHAT_ID))
    log.info("=" * 60)

    send_startup_message(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID, len(cfg.PAIRS))

    scan_count = 0
    while True:
        scan_count += 1
        start = time.time()
        log.info("── SCAN #%d  %s ──", scan_count, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

        try:
            fired = scan_once()
            log.info("── Scan #%d complete  signals_fired=%d  elapsed=%.1fs ──",
                     scan_count, fired, time.time() - start)
        except Exception as exc:
            log.exception("Unhandled error during scan: %s", exc)

        # Wait until the next scan interval, accounting for time already spent
        elapsed = time.time() - start
        sleep_for = max(0, cfg.SCAN_INTERVAL - elapsed)
        log.info("Next scan in %.0fs …\n", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    run()
