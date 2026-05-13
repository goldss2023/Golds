import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_VIP_CHAT_ID", "")

# Top 20 pairs: (yfinance ticker, display name, pip_factor)
PAIRS = [
    ("GC=F",      "XAUUSD",   "Gold vs US Dollar",           0.1),
    ("SI=F",      "XAGUSD",   "Silver vs US Dollar",         0.001),
    ("EURUSD=X",  "EURUSD",   "Euro vs US Dollar",           0.0001),
    ("GBPUSD=X",  "GBPUSD",   "British Pound vs US Dollar",  0.0001),
    ("USDJPY=X",  "USDJPY",   "US Dollar vs Japanese Yen",   0.01),
    ("USDCHF=X",  "USDCHF",   "US Dollar vs Swiss Franc",    0.0001),
    ("AUDUSD=X",  "AUDUSD",   "Australian Dollar vs USD",    0.0001),
    ("NZDUSD=X",  "NZDUSD",   "New Zealand Dollar vs USD",   0.0001),
    ("USDCAD=X",  "USDCAD",   "US Dollar vs Canadian Dollar",0.0001),
    ("GBPJPY=X",  "GBPJPY",   "British Pound vs Japanese Yen",0.01),
    ("EURJPY=X",  "EURJPY",   "Euro vs Japanese Yen",        0.01),
    ("EURGBP=X",  "EURGBP",   "Euro vs British Pound",       0.0001),
    ("AUDJPY=X",  "AUDJPY",   "Australian Dollar vs JPY",    0.01),
    ("EURAUD=X",  "EURAUD",   "Euro vs Australian Dollar",   0.0001),
    ("GBPAUD=X",  "GBPAUD",   "British Pound vs AUD",        0.0001),
    ("^DJI",      "US30",     "Dow Jones 30",                1.0),
    ("^NDX",      "NAS100",   "Nasdaq 100",                  1.0),
    ("^GSPC",     "SPX500",   "S&P 500",                     0.1),
    ("BTC-USD",   "BTCUSD",   "Bitcoin vs US Dollar",        1.0),
    ("ETH-USD",   "ETHUSD",   "Ethereum vs US Dollar",       0.1),
]

# Timeframes: (yfinance interval, label, candle_seconds)
TIMEFRAMES = [
    ("1h",  "H1",  3600),
    ("15m", "M15", 900),
    ("5m",  "M5",  300),
    ("1m",  "M1",  60),
]

# HTF for bias only
HTF_INTERVAL = "1h"

# EMA periods
EMA_FAST   = 21
EMA_SLOW   = 50
EMA_TREND  = 200

# RSI
RSI_PERIOD      = 14
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 70
RSI_PRE_ENTRY   = 35   # pre-signal buy zone (approaching oversold exit)
RSI_PRE_SELL    = 65   # pre-signal sell zone

# Signal cooldown per pair (seconds) - don't alert same pair twice within this window
COOLDOWN_SECONDS = 3600  # 1 hour

# How often to scan all pairs (seconds)
SCAN_INTERVAL = 60

# Minimum signal strength to alert (0-100)
MIN_SIGNAL_STRENGTH = 60

# ATR multiplier for stop-loss
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0
