import time
import logging
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# How many bars to pull per timeframe (enough for EMA-200 + recent action)
BARS_NEEDED = {
    "1m":  300,
    "5m":  300,
    "15m": 300,
    "1h":  300,
    "4h":  200,
    "1d":  200,
}

PERIOD_MAP = {
    "1m":  "1d",
    "5m":  "5d",
    "15m": "60d",
    "1h":  "180d",
    "4h":  "360d",
    "1d":  "2y",
}


def fetch_ohlcv(ticker: str, interval: str, retries: int = 3) -> pd.DataFrame | None:
    period = PERIOD_MAP.get(interval, "60d")
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker,
                period=interval_to_period(interval),
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if df is None or df.empty:
                log.warning("Empty data for %s %s", ticker, interval)
                return None
            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            return df
        except Exception as exc:
            wait = 2 ** attempt
            log.warning("Fetch error %s %s (attempt %d): %s. Retrying in %ds", ticker, interval, attempt + 1, exc, wait)
            time.sleep(wait)
    return None


def interval_to_period(interval: str) -> str:
    mapping = {
        "1m":  "1d",
        "2m":  "5d",
        "5m":  "5d",
        "15m": "60d",
        "30m": "60d",
        "1h":  "730d",
        "4h":  "730d",
        "1d":  "5y",
    }
    return mapping.get(interval, "60d")


def fetch_all_timeframes(ticker: str, intervals: list[str]) -> dict[str, pd.DataFrame]:
    result = {}
    for interval in intervals:
        df = fetch_ohlcv(ticker, interval)
        if df is not None and len(df) >= 50:
            result[interval] = df
    return result
