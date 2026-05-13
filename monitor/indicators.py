import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema   = ema(series, fast)
    slow_ema   = ema(series, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def swing_low(series: pd.Series, lookback: int = 5) -> pd.Series:
    """Returns True at bars that are a local swing low."""
    result = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i - lookback: i + lookback + 1]
        if series.iloc[i] == window.min():
            result.iloc[i] = True
    return result


def swing_high(series: pd.Series, lookback: int = 5) -> pd.Series:
    result = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i - lookback: i + lookback + 1]
        if series.iloc[i] == window.max():
            result.iloc[i] = True
    return result


def add_indicators(df: pd.DataFrame, ema_fast: int, ema_slow: int, ema_trend: int, rsi_period: int) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    df["ema_fast"]  = ema(close, ema_fast)
    df["ema_slow"]  = ema(close, ema_slow)
    df["ema_trend"] = ema(close, ema_trend)
    df["rsi"]       = rsi(close, rsi_period)
    df["atr"]       = atr(df)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(close)
    df["ema_gap"]   = (df["ema_fast"] - df["ema_slow"]) / df["atr"]  # normalised gap
    return df
