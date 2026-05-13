"""
Multi-timeframe signal detector.

Strategy (matches the screenshot setup):
  H1  → determine overall bias (trend direction)
  M15 → detect the forming setup (EMA cross, RSI reversal, V-reversal)
  M5  → tighten entry zone
  M1  → fire PRE-SIGNAL alert (1-2 minutes early)

Signal types detected:
  1. EMA_CROSS  – fast EMA crossing slow EMA with trend confirmation
  2. RSI_REVERSAL – RSI exiting oversold/overbought with momentum candle
  3. V_REVERSAL  – sharp spike followed by immediate strong rejection
  4. TREND_PULL  – pullback to EMA_FAST on trending chart, bounce starting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from indicators import add_indicators
import config as cfg

log = logging.getLogger(__name__)

Direction = Literal["BUY", "SELL"]


@dataclass
class Signal:
    ticker:    str
    symbol:    str
    full_name: str
    direction: Direction
    signal_type: str
    strength:  float          # 0-100
    entry:     float
    stop_loss: float
    tp1:       float
    tp2:       float
    tp3:       float
    atr:       float
    htf_bias:  str
    timeframe: str            # where the setup is forming
    rsi_m15:   float
    ema_gap:   float          # EMA fast-slow gap in ATR units
    notes:     list[str] = field(default_factory=list)

    @property
    def risk_reward(self) -> float:
        risk   = abs(self.entry - self.stop_loss)
        reward = abs(self.tp1 - self.entry)
        return round(reward / risk, 2) if risk else 0.0

    @property
    def sl_pct(self) -> float:
        return round(abs(self.entry - self.stop_loss) / self.entry * 100, 2)

    @property
    def tp1_pct(self) -> float:
        return round(abs(self.tp1 - self.entry) / self.entry * 100, 2)


# ──────────────────────────────────────────────
#  Helper utilities
# ──────────────────────────────────────────────

def _last(series: pd.Series, n: int = 1):
    return series.iloc[-n] if len(series) >= n else np.nan


def _htf_bias(df_h1: pd.DataFrame) -> str:
    """Returns 'BULLISH', 'BEARISH', or 'NEUTRAL' from H1 data."""
    df = add_indicators(df_h1, cfg.EMA_FAST, cfg.EMA_SLOW, cfg.EMA_TREND, cfg.RSI_PERIOD)
    close       = _last(df["Close"])
    ema_fast    = _last(df["ema_fast"])
    ema_slow    = _last(df["ema_slow"])
    ema_trend   = _last(df["ema_trend"])
    rsi_val     = _last(df["rsi"])

    bull_points = sum([
        close > ema_fast,
        close > ema_slow,
        close > ema_trend,
        ema_fast > ema_slow,
        rsi_val > 50,
    ])
    bear_points = sum([
        close < ema_fast,
        close < ema_slow,
        close < ema_trend,
        ema_fast < ema_slow,
        rsi_val < 50,
    ])
    if bull_points >= 4:
        return "BULLISH"
    if bear_points >= 4:
        return "BEARISH"
    return "NEUTRAL"


def _v_reversal_score(df: pd.DataFrame, direction: Direction) -> float:
    """
    Detects a V-shaped reversal (like in the screenshot) in the last 10 bars.
    Returns 0-100 score.
    """
    if len(df) < 10:
        return 0.0

    closes = df["Close"].values[-10:]
    highs  = df["High"].values[-10:]
    lows   = df["Low"].values[-10:]
    atrs   = df["atr"].values[-10:]
    avg_atr = np.nanmean(atrs)
    if avg_atr == 0:
        return 0.0

    if direction == "BUY":
        # Find the low of the recent window
        low_idx  = int(np.argmin(lows))
        if low_idx < 2 or low_idx > 7:        # spike must be in middle of window
            return 0.0
        drop    = closes[0] - lows[low_idx]   # how far price fell
        recovery = closes[-1] - lows[low_idx] # how much it recovered
        if drop < avg_atr * 1.5:              # spike must be significant
            return 0.0
        ratio   = recovery / drop             # 1.0 = full recovery
        score   = min(ratio * 80, 80)

        # Bonus: strong rejection candle at low (long lower wick)
        wick = lows[low_idx - 1:low_idx + 2]
        candle_body = abs(df["Close"].values[-10:][low_idx] - df["Open"].values[-10:][low_idx])
        lower_wick  = df["Open"].values[-10:][low_idx] - lows[low_idx]
        if candle_body > 0 and lower_wick / candle_body > 1.5:
            score += 20
        return min(score, 100)

    else:  # SELL
        high_idx = int(np.argmax(highs))
        if high_idx < 2 or high_idx > 7:
            return 0.0
        spike    = highs[high_idx] - closes[0]
        reversal = highs[high_idx] - closes[-1]
        if spike < avg_atr * 1.5:
            return 0.0
        ratio  = reversal / spike
        score  = min(ratio * 80, 80)
        upper_wick = highs[high_idx] - df["Open"].values[-10:][high_idx]
        candle_body = abs(df["Close"].values[-10:][high_idx] - df["Open"].values[-10:][high_idx])
        if candle_body > 0 and upper_wick / candle_body > 1.5:
            score += 20
        return min(score, 100)


# ──────────────────────────────────────────────
#  Core detection
# ──────────────────────────────────────────────

def detect_signal(
    ticker: str,
    symbol: str,
    full_name: str,
    pip_factor: float,
    timeframe_data: dict[str, pd.DataFrame],
) -> Signal | None:
    """
    Analyses multi-timeframe data and returns a Signal if conditions are met,
    or None otherwise.
    """
    # Need at least M15 data
    df_m15 = timeframe_data.get("15m")
    df_m5  = timeframe_data.get("5m")
    df_m1  = timeframe_data.get("1m")
    df_h1  = timeframe_data.get("1h")

    if df_m15 is None or len(df_m15) < 60:
        return None

    # Add indicators to available timeframes
    df_m15 = add_indicators(df_m15, cfg.EMA_FAST, cfg.EMA_SLOW, cfg.EMA_TREND, cfg.RSI_PERIOD)
    if df_m5 is not None and len(df_m5) >= 30:
        df_m5 = add_indicators(df_m5, cfg.EMA_FAST, cfg.EMA_SLOW, cfg.EMA_TREND, cfg.RSI_PERIOD)
    if df_m1 is not None and len(df_m1) >= 30:
        df_m1 = add_indicators(df_m1, cfg.EMA_FAST, cfg.EMA_SLOW, cfg.EMA_TREND, cfg.RSI_PERIOD)

    # HTF bias
    htf_bias = _htf_bias(df_h1) if df_h1 is not None and len(df_h1) >= 50 else "NEUTRAL"

    # Current M15 values
    price    = float(_last(df_m15["Close"]))
    rsi_val  = float(_last(df_m15["rsi"]))
    ema_fast = float(_last(df_m15["ema_fast"]))
    ema_slow = float(_last(df_m15["ema_slow"]))
    atr_val  = float(_last(df_m15["atr"]))
    ema_gap  = float(_last(df_m15["ema_gap"]))
    macd_h   = float(_last(df_m15["macd_hist"]))

    if atr_val == 0 or np.isnan(atr_val):
        return None

    # Previous bar values (for crossover detection)
    rsi_prev     = float(_last(df_m15["rsi"], 2))
    ema_gap_prev = float(_last(df_m15["ema_gap"], 2))
    macd_h_prev  = float(_last(df_m15["macd_hist"], 2))

    signals_found: list[tuple[Direction, str, float, list[str]]] = []

    # ── BUY signal detection ──────────────────────────────────────────────

    buy_notes: list[str] = []
    buy_score = 0.0

    # 1. RSI oversold exit (RSI crossed above RSI_OVERSOLD from below)
    rsi_buy_exit = rsi_prev < cfg.RSI_OVERSOLD and rsi_val > cfg.RSI_OVERSOLD
    rsi_pre_exit = cfg.RSI_OVERSOLD <= rsi_val <= cfg.RSI_PRE_ENTRY  # just exited oversold

    if rsi_buy_exit:
        buy_score += 30
        buy_notes.append("RSI exited oversold")
    elif rsi_pre_exit:
        buy_score += 15
        buy_notes.append("RSI near oversold exit")
    elif rsi_val < cfg.RSI_PRE_ENTRY:
        buy_score += 10
        buy_notes.append("RSI in oversold zone")

    # 2. EMA fast crossing above slow (or about to)
    ema_cross_buy = ema_gap_prev < 0 and ema_gap > 0
    ema_pre_cross_buy = -0.3 < ema_gap < 0.1  # converging, about to cross

    if ema_cross_buy:
        buy_score += 30
        buy_notes.append("EMA bullish crossover")
    elif ema_pre_cross_buy:
        buy_score += 15
        buy_notes.append("EMA converging (about to cross up)")

    # 3. MACD histogram turning positive
    if macd_h_prev < 0 and macd_h > 0:
        buy_score += 15
        buy_notes.append("MACD histogram turned positive")
    elif macd_h_prev < macd_h < 0:
        buy_score += 8
        buy_notes.append("MACD momentum building")

    # 4. HTF alignment
    if htf_bias == "BULLISH":
        buy_score += 15
        buy_notes.append("H1 trend is bullish")
    elif htf_bias == "NEUTRAL":
        buy_score += 5

    # 5. V-reversal pattern
    v_score = _v_reversal_score(df_m15, "BUY")
    if v_score > 50:
        buy_score += v_score * 0.15
        buy_notes.append(f"V-reversal pattern ({v_score:.0f}%)")

    # 6. Price below EMA trend (potential mean reversion setup)
    if price < ema_fast * 0.999:
        buy_score += 5
        buy_notes.append("Price below fast EMA (pullback)")

    # 7. M1 confirmation (faster timeframe agrees)
    if df_m1 is not None:
        rsi_m1 = float(_last(df_m1["rsi"]))
        if rsi_m1 > 50:
            buy_score += 5
            buy_notes.append("M1 RSI above 50")

    if buy_score >= cfg.MIN_SIGNAL_STRENGTH:
        signals_found.append(("BUY", _classify_signal(buy_notes), buy_score, buy_notes))

    # ── SELL signal detection ─────────────────────────────────────────────

    sell_notes: list[str] = []
    sell_score = 0.0

    rsi_sell_exit = rsi_prev > cfg.RSI_OVERBOUGHT and rsi_val < cfg.RSI_OVERBOUGHT
    rsi_pre_sell  = cfg.RSI_PRE_SELL <= rsi_val <= cfg.RSI_OVERBOUGHT

    if rsi_sell_exit:
        sell_score += 30
        sell_notes.append("RSI exited overbought")
    elif rsi_pre_sell:
        sell_score += 15
        sell_notes.append("RSI near overbought exit")
    elif rsi_val > cfg.RSI_PRE_SELL:
        sell_score += 10
        sell_notes.append("RSI in overbought zone")

    ema_cross_sell     = ema_gap_prev > 0 and ema_gap < 0
    ema_pre_cross_sell = -0.1 < ema_gap < 0.3

    if ema_cross_sell:
        sell_score += 30
        sell_notes.append("EMA bearish crossover")
    elif ema_pre_cross_sell:
        sell_score += 15
        sell_notes.append("EMA converging (about to cross down)")

    if macd_h_prev > 0 and macd_h < 0:
        sell_score += 15
        sell_notes.append("MACD histogram turned negative")
    elif macd_h_prev > macd_h > 0:
        sell_score += 8
        sell_notes.append("MACD momentum fading")

    if htf_bias == "BEARISH":
        sell_score += 15
        sell_notes.append("H1 trend is bearish")
    elif htf_bias == "NEUTRAL":
        sell_score += 5

    v_score_sell = _v_reversal_score(df_m15, "SELL")
    if v_score_sell > 50:
        sell_score += v_score_sell * 0.15
        sell_notes.append(f"Spike-reversal pattern ({v_score_sell:.0f}%)")

    if price > ema_fast * 1.001:
        sell_score += 5
        sell_notes.append("Price above fast EMA (extended)")

    if df_m1 is not None:
        rsi_m1 = float(_last(df_m1["rsi"]))
        if rsi_m1 < 50:
            sell_score += 5
            sell_notes.append("M1 RSI below 50")

    if sell_score >= cfg.MIN_SIGNAL_STRENGTH:
        signals_found.append(("SELL", _classify_signal(sell_notes), sell_score, sell_notes))

    if not signals_found:
        return None

    # Pick the strongest signal
    direction, sig_type, strength, notes = max(signals_found, key=lambda x: x[2])
    strength = min(strength, 100.0)

    # ── Entry, SL, TP levels ──────────────────────────────────────────────
    sl_dist  = atr_val * cfg.ATR_SL_MULT
    tp1_dist = atr_val * cfg.ATR_TP_MULT
    tp2_dist = atr_val * cfg.ATR_TP_MULT * 1.8
    tp3_dist = atr_val * cfg.ATR_TP_MULT * 3.0

    # Use M5 for tighter entry if available
    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_price = float(_last(entry_df["Close"]))

    if direction == "BUY":
        stop_loss = entry_price - sl_dist
        tp1       = entry_price + tp1_dist
        tp2       = entry_price + tp2_dist
        tp3       = entry_price + tp3_dist
    else:
        stop_loss = entry_price + sl_dist
        tp1       = entry_price - tp1_dist
        tp2       = entry_price - tp2_dist
        tp3       = entry_price - tp3_dist

    return Signal(
        ticker      = ticker,
        symbol      = symbol,
        full_name   = full_name,
        direction   = direction,
        signal_type = sig_type,
        strength    = round(strength, 1),
        entry       = round(entry_price, _price_decimals(entry_price)),
        stop_loss   = round(stop_loss, _price_decimals(stop_loss)),
        tp1         = round(tp1, _price_decimals(tp1)),
        tp2         = round(tp2, _price_decimals(tp2)),
        tp3         = round(tp3, _price_decimals(tp3)),
        atr         = round(atr_val, _price_decimals(atr_val)),
        htf_bias    = htf_bias,
        timeframe   = "M15",
        rsi_m15     = round(rsi_val, 1),
        ema_gap     = round(ema_gap, 3),
        notes       = notes,
    )


def _classify_signal(notes: list[str]) -> str:
    if any("V-reversal" in n or "Spike-reversal" in n for n in notes):
        return "V-Reversal"
    if any("crossover" in n for n in notes):
        return "EMA Crossover"
    if any("exited" in n for n in notes):
        return "RSI Reversal"
    if any("converging" in n for n in notes):
        return "EMA Pre-Cross"
    return "Momentum Setup"


def _price_decimals(price: float) -> int:
    if price > 1000:
        return 1
    if price > 10:
        return 2
    if price > 1:
        return 4
    return 5
