#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════
#  HIGH-FREQUENCY PAPER TRADING ARBITRAGE BOT
#  Sources : Jupiter · Binance · Kraken · OKX · Bybit ·
#            Pyth · DeFiLlama · CoinGecko · The Graph
#  Types   : DEX_CEX · ORACLE · YIELD · CEX_CEX · GECKO_ARB
#  Target  : 500,000+ paper detections / day
#  Paper trading only — no real trades, no wallet, no API keys
# ═══════════════════════════════════════════════════════════════════════════

# ── AUTO-INSTALL ─────────────────────────────────────────────────────────────
import subprocess, sys

def _pip(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", pkg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

for _p in ["aiohttp", "websockets", "rich"]:
    try:
        __import__(_p)
    except ImportError:
        print(f"Installing {_p}…", flush=True)
        _pip(_p)

# ── STDLIB ───────────────────────────────────────────────────────────────────
import asyncio
import json
import csv
import os
import time
import signal
import math
from datetime import datetime
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

# ── THIRD-PARTY ───────────────────────────────────────────────────────────────
import aiohttp
import websockets
from rich.console import Console
from rich.live import Live
from rich.text import Text


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════

TOKENS = [
    "SOL","BTC","ETH","BONK","JTO","WIF","PYTH","JUP","RAY","ORCA",
    "MEME","POPCAT","WEN","SAMO","BOME","MYRO","SLERF","ZEUS",
    "SHARK","GUAC","BERN","AURY","STEP","COPE",
]

JUPITER_IDS: Dict[str, str] = {
    "SOL":    "So11111111111111111111111111111111111111112",
    "BTC":    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",
    "ETH":    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
    "BONK":   "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JTO":    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "WIF":    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "PYTH":   "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "JUP":    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY":    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA":   "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "MEME":   "MEMEcZDPEJGpyYGEFnEXAUksFZzF7B4aBkVaRFg6b3o",
    "POPCAT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "WEN":    "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk",
    "SAMO":   "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    "BOME":   "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",
    "MYRO":   "HhJpBhRRn4g56VsyLuT8DL5Bv31HkXqsrahTTUCZeZg4",
    "SLERF":  "7BgBvyjrZX1YKz4oh9mjb8ZScatkkwb8DzFx7LoiVkM3",
    "ZEUS":   "ZEUS1aR7aX8DFFkykstARCPpGmHZFaKZsGSzDHFHD5T",
    "SHARK":  "SHARKSYJjqaNyxVfrpnBN1pLROYyerFVRn4VE4jMcCS",
    "GUAC":   "AZsHEMXd36Bj1EMNXhowJajpUXzrKcK57wW4ZGXVa7yR",
    "BERN":   "CKfatsPMUf8SkiURsDXs7eK6GWb4Jsd6UDbs7twMCWxo",
    "AURY":   "AURYydfxJib1ZkTir1Jn1J9ECYUtjb6rKQVmtYaixWPP",
    "STEP":   "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT",
    "COPE":   "8HGyAAB1yoM1ttS7pXjHMa3dukTFGQggnFFH3hJZgzQh",
}

BINANCE_SYMBOLS: Dict[str, str] = {
    "SOL":"SOLUSDT","BTC":"BTCUSDT","ETH":"ETHUSDT","BONK":"BONKUSDT",
    "JTO":"JTOUSDT","WIF":"WIFUSDT","PYTH":"PYTHUSDT","JUP":"JUPUSDT",
    "RAY":"RAYUSDT","ORCA":"ORCAUSDT","MEME":"MEMEUSDT","POPCAT":"POPCATUSDT",
    "WEN":"WENUSDT","SAMO":"SAMOUSDT","BOME":"BOMEUSDT","MYRO":"MYROUSDT",
    "SLERF":"SLERFUSDT","ZEUS":"ZEUSUSDT",
}

KRAKEN_SYMBOLS: Dict[str, str] = {
    "BTC":"XBT/USD","ETH":"ETH/USD","SOL":"SOL/USD",
    "ORCA":"ORCA/USD","RAY":"RAY/USD",
}
KRAKEN_REVERSE: Dict[str, str] = {v: k for k, v in KRAKEN_SYMBOLS.items()}

OKX_SYMBOLS: Dict[str, str] = {
    "BTC":"BTC-USDT","ETH":"ETH-USDT","SOL":"SOL-USDT",
    "BONK":"BONK-USDT","JTO":"JTO-USDT","WIF":"WIF-USDT",
    "PYTH":"PYTH-USDT","JUP":"JUP-USDT","RAY":"RAY-USDT",
}
OKX_REVERSE: Dict[str, str] = {v: k for k, v in OKX_SYMBOLS.items()}

BYBIT_SYMBOLS: Dict[str, str] = {
    "BTC":"BTCUSDT","ETH":"ETHUSDT","SOL":"SOLUSDT",
    "BONK":"BONKUSDT","JTO":"JTOUSDT","WIF":"WIFUSDT",
    "PYTH":"PYTHUSDT","JUP":"JUPUSDT",
}
BYBIT_REVERSE: Dict[str, str] = {v: k for k, v in BYBIT_SYMBOLS.items()}

PYTH_IDS: Dict[str, str] = {
    "SOL":  "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "BTC":  "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH":  "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "BONK": "72b021217ca3fe68922a19aaf990109cb9d84e9ad004b4d2025ad6f529314419",
    "JTO":  "b43660a5f790c69354b0729a5ef9d50d68f1df92107540210b9cccba1f947cc2",
    "WIF":  "4ca4beeca86f0d164160323817a4e42b10010a724c2217c6ee41b54cd4cc61fc",
    "PYTH": "0bbf28e9a841a1cc788f6a361b17ca072d0ea3098a1e5df1c3922d06719579ff",
    "JUP":  "0a0408d619e9380abad35060f9192039ed5042fa6f82301d0e48bb52be830996",
    "RAY":  "91568baa8beb53db23eb3fb7f22c6e8bd303d103919e19733f2bb642d3e7987a",
}
PYTH_REVERSE: Dict[str, str] = {v: k for k, v in PYTH_IDS.items()}

COINGECKO_IDS: Dict[str, str] = {
    "SOL":"solana","BTC":"bitcoin","ETH":"ethereum","BONK":"bonk",
    "JTO":"jito-governance-token","WIF":"dogwifcoin","PYTH":"pyth-network",
    "JUP":"jupiter-exchange-solana","RAY":"raydium","ORCA":"orca",
    "MEME":"memecoin-2","WEN":"wen-4","SAMO":"samoyedcoin",
}

# Thresholds (%)
THRESHOLDS: Dict[str, float] = {
    "DEX_CEX":  0.25,
    "ORACLE":   0.30,
    "CEX_CEX":  0.15,
    "GECKO_ARB":0.20,
}
YIELD_APY_MIN   = 2.0      # % APY floor for DeFiLlama pools
DEDUP_SECONDS   = 2.0      # cooldown per (token, src_a, src_b)
DEDUP_CLEAN_INT = 30       # seconds between dedup dict cleanup
TRADE_GBP       = 50.0
FLASH_MULT      = 10
FEE_BOTH_LEGS   = 0.002    # 0.1% × 2

# Poll intervals
JUPITER_INT   = 4
PYTH_INT      = 8
LLAMA_INT     = 45
GECKO_INT     = 30
GRAPH_INT     = 15
DASH_INT      = 2

CSV_ROTATE_MB = 100
CSV_BASE      = "arb_opportunities"

ALL_SOURCES = [
    "Jupiter","Binance","Kraken","OKX","Bybit","Pyth","CoinGecko","TheGraph",
]


# ═══════════════════════════════════════════════════════════════════════════
#  STATE
# ═══════════════════════════════════════════════════════════════════════════

class BotState:
    def __init__(self):
        # prices[source][token] = USD price (positive float)
        self.prices: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.lock = asyncio.Lock()

        # opportunity history
        self.opp_60s: deque  = deque()          # (ts, Opportunity)
        self.recent_5: deque = deque(maxlen=5)

        # running totals
        self.total_base  = 0.0
        self.total_flash = 0.0
        self.best        = 0.0
        self.worst       = math.inf
        self.total_count = 0
        self.type_counts: Dict[str, int] = defaultdict(int)

        # trade rate
        self.tps_window: deque = deque(maxlen=60)  # (ts, count) per second
        self.last_tps_ts   = time.time()
        self.last_tps_cnt  = 0

        # dedup: (token, src_a, src_b) → last triggered time
        self.dedup: Dict[Tuple[str,str,str], float] = {}
        self.last_dedup_clean = time.time()

        # source health
        self.health: Dict[str, str]  = {s: "…" for s in ALL_SOURCES}
        self.lag:    Dict[str, float] = {s: 0.0  for s in ALL_SOURCES}

        # misc
        self.pools_active = 0
        self.running      = True
        self.start_time   = time.time()
        self.status       = "Starting…"

        # CSV state
        self.csv_index    = 0
        self.csv_bytes    = 0
        self.csv_queue: asyncio.Queue = asyncio.Queue()


@dataclass
class Opportunity:
    timestamp:        str
    token:            str
    source_a:         str
    source_b:         str
    price_a:          float
    price_b:          float
    gap_pct:          float
    profit_base_gbp:  float
    profit_flash_gbp: float
    opp_type:         str


# ═══════════════════════════════════════════════════════════════════════════
#  CSV — async queue writer, auto-rotation at 100 MB
# ═══════════════════════════════════════════════════════════════════════════

CSV_HEADER = [
    "timestamp","token","source_a","source_b",
    "price_a_usd","price_b_usd","gap_pct",
    "profit_base_gbp","profit_flash_gbp","type",
]

def _csv_path(index: int) -> str:
    return f"{CSV_BASE}.csv" if index == 0 else f"{CSV_BASE}_{index}.csv"

def _init_csv(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADER)

async def csv_writer_loop(state: BotState):
    """Drains the CSV queue; rotates file when it exceeds CSV_ROTATE_MB."""
    path = _csv_path(state.csv_index)
    _init_csv(path)
    while state.running or not state.csv_queue.empty():
        try:
            opp: Opportunity = await asyncio.wait_for(state.csv_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        row = [
            opp.timestamp, opp.token, opp.source_a, opp.source_b,
            f"{opp.price_a:.8f}", f"{opp.price_b:.8f}",
            f"{opp.gap_pct:.4f}", f"{opp.profit_base_gbp:.4f}",
            f"{opp.profit_flash_gbp:.4f}", opp.opp_type,
        ]
        await asyncio.to_thread(_append_csv_row, path, row)
        line_bytes = sum(len(str(c)) for c in row) + 12
        state.csv_bytes += line_bytes
        if state.csv_bytes >= CSV_ROTATE_MB * 1024 * 1024:
            state.csv_index += 1
            state.csv_bytes  = 0
            path = _csv_path(state.csv_index)
            _init_csv(path)

def _append_csv_row(path: str, row: list):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow(row)


# ═══════════════════════════════════════════════════════════════════════════
#  OPPORTUNITY DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _safe_gap_pct(price_a: float, price_b: float) -> Optional[float]:
    """Returns gap % or None if prices are invalid."""
    if (
        not math.isfinite(price_a) or not math.isfinite(price_b)
        or price_a <= 0 or price_b <= 0
    ):
        return None
    denom = min(price_a, price_b)
    if denom == 0:
        return None
    return abs(price_a - price_b) / denom * 100.0

def _profit(gap_pct: float) -> Tuple[float, float]:
    net = gap_pct / 100.0 - FEE_BOTH_LEGS
    if net <= 0:
        return 0.0, 0.0
    return TRADE_GBP * net, TRADE_GBP * FLASH_MULT * net

async def _record(
    state: BotState,
    token: str,
    src_a: str,
    src_b: str,
    price_a: float,
    price_b: float,
    opp_type: str,
    threshold: float,
):
    gap = _safe_gap_pct(price_a, price_b)
    if gap is None or gap < threshold:
        return

    profit_base, profit_flash = _profit(gap)
    if profit_base <= 0:
        return

    # dedup check
    now = time.time()
    key = (token, src_a, src_b)
    async with state.lock:
        last = state.dedup.get(key, 0.0)
        if now - last < DEDUP_SECONDS:
            return
        state.dedup[key] = now

        # clean stale dedup entries periodically
        if now - state.last_dedup_clean > DEDUP_CLEAN_INT:
            cutoff = now - DEDUP_SECONDS * 10
            state.dedup = {k: v for k, v in state.dedup.items() if v > cutoff}
            state.last_dedup_clean = now

    opp = Opportunity(
        timestamp        = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        token            = token,
        source_a         = src_a,
        source_b         = src_b,
        price_a          = price_a,
        price_b          = price_b,
        gap_pct          = gap,
        profit_base_gbp  = profit_base,
        profit_flash_gbp = profit_flash,
        opp_type         = opp_type,
    )

    async with state.lock:
        state.opp_60s.append((now, opp))
        state.recent_5.append(opp)
        state.total_base  += profit_base
        state.total_flash += profit_flash
        state.total_count += 1
        state.type_counts[opp_type] += 1
        if profit_base > state.best:
            state.best = profit_base
        if profit_base < state.worst:
            state.worst = profit_base

    await state.csv_queue.put(opp)

async def _record_yield(
    state: BotState,
    token: str,
    project: str,
    chain: str,
    apy: float,
):
    """Separate handler for DeFiLlama yield opportunities."""
    if not math.isfinite(apy) or apy < YIELD_APY_MIN:
        return

    # Daily profit estimate: £50 × (APY%/100/365)
    profit_base  = TRADE_GBP * (apy / 100.0 / 365.0)
    profit_flash = profit_base * FLASH_MULT
    if profit_base <= 0:
        return

    now = time.time()
    key = (token, "DeFiLlama", chain)
    async with state.lock:
        last = state.dedup.get(key, 0.0)
        if now - last < DEDUP_SECONDS:
            return
        state.dedup[key] = now

    opp = Opportunity(
        timestamp        = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        token            = f"{token}@{project}",
        source_a         = "DeFiLlama",
        source_b         = chain,
        price_a          = apy,
        price_b          = 0.0,
        gap_pct          = apy,
        profit_base_gbp  = profit_base,
        profit_flash_gbp = profit_flash,
        opp_type         = "YIELD",
    )

    async with state.lock:
        state.opp_60s.append((now, opp))
        state.recent_5.append(opp)
        state.total_base  += profit_base
        state.total_flash += profit_flash
        state.total_count += 1
        state.type_counts["YIELD"] += 1
        if profit_base > state.best:
            state.best = profit_base
        if profit_base < state.worst:
            state.worst = profit_base

    await state.csv_queue.put(opp)

def _purge_60s(state: BotState):
    cutoff = time.time() - 60
    while state.opp_60s and state.opp_60s[0][0] < cutoff:
        state.opp_60s.popleft()


# ═══════════════════════════════════════════════════════════════════════════
#  COMPARISON ENGINE — tight loop, yields every cycle
# ═══════════════════════════════════════════════════════════════════════════

SOURCE_PAIRS = [
    ("Jupiter","Binance","DEX_CEX"),  ("Jupiter","Kraken","DEX_CEX"),
    ("Jupiter","OKX","DEX_CEX"),      ("Jupiter","Bybit","DEX_CEX"),
    ("Jupiter","CoinGecko","DEX_CEX"),("Jupiter","TheGraph","DEX_CEX"),
    ("Binance","Kraken","CEX_CEX"),   ("Binance","OKX","CEX_CEX"),
    ("Binance","Bybit","CEX_CEX"),    ("Kraken","OKX","CEX_CEX"),
    ("Kraken","Bybit","CEX_CEX"),     ("OKX","Bybit","CEX_CEX"),
    ("Jupiter","Pyth","ORACLE"),      ("Binance","Pyth","ORACLE"),
    ("CoinGecko","Binance","GECKO_ARB"),
    ("CoinGecko","Kraken","GECKO_ARB"),
]

async def comparison_loop(state: BotState):
    while state.running:
        async with state.lock:
            snap = {src: dict(prices) for src, prices in state.prices.items()}

        tasks = []
        for src_a, src_b, opp_type in SOURCE_PAIRS:
            pa = snap.get(src_a, {})
            pb = snap.get(src_b, {})
            threshold = THRESHOLDS.get(opp_type, 0.25)
            for tok in TOKENS:
                a = pa.get(tok)
                b = pb.get(tok)
                if a and b:
                    tasks.append(_record(state, tok, src_a, src_b, a, b, opp_type, threshold))

        if tasks:
            await asyncio.gather(*tasks)

        await asyncio.sleep(0)   # yield — never block the loop


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 1 — JUPITER (REST, every 4 s)
# ═══════════════════════════════════════════════════════════════════════════

async def jupiter_loop(session: aiohttp.ClientSession, state: BotState):
    ids = ",".join(JUPITER_IDS.values())
    url = f"https://price.jup.ag/v4/price?ids={ids}"
    while state.running:
        t0 = time.time()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = (await r.json(content_type=None)).get("data", {})
                    async with state.lock:
                        for tok, mint in JUPITER_IDS.items():
                            entry = data.get(mint)
                            if entry:
                                p = float(entry.get("price", 0))
                                if p > 0:
                                    state.prices["Jupiter"][tok] = p
                    state.health["Jupiter"] = "✓"
                    state.lag["Jupiter"]    = (time.time() - t0) * 1000
                else:
                    state.health["Jupiter"] = f"HTTP {r.status}"
        except Exception as e:
            state.health["Jupiter"] = type(e).__name__[:12]
        await asyncio.sleep(JUPITER_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 2 — BINANCE (WebSocket, real-time)
# ═══════════════════════════════════════════════════════════════════════════

async def binance_loop(state: BotState):
    streams = "/".join(v.lower() + "@miniTicker" for v in BINANCE_SYMBOLS.values())
    uri     = f"wss://stream.binance.com:9443/stream?streams={streams}"
    delay   = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                delay = 2
                state.health["Binance"] = "✓ streaming"
                async for raw in ws:
                    if not state.running:
                        break
                    try:
                        ticker = json.loads(raw).get("data", {})
                        sym    = ticker.get("s", "")
                        price  = ticker.get("c")
                        if price:
                            for tok, bsym in BINANCE_SYMBOLS.items():
                                if bsym == sym:
                                    p = float(price)
                                    if p > 0:
                                        async with state.lock:
                                            state.prices["Binance"][tok] = p
                                    break
                    except Exception:
                        pass
        except Exception as e:
            if not state.running:
                break
            state.health["Binance"] = f"retry {delay}s"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 3 — KRAKEN (WebSocket, real-time)
# ═══════════════════════════════════════════════════════════════════════════

async def kraken_loop(state: BotState):
    uri   = "wss://ws.kraken.com"
    pairs = list(KRAKEN_SYMBOLS.values())
    sub   = json.dumps({"event":"subscribe","pair":pairs,"subscription":{"name":"ticker"}})
    delay = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(sub)
                delay = 2
                state.health["Kraken"] = "✓ streaming"
                async for raw in ws:
                    if not state.running:
                        break
                    try:
                        msg = json.loads(raw)
                        # Kraken ticker: [channelID, {data}, "ticker", "XBT/USD"]
                        if isinstance(msg, list) and len(msg) == 4 and msg[2] == "ticker":
                            pair  = msg[3]
                            tok   = KRAKEN_REVERSE.get(pair)
                            price_str = msg[1].get("c", [None])[0]
                            if tok and price_str:
                                p = float(price_str)
                                if p > 0:
                                    async with state.lock:
                                        state.prices["Kraken"][tok] = p
                    except Exception:
                        pass
        except Exception as e:
            if not state.running:
                break
            state.health["Kraken"] = f"retry {delay}s"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 4 — OKX (WebSocket, real-time)
# ═══════════════════════════════════════════════════════════════════════════

async def okx_loop(state: BotState):
    uri  = "wss://ws.okx.com:8443/ws/v5/public"
    args = [{"channel": "tickers", "instId": inst} for inst in OKX_SYMBOLS.values()]
    sub  = json.dumps({"op": "subscribe", "args": args})
    delay = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(sub)
                delay = 2
                state.health["OKX"] = "✓ streaming"
                async for raw in ws:
                    if not state.running:
                        break
                    try:
                        msg  = json.loads(raw)
                        data = msg.get("data", [])
                        for item in data:
                            inst_id = item.get("instId", "")
                            tok     = OKX_REVERSE.get(inst_id)
                            last    = item.get("last")
                            if tok and last:
                                p = float(last)
                                if p > 0:
                                    async with state.lock:
                                        state.prices["OKX"][tok] = p
                    except Exception:
                        pass
        except Exception as e:
            if not state.running:
                break
            state.health["OKX"] = f"retry {delay}s"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 5 — BYBIT (WebSocket, real-time)
# ═══════════════════════════════════════════════════════════════════════════

async def bybit_loop(state: BotState):
    uri  = "wss://stream.bybit.com/v5/public/spot"
    args = [f"tickers.{sym}" for sym in BYBIT_SYMBOLS.values()]
    sub  = json.dumps({"op": "subscribe", "args": args})
    delay = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(sub)
                delay = 2
                state.health["Bybit"] = "✓ streaming"
                async for raw in ws:
                    if not state.running:
                        break
                    try:
                        msg   = json.loads(raw)
                        topic = msg.get("topic", "")
                        data  = msg.get("data", {})
                        if topic.startswith("tickers."):
                            sym = topic.split("tickers.")[1]
                            tok = BYBIT_REVERSE.get(sym)
                            if tok:
                                last = data.get("lastPrice")
                                if last:
                                    p = float(last)
                                    if p > 0:
                                        async with state.lock:
                                            state.prices["Bybit"][tok] = p
                    except Exception:
                        pass
        except Exception as e:
            if not state.running:
                break
            state.health["Bybit"] = f"retry {delay}s"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 6 — PYTH NETWORK (REST, every 8 s)
# ═══════════════════════════════════════════════════════════════════════════

async def pyth_loop(session: aiohttp.ClientSession, state: BotState):
    params = "&".join(f"ids[]={v}" for v in PYTH_IDS.values())
    url    = f"https://hermes.pyth.network/api/latest_price_feeds?{params}"
    while state.running:
        t0 = time.time()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status == 200:
                    feeds = await r.json(content_type=None)
                    async with state.lock:
                        for feed in feeds:
                            fid  = feed.get("id", "")
                            tok  = PYTH_REVERSE.get(fid)
                            if not tok:
                                continue
                            pd   = feed.get("price", {})
                            raw  = pd.get("price")
                            expo = pd.get("expo", 0)
                            if raw is not None:
                                p = float(raw) * (10 ** expo)
                                if p > 0:
                                    state.prices["Pyth"][tok] = p
                    state.health["Pyth"] = "✓"
                    state.lag["Pyth"]    = (time.time() - t0) * 1000
                else:
                    state.health["Pyth"] = f"HTTP {r.status}"
        except Exception as e:
            state.health["Pyth"] = type(e).__name__[:12]
        await asyncio.sleep(PYTH_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 7 — DEFILLAMA (REST, every 45 s, ALL pools, batched)
# ═══════════════════════════════════════════════════════════════════════════

BATCH_SIZE = 500

async def _process_pool_batch(state: BotState, batch: list):
    for pool in batch:
        try:
            apy = pool.get("apy")
            if apy is None:
                continue
            apy = float(apy)
            if not math.isfinite(apy) or apy < YIELD_APY_MIN:
                continue
            sym     = str(pool.get("symbol", "")).split("-")[0][:10]
            project = str(pool.get("project", ""))[:12]
            chain   = str(pool.get("chain", "chain"))[:12]
            await _record_yield(state, sym, project, chain, apy)
        except Exception:
            continue
        await asyncio.sleep(0)

async def defillama_loop(session: aiohttp.ClientSession, state: BotState):
    while state.running:
        t0 = time.time()
        try:
            async with session.get(
                "https://yields.llama.fi/pools",
                timeout=aiohttp.ClientTimeout(total=40),
            ) as r:
                if r.status == 200:
                    pools = (await r.json(content_type=None)).get("data", [])
                    async with state.lock:
                        state.pools_active = len(pools)
                    state.health["DeFiLlama"] = f"✓ {len(pools):,} pools"
                    state.lag["DeFiLlama"]    = (time.time() - t0) * 1000

                    # Process all pools in batches of BATCH_SIZE
                    batches = [
                        pools[i : i + BATCH_SIZE]
                        for i in range(0, len(pools), BATCH_SIZE)
                    ]
                    batch_tasks = [_process_pool_batch(state, b) for b in batches]
                    await asyncio.gather(*batch_tasks)
                else:
                    state.health["DeFiLlama"] = f"HTTP {r.status}"
        except Exception as e:
            state.health["DeFiLlama"] = type(e).__name__[:16]
        await asyncio.sleep(LLAMA_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 8 — COINGECKO (REST, every 30 s, free tier)
# ═══════════════════════════════════════════════════════════════════════════

async def coingecko_loop(session: aiohttp.ClientSession, state: BotState):
    ids  = ",".join(COINGECKO_IDS.values())
    url  = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    rev  = {v: k for k, v in COINGECKO_IDS.items()}
    while state.running:
        t0 = time.time()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    async with state.lock:
                        for gecko_id, tok in rev.items():
                            entry = data.get(gecko_id, {})
                            p = entry.get("usd", 0)
                            if p and float(p) > 0:
                                state.prices["CoinGecko"][tok] = float(p)
                    state.health["CoinGecko"] = "✓"
                    state.lag["CoinGecko"]    = (time.time() - t0) * 1000
                elif r.status == 429:
                    state.health["CoinGecko"] = "rate-limited"
                    await asyncio.sleep(60)
                    continue
                else:
                    state.health["CoinGecko"] = f"HTTP {r.status}"
        except Exception as e:
            state.health["CoinGecko"] = type(e).__name__[:12]
        await asyncio.sleep(GECKO_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  SOURCE 9 — THE GRAPH / UNISWAP V3 (REST, every 15 s)
# ═══════════════════════════════════════════════════════════════════════════

GRAPH_URL = (
    "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
)
GRAPH_QUERY = """
{
  pools(first:200, orderBy:volumeUSD, orderDirection:desc,
        where:{volumeUSD_gt:"1000000"}) {
    token0 { symbol decimals }
    token1 { symbol decimals }
    sqrtPrice
    token0Price
    token1Price
  }
}
"""
USDC_SYMS = {"USDC","USDT","DAI","BUSD","TUSD"}

async def graph_loop(session: aiohttp.ClientSession, state: BotState):
    while state.running:
        t0 = time.time()
        try:
            async with session.post(
                GRAPH_URL,
                json={"query": GRAPH_QUERY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    pools = (await r.json(content_type=None)) \
                        .get("data", {}).get("pools", [])
                    async with state.lock:
                        for pool in pools:
                            t0_sym = pool.get("token0", {}).get("symbol", "")
                            t1_sym = pool.get("token1", {}).get("symbol", "")
                            # Find the non-stable token
                            if t1_sym in USDC_SYMS and t0_sym in TOKENS:
                                p = pool.get("token0Price")
                                if p:
                                    state.prices["TheGraph"][t0_sym] = float(p)
                            elif t0_sym in USDC_SYMS and t1_sym in TOKENS:
                                p = pool.get("token1Price")
                                if p:
                                    state.prices["TheGraph"][t1_sym] = float(p)
                    state.health["TheGraph"] = f"✓ {len(pools)} pools"
                    state.lag["TheGraph"]    = (time.time() - t0) * 1000
                else:
                    state.health["TheGraph"] = f"HTTP {r.status}"
        except Exception as e:
            state.health["TheGraph"] = type(e).__name__[:14]
        await asyncio.sleep(GRAPH_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

console = Console()

def _fmt(v: float) -> str:
    if v == math.inf or v == 0:
        return "£0.00"
    return f"£{v:,.2f}"

def _runtime(state: BotState) -> str:
    e = int(time.time() - state.start_time)
    h, r = divmod(e, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def _tps(state: BotState) -> float:
    now = time.time()
    dt  = now - state.last_tps_ts
    if dt >= 1.0:
        cnt = state.total_count - state.last_tps_cnt
        state.tps_window.append(cnt / dt)
        state.last_tps_ts  = now
        state.last_tps_cnt = state.total_count
    return sum(state.tps_window) / max(len(state.tps_window), 1)

def _pace_bar(state: BotState) -> str:
    target_per_day = 500_000
    elapsed = time.time() - state.start_time
    if elapsed < 5:
        return "[          ]  0%"
    rate     = state.total_count / elapsed * 86400
    pct      = min(rate / target_per_day, 1.0)
    filled   = int(pct * 10)
    bar      = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {pct*100:.0f}%"

def _proj(state: BotState):
    elapsed = time.time() - state.start_time
    if elapsed < 10:
        return 0.0, 0.0, 0.0
    rate = state.total_base / elapsed
    return rate * 3600, rate * 86400, rate * 86400 * 7

def build_dashboard(state: BotState) -> str:
    _purge_60s(state)
    tps           = _tps(state)
    per_h, per_d, per_w = _proj(state)
    all_60        = len(state.opp_60s)
    quality       = sum(1 for _, o in state.opp_60s if o.gap_pct >= 0.5)
    worst         = state.worst if state.worst != math.inf else 0.0
    recent        = list(state.recent_5)
    W             = 50

    def row(s=""):
        return f"║ {s:<{W-2}} ║"

    def div():
        return "╠" + "═" * W + "╣"

    # source health block
    src_lines = []
    pairs = [
        ("Jupiter",   "Binance"),
        ("Kraken",    "OKX"),
        ("Bybit",     "Pyth"),
        ("CoinGecko", "TheGraph"),
        ("DeFiLlama", ""),
    ]
    for a, b in pairs:
        ha = state.health.get(a, "…")[:14]
        hb = state.health.get(b, "")[:14] if b else ""
        la = f"{state.lag.get(a,0):.0f}ms" if state.lag.get(a) else ""
        lb = f"{state.lag.get(b,0):.0f}ms" if b and state.lag.get(b) else ""
        left  = f"{a:<10} {ha:<14} {la:<6}"
        right = f"{b:<10} {hb:<14} {lb:<6}" if b else ""
        src_lines.append(row(f"  {left}{right}"))

    lines = [
        "╔" + "═" * W + "╗",
        row("  ⚡ HIGH-FREQUENCY PAPER TRADING ARB BOT ⚡"),
        div(),
        row(f"  Runtime : {_runtime(state):<20} Sources : 9"),
        row(f"  Tokens  : {len(TOKENS):<20} Pools   : {state.pools_active:,}"),
        div(),
        row("  LIVE TRADE RATE"),
        row(f"  Per second : {tps:<8.2f}  Target 500k/day pace:"),
        row(f"  {_pace_bar(state)}"),
        row(f"  Total all-time : {state.total_count:,}"),
        div(),
        row("  OPPORTUNITIES (last 60 s)"),
        row(f"  All detected   : {all_60}"),
        row(f"  Quality >0.5%  : {quality}"),
        div(),
        row("  PAPER PROFIT"),
        row(f"  Base £50       : {_fmt(state.total_base)}"),
        row(f"  Flash 10x      : {_fmt(state.total_flash)}"),
        row(f"  Best trade     : {_fmt(state.best)}"),
        row(f"  Worst trade    : {_fmt(worst)}"),
        div(),
        row("  BY TYPE"),
        row(f"  DEX_CEX  {state.type_counts['DEX_CEX']:<8}  CEX_CEX {state.type_counts['CEX_CEX']:<8}"),
        row(f"  ORACLE   {state.type_counts['ORACLE']:<8}  YIELD   {state.type_counts['YIELD']:<8}"),
        row(f"  GECKO    {state.type_counts['GECKO_ARB']:<8}"),
        div(),
        row("  LAST 5 DETECTIONS"),
    ]

    for i in range(5):
        if i < len(recent):
            o   = recent[-(i + 1)]
            tok = o.token[:16].ljust(16)
            lines.append(row(f"  {tok} {o.gap_pct:>6.2f}%  {_fmt(o.profit_base_gbp):>9}  {o.opp_type}"))
        else:
            lines.append(row("  —"))

    lines += [
        div(),
        row("  PROJECTED"),
        row(f"  Per hour   : {_fmt(per_h)}"),
        row(f"  Per 24 hrs : {_fmt(per_d)}"),
        row(f"  Per 7 days : {_fmt(per_w)}"),
        div(),
        row("  SOURCE HEALTH"),
        *src_lines,
        "╚" + "═" * W + "╝",
        f"  CSV → {_csv_path(state.csv_index)}   queue: {state.csv_queue.qsize()}",
    ]
    return "\n".join(lines)

async def dashboard_loop(state: BotState):
    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while state.running:
                live.update(Text(build_dashboard(state), style="bold green"))
                await asyncio.sleep(DASH_INT)
    except Exception:
        while state.running:
            print("\033[2J\033[H" + build_dashboard(state), flush=True)
            await asyncio.sleep(DASH_INT)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    state = BotState()

    # graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: setattr(state, "running", False))
        except (NotImplementedError, OSError):
            pass

    connector = aiohttp.TCPConnector(limit=50, enable_cleanup_closed=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            asyncio.create_task(csv_writer_loop(state),          name="csv"),
            asyncio.create_task(comparison_loop(state),          name="compare"),
            asyncio.create_task(jupiter_loop(session, state),    name="jupiter"),
            asyncio.create_task(binance_loop(state),             name="binance"),
            asyncio.create_task(kraken_loop(state),              name="kraken"),
            asyncio.create_task(okx_loop(state),                 name="okx"),
            asyncio.create_task(bybit_loop(state),               name="bybit"),
            asyncio.create_task(pyth_loop(session, state),       name="pyth"),
            asyncio.create_task(defillama_loop(session, state),  name="defillama"),
            asyncio.create_task(coingecko_loop(session, state),  name="coingecko"),
            asyncio.create_task(graph_loop(session, state),      name="graph"),
            asyncio.create_task(dashboard_loop(state),           name="dashboard"),
        ]
        print(f"Bot running — {len(tasks)} tasks active. Ctrl+C to stop.\n")
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            state.running = False
            for t in tasks:
                t.cancel()
            await asyncio.sleep(0.5)
            print(f"\nStopped. {state.total_count:,} opportunities logged.")
            print(f"CSV: {_csv_path(state.csv_index)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
