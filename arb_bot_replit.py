# ═══════════════════════════════════════════════════════════════
#   PAPER TRADING ARBITRAGE BOT  —  Replit Ready
#   No real trades. No wallet. No API keys required.
#   Paste this entire file into Replit and press Run.
# ═══════════════════════════════════════════════════════════════

# ── AUTO-INSTALL PACKAGES ────────────────────────────────────────
import subprocess, sys

def _install(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", pkg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

for _pkg in ["aiohttp", "websockets", "rich"]:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"Installing {_pkg}...")
        _install(_pkg)

# ── STANDARD LIBRARY ─────────────────────────────────────────────
import asyncio
import json
import csv
import os
import time
import signal
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field

# ── THIRD-PARTY ───────────────────────────────────────────────────
import aiohttp
import websockets
from rich.console import Console
from rich.live import Live
from rich.text import Text


# ════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════

TOKENS = [
    "SOL", "BTC", "ETH", "BONK", "JTO", "WIF",
    "PYTH", "JUP", "RAY", "ORCA", "MEME", "POPCAT",
    "WEN", "SAMO", "BOME", "MYRO", "SLERF", "ZEUS",
    "SHARK", "GUAC", "BERN", "AURY", "STEP", "COPE",
]

# Jupiter DEX mint addresses
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

# Binance CEX trading pairs
BINANCE_SYMBOLS = {
    "SOL":    "SOLUSDT",
    "BTC":    "BTCUSDT",
    "ETH":    "ETHUSDT",
    "BONK":   "BONKUSDT",
    "JTO":    "JTOUSDT",
    "WIF":    "WIFUSDT",
    "PYTH":   "PYTHUSDT",
    "JUP":    "JUPUSDT",
    "RAY":    "RAYUSDT",
    "ORCA":   "ORCAUSDT",
    "MEME":   "MEMEUSDT",
    "POPCAT": "POPCATUSDT",
    "WEN":    "WENUSDT",
    "SAMO":   "SAMOUSDT",
    "BOME":   "BOMEUSDT",
    "MYRO":   "MYROUSDT",
    "SLERF":  "SLERFUSDT",
    "ZEUS":   "ZEUSUSDT",
}

# Pyth Network price feed IDs
PYTH_IDS = {
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

# Trading parameters
TRADE_AMOUNT_GBP      = 50.0   # base paper trade size
FLASH_LOAN_MULTIPLIER = 10     # simulated flash loan leverage
MIN_GAP_PCT           = 0.25  # DEX vs CEX trigger threshold %
ORACLE_GAP_PCT        = 0.30  # DEX vs oracle trigger threshold %
YIELD_GAP_PCT         = 2.0   # DeFiLlama APY threshold %
FEE_EACH_SIDE         = 0.001  # 0.1% per leg

# Poll intervals (seconds)
JUPITER_POLL_INTERVAL   = 5
PYTH_POLL_INTERVAL      = 10
DEFILLAMA_POLL_INTERVAL = 60
DASHBOARD_REFRESH       = 3

CSV_FILE = "arb_opportunities.csv"


# ════════════════════════════════════════════════════════════════
#  STATE
# ════════════════════════════════════════════════════════════════

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
    opp_type:         str   # DEX_CEX | ORACLE | YIELD

@dataclass
class BotState:
    start_time:        float = field(default_factory=time.time)
    jupiter_prices:    dict  = field(default_factory=dict)
    binance_prices:    dict  = field(default_factory=dict)
    pyth_prices:       dict  = field(default_factory=dict)
    opportunities_60s: deque = field(default_factory=deque)
    recent_5:          deque = field(default_factory=lambda: deque(maxlen=5))
    total_profit_base: float = 0.0
    total_profit_flash:float = 0.0
    best_profit:       float = 0.0
    worst_profit:      float = float("inf")
    tokens_monitored:  int   = len(TOKENS)
    pools_active:      int   = 0
    running:           bool  = True
    status_msg:        str   = "Starting up..."
    lock: asyncio.Lock       = field(default_factory=asyncio.Lock)

state   = BotState()
console = Console()


# ════════════════════════════════════════════════════════════════
#  CSV LOGGING
# ════════════════════════════════════════════════════════════════

def init_csv():
    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="") as f:
        if write_header:
            csv.writer(f).writerow([
                "timestamp", "token", "source_a", "source_b",
                "price_a_usd", "price_b_usd", "gap_pct",
                "profit_base_gbp", "profit_flash_gbp", "type",
            ])

def log_csv(opp: Opportunity):
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            opp.timestamp, opp.token, opp.source_a, opp.source_b,
            f"{opp.price_a:.8f}", f"{opp.price_b:.8f}",
            f"{opp.gap_pct:.4f}",
            f"{opp.profit_base_gbp:.4f}",
            f"{opp.profit_flash_gbp:.4f}",
            opp.opp_type,
        ])


# ════════════════════════════════════════════════════════════════
#  OPPORTUNITY DETECTION
# ════════════════════════════════════════════════════════════════

async def record_opportunity(token, src_a, src_b, price_a, price_b, opp_type):
    if price_a <= 0 or price_b <= 0:
        return

    gap_pct   = abs(price_a - price_b) / min(price_a, price_b) * 100
    threshold = ORACLE_GAP_PCT if opp_type == "ORACLE" else MIN_GAP_PCT

    if gap_pct < threshold:
        return

    net_gap = gap_pct / 100 - (FEE_EACH_SIDE * 2)
    if net_gap <= 0:
        return

    profit_base  = TRADE_AMOUNT_GBP * net_gap
    profit_flash = TRADE_AMOUNT_GBP * FLASH_LOAN_MULTIPLIER * net_gap

    opp = Opportunity(
        timestamp        = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        token            = token,
        source_a         = src_a,
        source_b         = src_b,
        price_a          = price_a,
        price_b          = price_b,
        gap_pct          = gap_pct,
        profit_base_gbp  = profit_base,
        profit_flash_gbp = profit_flash,
        opp_type         = opp_type,
    )

    async with state.lock:
        state.opportunities_60s.append((time.time(), opp))
        state.recent_5.append(opp)
        state.total_profit_base  += profit_base
        state.total_profit_flash += profit_flash
        if profit_base > state.best_profit:
            state.best_profit = profit_base
        if profit_base < state.worst_profit:
            state.worst_profit = profit_base

    log_csv(opp)

def _purge_60s():
    cutoff = time.time() - 60
    while state.opportunities_60s and state.opportunities_60s[0][0] < cutoff:
        state.opportunities_60s.popleft()


# ════════════════════════════════════════════════════════════════
#  JUPITER DEX  (REST, every 5 s)
# ════════════════════════════════════════════════════════════════

async def fetch_jupiter(session: aiohttp.ClientSession):
    ids = ",".join(JUPITER_IDS[t] for t in TOKENS if t in JUPITER_IDS)
    url = f"https://price.jup.ag/v4/price?ids={ids}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                prices = (await r.json()).get("data", {})
                async with state.lock:
                    for token, mint in JUPITER_IDS.items():
                        if mint in prices:
                            state.jupiter_prices[token] = float(prices[mint]["price"])
                state.status_msg = "Jupiter OK | Binance WS streaming"
            else:
                state.status_msg = f"Jupiter HTTP {r.status}"
    except Exception as e:
        state.status_msg = f"Jupiter error: {type(e).__name__}"

async def jupiter_loop(session):
    while state.running:
        await fetch_jupiter(session)
        await _compare_jup_vs_binance()
        await _compare_jup_vs_pyth()
        await asyncio.sleep(JUPITER_POLL_INTERVAL)


# ════════════════════════════════════════════════════════════════
#  BINANCE CEX  (WebSocket, real-time)
# ════════════════════════════════════════════════════════════════

async def binance_ws_loop():
    streams  = "/".join(v.lower() + "@miniTicker" for v in BINANCE_SYMBOLS.values())
    uri      = f"wss://stream.binance.com:9443/stream?streams={streams}"
    delay    = 2
    while state.running:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                delay = 2
                async for raw in ws:
                    if not state.running:
                        break
                    ticker = json.loads(raw).get("data", {})
                    sym    = ticker.get("s", "")
                    price  = ticker.get("c")
                    if price:
                        for token, bsym in BINANCE_SYMBOLS.items():
                            if bsym == sym:
                                async with state.lock:
                                    state.binance_prices[token] = float(price)
                                break
        except Exception as e:
            if not state.running:
                break
            state.status_msg = f"Binance WS error ({type(e).__name__}), retry {delay}s"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# ════════════════════════════════════════════════════════════════
#  PYTH ORACLE  (REST, every 10 s)
# ════════════════════════════════════════════════════════════════

async def fetch_pyth(session: aiohttp.ClientSession):
    params = "&".join(f"ids[]={v}" for v in PYTH_IDS.values())
    url    = f"https://hermes.pyth.network/api/latest_price_feeds?{params}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                id_map = {v: k for k, v in PYTH_IDS.items()}
                async with state.lock:
                    for feed in await r.json():
                        sym = id_map.get(feed.get("id", ""))
                        if sym:
                            pd   = feed.get("price", {})
                            raw  = pd.get("price")
                            expo = pd.get("expo", 0)
                            if raw is not None:
                                state.pyth_prices[sym] = float(raw) * (10 ** expo)
    except Exception:
        pass

async def pyth_loop(session):
    while state.running:
        await fetch_pyth(session)
        await asyncio.sleep(PYTH_POLL_INTERVAL)


# ════════════════════════════════════════════════════════════════
#  DEFILLAMA YIELDS  (REST, every 60 s)
# ════════════════════════════════════════════════════════════════

async def fetch_defillama(session: aiohttp.ClientSession):
    try:
        async with session.get(
            "https://yields.llama.fi/pools",
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            if r.status != 200:
                return
            pools = (await r.json()).get("data", [])
            valid = sorted(
                [p for p in pools if p.get("apy") is not None],
                key=lambda x: x.get("apy", 0), reverse=True
            )
            async with state.lock:
                state.pools_active = len(pools)
            for pool in valid[:100]:
                apy = pool.get("apy") or 0
                if apy > YIELD_GAP_PCT:
                    label = f"{pool.get('symbol','?')[:10]}@{pool.get('project','?')[:8]}"
                    chain = pool.get("chain", "chain")
                    await record_opportunity(
                        token   = label,
                        src_a   = "DeFiLlama",
                        src_b   = f"{chain}Pool",
                        price_a = apy,
                        price_b = 0.0,
                        opp_type= "YIELD",
                    )
    except Exception:
        pass

async def defillama_loop(session):
    while state.running:
        await fetch_defillama(session)
        await asyncio.sleep(DEFILLAMA_POLL_INTERVAL)


# ════════════════════════════════════════════════════════════════
#  PRICE COMPARISONS
# ════════════════════════════════════════════════════════════════

async def _compare_jup_vs_binance():
    async with state.lock:
        j = dict(state.jupiter_prices)
        b = dict(state.binance_prices)
    for tok in TOKENS:
        if j.get(tok) and b.get(tok):
            await record_opportunity(tok, "Jupiter", "Binance", j[tok], b[tok], "DEX_CEX")

async def _compare_jup_vs_pyth():
    async with state.lock:
        j = dict(state.jupiter_prices)
        p = dict(state.pyth_prices)
    for tok in TOKENS:
        if j.get(tok) and p.get(tok):
            await record_opportunity(tok, "Jupiter", "Pyth", j[tok], p[tok], "ORACLE")


# ════════════════════════════════════════════════════════════════
#  TERMINAL DASHBOARD
# ════════════════════════════════════════════════════════════════

def _fmt(val: float) -> str:
    if val == float("inf") or val == 0:
        return "£0.00"
    return f"£{val:,.2f}"

def _runtime() -> str:
    e = int(time.time() - state.start_time)
    h, r = divmod(e, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def _projections():
    elapsed = time.time() - state.start_time
    if elapsed < 10:
        return 0.0, 0.0, 0.0
    rate = state.total_profit_base / elapsed
    return rate * 3600, rate * 86400, rate * 86400 * 7

def build_dashboard() -> str:
    _purge_60s()
    per_h, per_d, per_w = _projections()

    all_60     = len(state.opportunities_60s)
    quality    = sum(1 for _, o in state.opportunities_60s if o.gap_pct >= 0.5)
    worst      = state.worst_profit if state.worst_profit != float("inf") else 0.0
    recent     = list(state.recent_5)

    W = 41  # inner width

    def row(content=""):
        return f"║ {content:<{W-2}} ║"

    def divider():
        return "╠" + "═" * W + "╣"

    lines = [
        "╔" + "═" * W + "╗",
        row("      PAPER TRADING LIVE"),
        divider(),
        row(f"Runtime:          {_runtime()}"),
        row(f"Tokens monitored: {state.tokens_monitored}"),
        row(f"Pools active:     {state.pools_active:,}"),
        divider(),
        row("OPPORTUNITIES FOUND:"),
        row(f"  Last 60 seconds:       {all_60}"),
        row(f"  Quality filtered >0.5%: {quality}"),
        row(f"  Would have traded:      {quality}"),
        divider(),
        row("PAPER PROFIT SO FAR:"),
        row(f"  Without flash loans:  {_fmt(state.total_profit_base)}"),
        row(f"  With 10x flash loans: {_fmt(state.total_profit_flash)}"),
        row(f"  Best single trade:    {_fmt(state.best_profit)}"),
        row(f"  Worst trade:          {_fmt(worst)}"),
        divider(),
        row("LAST 5 OPPORTUNITIES:"),
    ]

    for i in range(5):
        if i < len(recent):
            o   = recent[-(i + 1)]
            tok = o.token[:14].ljust(14)
            gap = f"{o.gap_pct:.2f}%".rjust(6)
            prf = _fmt(o.profit_base_gbp).rjust(8)
            lines.append(row(f"  {tok} {gap} gap {prf} profit"))
        else:
            lines.append(row("  -"))

    lines += [
        divider(),
        row("PROJECTED (at this rate):"),
        row(f"  Per hour:  {_fmt(per_h)}"),
        row(f"  Per 24hrs: {_fmt(per_d)}"),
        row(f"  Per 7days: {_fmt(per_w)}"),
        "╚" + "═" * W + "╝",
        "",
        f"  CSV : {CSV_FILE}",
        f"  Info: {state.status_msg}",
    ]
    return "\n".join(lines)

async def dashboard_loop():
    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while state.running:
                live.update(Text(build_dashboard(), style="bold green"))
                await asyncio.sleep(DASHBOARD_REFRESH)
    except Exception:
        # Fallback for environments where Live mode fails
        while state.running:
            print("\033[2J\033[H" + build_dashboard(), flush=True)
            await asyncio.sleep(DASHBOARD_REFRESH)


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════

async def main():
    init_csv()
    print("Paper Trading Arb Bot starting...")
    print(f"Monitoring {len(TOKENS)} tokens across Jupiter, Binance, Pyth, DeFiLlama")
    print(f"Logging to: {CSV_FILE}\n")
    await asyncio.sleep(1)

    # Graceful shutdown on Ctrl+C / SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: setattr(state, "running", False))
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            asyncio.create_task(jupiter_loop(session),   name="jupiter"),
            asyncio.create_task(binance_ws_loop(),       name="binance_ws"),
            asyncio.create_task(pyth_loop(session),      name="pyth"),
            asyncio.create_task(defillama_loop(session), name="defillama"),
            asyncio.create_task(dashboard_loop(),        name="dashboard"),
        ]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            state.running = False
            for t in tasks:
                t.cancel()
            await asyncio.sleep(0.5)
            print(f"\nStopped. Opportunities logged to {CSV_FILE}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
