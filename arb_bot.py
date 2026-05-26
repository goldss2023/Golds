#!/usr/bin/env python3
"""
Paper Trading Arbitrage Bot
Monitors Jupiter DEX, Binance CEX, Pyth oracle, and DeFiLlama yield pools.
No real trades. No wallet. No keys required.
"""

import asyncio
import aiohttp
import websockets
import json
import csv
import os
import time
import signal
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

# ─── CONFIG ──────────────────────────────────────────────────────────────────

TOKENS = [
    "SOL", "BTC", "ETH", "BONK", "JTO", "WIF",
    "PYTH", "JUP", "RAY", "ORCA", "MEME", "POPCAT",
    "WEN", "SAMO", "BOME", "MYRO", "SLERF", "ZEUS",
    "SHARK", "GUAC", "BERN", "AURY", "STEP", "COPE",
]

# Jupiter uses mint addresses for some tokens; map symbol → id used in API
JUPITER_IDS = {
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

# Binance symbol map (symbol → binance trading pair)
BINANCE_SYMBOLS = {
    "SOL": "SOLUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT",
    "BONK": "BONKUSDT", "JTO": "JTOUSDT", "WIF": "WIFUSDT",
    "PYTH": "PYTHUSDT", "JUP": "JUPUSDT", "RAY": "RAYUSDT",
    "ORCA": "ORCAUSDT", "MEME": "MEMEUSDT", "POPCAT": "POPCATUSDT",
    "WEN": "WENUSDT", "SAMO": "SAMOUSDT", "BOME": "BOMEUSDT",
    "MYRO": "MYROUSDT", "SLERF": "SLERFUSDT", "ZEUS": "ZEUSUSDT",
}

TRADE_AMOUNT_GBP = 50.0
FLASH_LOAN_MULTIPLIER = 10
MIN_GAP_PCT = 0.25
ORACLE_GAP_PCT = 0.30
YIELD_GAP_PCT = 2.0
JUPITER_POLL_INTERVAL = 5
PYTH_POLL_INTERVAL = 10
DEFILLAMA_POLL_INTERVAL = 60
DASHBOARD_REFRESH = 3
CSV_FILE = "arb_opportunities.csv"
GBP_USD_RATE = 1.27  # approximate

# ─── STATE ───────────────────────────────────────────────────────────────────

@dataclass
class Opportunity:
    timestamp: str
    token: str
    source_a: str
    source_b: str
    price_a: float
    price_b: float
    gap_pct: float
    profit_base_gbp: float
    profit_flash_gbp: float
    opp_type: str  # "DEX_CEX" | "ORACLE" | "YIELD"

@dataclass
class BotState:
    start_time: float = field(default_factory=time.time)
    jupiter_prices: dict = field(default_factory=dict)
    binance_prices: dict = field(default_factory=dict)
    pyth_prices: dict = field(default_factory=dict)
    top_yield_pools: list = field(default_factory=list)
    opportunities_all: list = field(default_factory=list)      # all time
    opportunities_60s: deque = field(default_factory=lambda: deque())
    recent_5: deque = field(default_factory=lambda: deque(maxlen=5))
    total_profit_base: float = 0.0
    total_profit_flash: float = 0.0
    best_profit: float = 0.0
    worst_profit: float = float("inf")
    tokens_monitored: int = len(TOKENS)
    pools_active: int = 0
    running: bool = True
    status_msg: str = "Initialising..."
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

state = BotState()
console = Console()

# ─── CSV ─────────────────────────────────────────────────────────────────────

def init_csv():
    exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow([
                "timestamp", "token", "source_a", "source_b",
                "price_a_usd", "price_b_usd", "gap_pct",
                "profit_base_gbp", "profit_flash_gbp", "type"
            ])

def log_csv(opp: Opportunity):
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            opp.timestamp, opp.token, opp.source_a, opp.source_b,
            f"{opp.price_a:.8f}", f"{opp.price_b:.8f}",
            f"{opp.gap_pct:.4f}",
            f"{opp.profit_base_gbp:.4f}", f"{opp.profit_flash_gbp:.4f}",
            opp.opp_type
        ])

# ─── OPPORTUNITY DETECTION ────────────────────────────────────────────────────

async def record_opportunity(token, src_a, src_b, price_a, price_b, opp_type):
    if price_a <= 0 or price_b <= 0:
        return
    gap_pct = abs(price_a - price_b) / min(price_a, price_b) * 100
    threshold = ORACLE_GAP_PCT if opp_type == "ORACLE" else MIN_GAP_PCT
    if gap_pct < threshold:
        return

    # Calculate GBP profit: gap% of trade amount, minus 0.1% fees each side
    net_gap = gap_pct / 100 - 0.002
    if net_gap <= 0:
        return
    profit_base = TRADE_AMOUNT_GBP * net_gap
    profit_flash = TRADE_AMOUNT_GBP * FLASH_LOAN_MULTIPLIER * net_gap

    opp = Opportunity(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        token=token,
        source_a=src_a,
        source_b=src_b,
        price_a=price_a,
        price_b=price_b,
        gap_pct=gap_pct,
        profit_base_gbp=profit_base,
        profit_flash_gbp=profit_flash,
        opp_type=opp_type,
    )

    async with state.lock:
        state.opportunities_all.append(opp)
        state.opportunities_60s.append((time.time(), opp))
        state.recent_5.append(opp)
        state.total_profit_base += profit_base
        state.total_profit_flash += profit_flash
        if profit_base > state.best_profit:
            state.best_profit = profit_base
        if profit_base < state.worst_profit:
            state.worst_profit = profit_base

    log_csv(opp)

def purge_60s_window():
    cutoff = time.time() - 60
    while state.opportunities_60s and state.opportunities_60s[0][0] < cutoff:
        state.opportunities_60s.popleft()

# ─── JUPITER ─────────────────────────────────────────────────────────────────

async def fetch_jupiter(session: aiohttp.ClientSession):
    ids = ",".join(JUPITER_IDS[t] for t in TOKENS if t in JUPITER_IDS)
    url = f"https://price.jup.ag/v4/price?ids={ids}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                prices = data.get("data", {})
                async with state.lock:
                    for token, mint in JUPITER_IDS.items():
                        if mint in prices:
                            state.jupiter_prices[token] = float(prices[mint]["price"])
                state.status_msg = "Jupiter: OK"
            else:
                state.status_msg = f"Jupiter: HTTP {r.status}"
    except Exception as e:
        state.status_msg = f"Jupiter: {type(e).__name__}"

async def jupiter_loop(session):
    while state.running:
        await fetch_jupiter(session)
        await compare_jupiter_vs_binance()
        await compare_jupiter_vs_pyth()
        await asyncio.sleep(JUPITER_POLL_INTERVAL)

# ─── BINANCE WebSocket ────────────────────────────────────────────────────────

async def binance_ws_loop():
    symbols = [v.lower() + "@miniTicker" for v in BINANCE_SYMBOLS.values()]
    streams = "/".join(symbols)
    uri = f"wss://stream.binance.com:9443/stream?streams={streams}"
    retry_delay = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                retry_delay = 2
                state.status_msg = "Binance WS: connected"
                async for raw in ws:
                    if not state.running:
                        break
                    msg = json.loads(raw)
                    ticker = msg.get("data", {})
                    sym = ticker.get("s", "")
                    price_str = ticker.get("c")
                    if price_str:
                        for token, bsym in BINANCE_SYMBOLS.items():
                            if bsym == sym:
                                async with state.lock:
                                    state.binance_prices[token] = float(price_str)
                                break
        except Exception as e:
            if not state.running:
                break
            state.status_msg = f"Binance WS: {type(e).__name__}, retry {retry_delay}s"
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

# ─── PYTH ─────────────────────────────────────────────────────────────────────

PYTH_IDS = {
    "SOL": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "BTC": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "BONK": "72b021217ca3fe68922a19aaf990109cb9d84e9ad004b4d2025ad6f529314419",
    "JTO": "b43660a5f790c69354b0729a5ef9d50d68f1df92107540210b9cccba1f947cc2",
    "WIF": "4ca4beeca86f0d164160323817a4e42b10010a724c2217c6ee41b54cd4cc61fc",
    "PYTH": "0bbf28e9a841a1cc788f6a361b17ca072d0ea3098a1e5df1c3922d06719579ff",
    "JUP":  "0a0408d619e9380abad35060f9192039ed5042fa6f82301d0e48bb52be830996",
    "RAY":  "91568baa8beb53db23eb3fb7f22c6e8bd303d103919e19733f2bb642d3e7987a",
}

async def fetch_pyth(session: aiohttp.ClientSession):
    ids_param = "&".join(f"ids[]={v}" for v in PYTH_IDS.values())
    url = f"https://hermes.pyth.network/api/latest_price_feeds?{ids_param}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                feeds = await r.json()
                id_to_symbol = {v: k for k, v in PYTH_IDS.items()}
                async with state.lock:
                    for feed in feeds:
                        feed_id = feed.get("id", "")
                        symbol = id_to_symbol.get(feed_id)
                        if symbol:
                            price_data = feed.get("price", {})
                            raw_price = price_data.get("price")
                            expo = price_data.get("expo", 0)
                            if raw_price is not None:
                                state.pyth_prices[symbol] = float(raw_price) * (10 ** expo)
    except Exception as e:
        pass  # Pyth is best-effort

async def pyth_loop(session):
    while state.running:
        await fetch_pyth(session)
        await asyncio.sleep(PYTH_POLL_INTERVAL)

# ─── DEFILLAMA ────────────────────────────────────────────────────────────────

async def fetch_defillama(session: aiohttp.ClientSession):
    url = "https://yields.llama.fi/pools"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status == 200:
                data = await r.json()
                pools = data.get("data", [])
                # Sort by APY descending, take top 100
                pools_sorted = sorted(
                    [p for p in pools if p.get("apy") is not None],
                    key=lambda x: x.get("apy", 0),
                    reverse=True
                )[:100]
                async with state.lock:
                    state.top_yield_pools = pools_sorted
                    state.pools_active = len(pools)
                # Detect yield opportunities: pools where APY > YIELD_GAP_PCT
                for pool in pools_sorted[:100]:
                    apy = pool.get("apy", 0) or 0
                    if apy > YIELD_GAP_PCT:
                        symbol = pool.get("symbol", "UNKNOWN")
                        project = pool.get("project", "")
                        chain = pool.get("chain", "")
                        # Simulate as opportunity with yield gap
                        token_label = f"{symbol[:10]}@{project[:8]}"
                        await record_opportunity(
                            token=token_label,
                            src_a="DeFiLlama",
                            src_b=f"{chain}Pool",
                            price_a=apy,
                            price_b=0.0,  # baseline
                            opp_type="YIELD",
                        )
    except Exception as e:
        pass

async def defillama_loop(session):
    while state.running:
        await fetch_defillama(session)
        await asyncio.sleep(DEFILLAMA_POLL_INTERVAL)

# ─── COMPARISONS ──────────────────────────────────────────────────────────────

async def compare_jupiter_vs_binance():
    async with state.lock:
        j = dict(state.jupiter_prices)
        b = dict(state.binance_prices)
    for token in TOKENS:
        jp = j.get(token)
        bp = b.get(token)
        if jp and bp:
            await record_opportunity(token, "Jupiter", "Binance", jp, bp, "DEX_CEX")

async def compare_jupiter_vs_pyth():
    async with state.lock:
        j = dict(state.jupiter_prices)
        p = dict(state.pyth_prices)
    for token in TOKENS:
        jp = j.get(token)
        pp = p.get(token)
        if jp and pp:
            await record_opportunity(token, "Jupiter", "Pyth", jp, pp, "ORACLE")

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

def format_gbp(val: float) -> str:
    if val == float("inf") or val == 0:
        return "£0.00"
    return f"£{val:,.2f}"

def runtime_str() -> str:
    elapsed = int(time.time() - state.start_time)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def projected_profits() -> tuple:
    elapsed = time.time() - state.start_time
    if elapsed < 10:
        return 0.0, 0.0, 0.0
    rate = state.total_profit_base / elapsed  # GBP per second
    per_hour = rate * 3600
    per_day = rate * 86400
    per_week = rate * 86400 * 7
    return per_hour, per_day, per_week

def build_dashboard() -> str:
    purge_60s_window()
    per_hour, per_day, per_week = projected_profits()

    # Count quality-filtered (gap > 0.5%)
    quality = [o for _, o in state.opportunities_60s if o.gap_pct >= 0.5]
    all_60 = len(state.opportunities_60s)
    quality_count = len(quality)

    worst = state.worst_profit if state.worst_profit != float("inf") else 0.0

    lines = [
        "╔═══════════════════════════════════════╗",
        "║      PAPER TRADING LIVE               ║",
        "╠═══════════════════════════════════════╣",
        f"║ Runtime: {runtime_str():<29}║",
        f"║ Tokens monitored: {state.tokens_monitored:<20}║",
        f"║ Pools active: {state.pools_active:<24}║",
        "╠═══════════════════════════════════════╣",
        "║ OPPORTUNITIES FOUND:                  ║",
        f"║ Last 60 seconds: {all_60:<22}║",
        f"║ Quality filtered (>0.5%): {quality_count:<13}║",
        f"║ Would have traded: {quality_count:<20}║",
        "╠═══════════════════════════════════════╣",
        "║ PAPER PROFIT SO FAR:                  ║",
        f"║ Without flash loans: {format_gbp(state.total_profit_base):<18}║",
        f"║ With 10x flash loans: {format_gbp(state.total_profit_flash):<17}║",
        f"║ Best single trade:   {format_gbp(state.best_profit):<18}║",
        f"║ Worst trade:         {format_gbp(worst):<18}║",
        "╠═══════════════════════════════════════╣",
        "║ LAST 5 OPPORTUNITIES:                 ║",
    ]

    recent = list(state.recent_5)
    for i in range(5):
        if i < len(recent):
            o = recent[-(i+1)]
            tok = o.token[:12].ljust(12)
            gap = f"{o.gap_pct:.2f}%"
            prof = format_gbp(o.profit_base_gbp)
            line = f"║ {tok} {gap:>6} gap {prof:>8} profit ║"
            # Pad to width 41
            line = line[:41].ljust(41) + "║" if len(line) > 42 else line
            lines.append(line)
        else:
            lines.append("║ -                                     ║")

    lines += [
        "╠═══════════════════════════════════════╣",
        "║ PROJECTED (at this rate):             ║",
        f"║ Per hour:  {format_gbp(per_hour):<28}║",
        f"║ Per 24hrs: {format_gbp(per_day):<28}║",
        f"║ Per 7days: {format_gbp(per_week):<28}║",
        "╚═══════════════════════════════════════╝",
        "",
        f"  CSV log: {CSV_FILE}",
        f"  Status:  {state.status_msg}",
    ]
    return "\n".join(lines)

async def dashboard_loop():
    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while state.running:
            text = build_dashboard()
            live.update(Text(text, style="bold green"))
            await asyncio.sleep(DASHBOARD_REFRESH)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    init_csv()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(state, "running", False))

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            asyncio.create_task(jupiter_loop(session)),
            asyncio.create_task(binance_ws_loop()),
            asyncio.create_task(pyth_loop(session)),
            asyncio.create_task(defillama_loop(session)),
            asyncio.create_task(dashboard_loop()),
        ]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            state.running = False
            for t in tasks:
                t.cancel()
            console.print("\n[yellow]Bot stopped. CSV saved to arb_opportunities.csv[/yellow]")

if __name__ == "__main__":
    asyncio.run(main())
