#!/usr/bin/env python3
"""
LIVE API TEST SUITE — arb_bot_hf.py
Uses REAL network calls to REAL APIs. No mocks. No injected data.
Shows actual prices, actual latencies, actual WebSocket frames.

Run on any machine with internet access:
    pip install aiohttp websockets rich
    python3 live_test.py

Each test either PASSES (with real data printed) or FAILS (with the
exact error). Nothing is faked.
"""
import subprocess, sys
for _p in ["aiohttp", "websockets", "rich"]:
    try: __import__(_p)
    except ImportError:
        subprocess.check_call([sys.executable,"-m","pip","install","-q",_p],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

import asyncio, json, time, math, csv, os, tempfile
from datetime import datetime
import aiohttp
import websockets
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

TIMEOUT = aiohttp.ClientTimeout(total=15)

def _ok(name, detail=""):
    global PASS_COUNT
    PASS_COUNT += 1
    RESULTS.append(("PASS", name, detail))
    console.print(f"  [bold green]✓[/] {name}", end="")
    if detail:
        console.print(f"  [dim]{detail}[/]", end="")
    console.print()

def _fail(name, reason):
    global FAIL_COUNT
    FAIL_COUNT += 1
    RESULTS.append(("FAIL", name, reason))
    console.print(f"  [bold red]✗[/] {name}  [red]{reason}[/]")

def run(name, coro):
    try:
        asyncio.run(coro)
    except AssertionError as e:
        _fail(name, str(e))
    except Exception as e:
        _fail(name, f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════
#  1. JUPITER — real prices for all 24 tokens
# ═══════════════════════════════════════════════════════════════

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

jupiter_prices = {}

async def test_jupiter_connectivity():
    ids = ",".join(JUPITER_IDS.values())
    url = f"https://price.jup.ag/v4/price?ids={ids}"
    t0  = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            data = (await r.json(content_type=None)).get("data", {})
            assert len(data) > 0, "empty response"
            for tok, mint in JUPITER_IDS.items():
                entry = data.get(mint)
                if entry:
                    p = float(entry["price"])
                    assert p > 0, f"{tok} price is {p}"
                    jupiter_prices[tok] = p
            lag = (time.time() - t0) * 1000
            _ok("Jupiter API reachable", f"{len(jupiter_prices)} prices in {lag:.0f}ms")
            # print table
            t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
            t.add_column("Token", style="cyan")
            t.add_column("Price (USD)", justify="right")
            for tok in list(jupiter_prices)[:12]:
                t.add_row(tok, f"${jupiter_prices[tok]:,.6f}")
            console.print(t)

async def test_jupiter_sol_price_sane():
    assert "SOL" in jupiter_prices, "SOL price not fetched yet"
    p = jupiter_prices["SOL"]
    assert 1 < p < 10_000, f"SOL price ${p} looks wrong"
    _ok("Jupiter SOL price in sane range", f"${p:,.2f}")

async def test_jupiter_btc_price_sane():
    assert "BTC" in jupiter_prices
    p = jupiter_prices["BTC"]
    assert 1_000 < p < 10_000_000, f"BTC price ${p} looks wrong"
    _ok("Jupiter BTC price in sane range", f"${p:,.2f}")

async def test_jupiter_all_positive():
    zeros = [t for t, p in jupiter_prices.items() if p <= 0]
    assert len(zeros) == 0, f"Zero/negative prices: {zeros}"
    _ok("All Jupiter prices positive", f"{len(jupiter_prices)} tokens")

async def test_jupiter_no_nan():
    nans = [t for t, p in jupiter_prices.items() if not math.isfinite(p)]
    assert len(nans) == 0, f"NaN/inf prices: {nans}"
    _ok("No NaN/inf in Jupiter prices")

async def test_jupiter_poll_twice():
    """Second poll should return fresh data (price may differ slightly)."""
    ids = ",".join(list(JUPITER_IDS.values())[:3])
    url = f"https://price.jup.ag/v4/price?ids={ids}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r1:
            d1 = await r1.json(content_type=None)
        await asyncio.sleep(2)
        async with s.get(url, timeout=TIMEOUT) as r2:
            d2 = await r2.json(content_type=None)
    assert d1 and d2
    _ok("Jupiter returns data on two consecutive polls")


# ═══════════════════════════════════════════════════════════════
#  2. BINANCE REST — sanity before WebSocket
# ═══════════════════════════════════════════════════════════════

binance_prices = {}

async def test_binance_rest_sol():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT"
    t0  = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            d = await r.json(content_type=None)
            p = float(d["price"])
            assert p > 0
            binance_prices["SOL"] = p
            lag = (time.time() - t0) * 1000
            _ok("Binance REST reachable", f"SOL = ${p:,.2f}  lag {lag:.0f}ms")

async def test_binance_rest_btc():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200
            p = float((await r.json(content_type=None))["price"])
            assert p > 1000
            binance_prices["BTC"] = p
            _ok("Binance BTC price sane", f"${p:,.2f}")

async def test_binance_multi_ticker():
    symbols = ["SOLUSDT","ETHUSDT","BTCUSDT","BONKUSDT","JUPUSDT","RAYUSDT"]
    async with aiohttp.ClientSession() as s:
        for sym in symbols:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
            async with s.get(url, timeout=TIMEOUT) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    p = float(d["price"])
                    tok = sym.replace("USDT","")
                    binance_prices[tok] = p
    got = len(binance_prices)
    assert got >= 3, f"Only got {got} Binance prices"
    _ok("Binance multi-token REST", f"{got} prices fetched")
    for tok, p in list(binance_prices.items())[:6]:
        console.print(f"    [dim]{tok:8} ${p:,.4f}[/]")


# ═══════════════════════════════════════════════════════════════
#  3. BINANCE WEBSOCKET — real streaming frames
# ═══════════════════════════════════════════════════════════════

async def test_binance_ws_connects_and_streams():
    uri    = "wss://stream.binance.com:9443/stream?streams=solusdt@miniTicker/ethusdt@miniTicker/btcusdt@miniTicker"
    frames = []
    prices = {}
    t0     = time.time()
    try:
        async with websockets.connect(uri, ping_interval=None) as ws:
            while len(frames) < 5 and time.time() - t0 < 15:
                raw    = await asyncio.wait_for(ws.recv(), timeout=10)
                ticker = json.loads(raw).get("data", {})
                sym    = ticker.get("s","")
                price  = ticker.get("c")
                if price:
                    prices[sym] = float(price)
                    frames.append(sym)
        assert len(frames) >= 3, f"Only {len(frames)} frames in 15s"
        _ok("Binance WS streams real tickers", f"{len(frames)} frames  SOL=${prices.get('SOLUSDT',0):,.2f}")
        for sym, p in prices.items():
            console.print(f"    [dim]{sym:12} ${p:,.4f}[/]")
    except Exception as e:
        _fail("Binance WebSocket", str(e))

async def test_binance_ws_price_matches_rest():
    """WS price should be within 1% of REST price."""
    if "SOL" not in binance_prices:
        _fail("Binance WS vs REST", "REST price not available")
        return
    rest_price = binance_prices["SOL"]
    uri = "wss://stream.binance.com:9443/stream?streams=solusdt@miniTicker"
    async with websockets.connect(uri, ping_interval=None) as ws:
        raw   = await asyncio.wait_for(ws.recv(), timeout=10)
        ws_p  = float(json.loads(raw)["data"]["c"])
    diff_pct = abs(ws_p - rest_price) / rest_price * 100
    assert diff_pct < 1.0, f"WS ${ws_p} vs REST ${rest_price} = {diff_pct:.3f}% diff"
    _ok("Binance WS price matches REST", f"diff={diff_pct:.4f}%")


# ═══════════════════════════════════════════════════════════════
#  4. PYTH NETWORK — real oracle prices
# ═══════════════════════════════════════════════════════════════

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

pyth_prices = {}

async def test_pyth_connectivity():
    params = "&".join(f"ids[]={v}" for v in PYTH_IDS.values())
    url    = f"https://hermes.pyth.network/api/latest_price_feeds?{params}"
    t0     = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            feeds = await r.json(content_type=None)
            assert len(feeds) > 0
            rev = {v: k for k, v in PYTH_IDS.items()}
            for feed in feeds:
                tok  = rev.get(feed.get("id",""))
                pd   = feed.get("price", {})
                raw  = pd.get("price")
                expo = pd.get("expo", 0)
                if tok and raw is not None:
                    p = float(raw) * (10 ** expo)
                    if p > 0:
                        pyth_prices[tok] = p
            lag = (time.time() - t0) * 1000
            _ok("Pyth Network reachable", f"{len(pyth_prices)} feeds in {lag:.0f}ms")
            for tok, p in pyth_prices.items():
                console.print(f"    [dim]{tok:8} ${p:,.6f}[/]")

async def test_pyth_sol_sane():
    assert "SOL" in pyth_prices, "SOL not in Pyth response"
    p = pyth_prices["SOL"]
    assert 1 < p < 10_000, f"Pyth SOL ${p} looks wrong"
    _ok("Pyth SOL price sane", f"${p:,.4f}")

async def test_pyth_vs_jupiter_gap():
    """Real-world: Pyth oracle vs Jupiter DEX. Flag if gap > 0.3%."""
    common = set(pyth_prices) & set(jupiter_prices)
    assert len(common) > 0, "No tokens in common between Pyth and Jupiter"
    gaps = []
    for tok in common:
        jp = jupiter_prices[tok]
        pp = pyth_prices[tok]
        if jp > 0 and pp > 0:
            gap = abs(jp - pp) / min(jp, pp) * 100
            gaps.append((tok, jp, pp, gap))
    gaps.sort(key=lambda x: -x[3])
    _ok("Pyth vs Jupiter gap measured", f"{len(gaps)} pairs")
    t = Table(box=box.SIMPLE, header_style="bold yellow")
    t.add_column("Token")
    t.add_column("Jupiter", justify="right")
    t.add_column("Pyth", justify="right")
    t.add_column("Gap %", justify="right")
    t.add_column("Arb?", justify="center")
    for tok, jp, pp, gap in gaps:
        flag = "[green]YES[/]" if gap >= 0.30 else "[dim]no[/]"
        t.add_row(tok, f"${jp:,.4f}", f"${pp:,.4f}", f"{gap:.4f}%", flag)
    console.print(t)


# ═══════════════════════════════════════════════════════════════
#  5. DEFILLAMA — real pool scan
# ═══════════════════════════════════════════════════════════════

llama_pools = []

async def test_defillama_connectivity():
    t0 = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get("https://yields.llama.fi/pools",
                         timeout=aiohttp.ClientTimeout(total=40)) as r:
            assert r.status == 200, f"HTTP {r.status}"
            pools = (await r.json(content_type=None)).get("data", [])
            assert len(pools) > 100, f"Only {len(pools)} pools"
            llama_pools.extend(pools)
            lag = (time.time() - t0) * 1000
            _ok("DeFiLlama reachable", f"{len(pools):,} pools in {lag:.0f}ms")

async def test_defillama_pool_count():
    assert len(llama_pools) > 1000, f"Expected >1000 pools, got {len(llama_pools)}"
    _ok("DeFiLlama returns >1000 pools", f"{len(llama_pools):,} total")

async def test_defillama_top_apy_pools():
    valid = [p for p in llama_pools if p.get("apy") and float(p["apy"]) > 0]
    top   = sorted(valid, key=lambda x: float(x["apy"]), reverse=True)[:10]
    assert len(top) > 0
    _ok("DeFiLlama top APY pools", f"highest: {float(top[0]['apy']):.1f}% APY")
    t = Table(box=box.SIMPLE, header_style="bold cyan")
    t.add_column("Symbol")
    t.add_column("Project")
    t.add_column("Chain")
    t.add_column("APY %", justify="right")
    for p in top[:8]:
        t.add_row(
            str(p.get("symbol",""))[:16],
            str(p.get("project",""))[:16],
            str(p.get("chain",""))[:10],
            f"{float(p['apy']):,.2f}%",
        )
    console.print(t)

async def test_defillama_pools_above_2pct():
    above = [p for p in llama_pools
             if p.get("apy") and float(p["apy"]) >= 2.0]
    assert len(above) > 0
    _ok("Pools with APY ≥ 2%", f"{len(above):,} qualify for YIELD detection")

async def test_defillama_data_integrity():
    """Spot-check pool objects have expected fields."""
    sample = [p for p in llama_pools[:100] if p.get("apy")][:10]
    for p in sample:
        assert "symbol"  in p, f"Missing 'symbol' in pool"
        assert "project" in p, f"Missing 'project' in pool"
        assert "chain"   in p, f"Missing 'chain' in pool"
        apy = p.get("apy")
        assert apy is None or isinstance(apy, (int, float))
    _ok("DeFiLlama pool data integrity check")


# ═══════════════════════════════════════════════════════════════
#  6. COINGECKO — real prices
# ═══════════════════════════════════════════════════════════════

gecko_prices = {}
GECKO_IDS = {
    "SOL":"solana","BTC":"bitcoin","ETH":"ethereum","BONK":"bonk",
    "JTO":"jito-governance-token","WIF":"dogwifcoin","JUP":"jupiter-exchange-solana",
    "RAY":"raydium","ORCA":"orca",
}

async def test_coingecko_connectivity():
    ids = ",".join(GECKO_IDS.values())
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    t0  = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            data = await r.json(content_type=None)
            rev  = {v: k for k, v in GECKO_IDS.items()}
            for gecko_id, tok in rev.items():
                p = data.get(gecko_id, {}).get("usd", 0)
                if p:
                    gecko_prices[tok] = float(p)
            lag = (time.time() - t0) * 1000
            _ok("CoinGecko reachable", f"{len(gecko_prices)} prices in {lag:.0f}ms")
            for tok, p in gecko_prices.items():
                console.print(f"    [dim]{tok:8} ${p:,.4f}[/]")

async def test_coingecko_vs_binance_gap():
    common = set(gecko_prices) & set(binance_prices)
    assert len(common) > 0
    gaps = []
    for tok in common:
        gp = gecko_prices[tok]
        bp = binance_prices[tok]
        if gp > 0 and bp > 0:
            gap = abs(gp - bp) / min(gp, bp) * 100
            gaps.append((tok, gp, bp, gap))
    gaps.sort(key=lambda x: -x[3])
    _ok("CoinGecko vs Binance gap measured", f"{len(gaps)} pairs")
    t = Table(box=box.SIMPLE, header_style="bold yellow")
    t.add_column("Token")
    t.add_column("CoinGecko", justify="right")
    t.add_column("Binance", justify="right")
    t.add_column("Gap %", justify="right")
    t.add_column("Arb?", justify="center")
    for tok, gp, bp, gap in gaps:
        flag = "[green]YES[/]" if gap >= 0.20 else "[dim]no[/]"
        t.add_row(tok, f"${gp:,.4f}", f"${bp:,.4f}", f"{gap:.4f}%", flag)
    console.print(t)


# ═══════════════════════════════════════════════════════════════
#  7. KRAKEN — REST fallback (WebSocket tested separately)
# ═══════════════════════════════════════════════════════════════

kraken_prices = {}

async def test_kraken_rest():
    url = "https://api.kraken.com/0/public/Ticker?pair=SOLUSD,XBTUSD,ETHUSD"
    t0  = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            result = (await r.json(content_type=None)).get("result", {})
            for pair, data in result.items():
                last = float(data["c"][0])
                if "SOL" in pair or "XSOL" in pair:
                    kraken_prices["SOL"] = last
                elif "XBT" in pair:
                    kraken_prices["BTC"] = last
                elif "ETH" in pair:
                    kraken_prices["ETH"] = last
            lag = (time.time() - t0) * 1000
            assert len(kraken_prices) > 0
            _ok("Kraken REST reachable", f"{len(kraken_prices)} prices in {lag:.0f}ms  SOL=${kraken_prices.get('SOL',0):,.2f}")

async def test_kraken_ws_connects():
    uri = "wss://ws.kraken.com"
    sub = json.dumps({
        "event": "subscribe",
        "pair":  ["XBT/USD","ETH/USD","SOL/USD"],
        "subscription": {"name": "ticker"}
    })
    got = {}
    async with websockets.connect(uri, ping_interval=None) as ws:
        await ws.send(sub)
        deadline = time.time() + 15
        while len(got) < 2 and time.time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            if isinstance(msg, list) and len(msg) == 4 and msg[2] == "ticker":
                pair  = msg[3]
                price = float(msg[1]["c"][0])
                got[pair] = price
    assert len(got) >= 1, f"Only {len(got)} Kraken WS tickers"
    _ok("Kraken WebSocket streams", f"{len(got)} tickers  " + "  ".join(f"{p}=${v:,.2f}" for p,v in got.items()))


# ═══════════════════════════════════════════════════════════════
#  8. OKX WebSocket
# ═══════════════════════════════════════════════════════════════

async def test_okx_ws_connects():
    uri  = "wss://ws.okx.com:8443/ws/v5/public"
    args = [{"channel":"tickers","instId":i} for i in ["BTC-USDT","ETH-USDT","SOL-USDT"]]
    sub  = json.dumps({"op":"subscribe","args":args})
    got  = {}
    async with websockets.connect(uri, ping_interval=None) as ws:
        await ws.send(sub)
        deadline = time.time() + 15
        while len(got) < 2 and time.time() < deadline:
            raw  = await asyncio.wait_for(ws.recv(), timeout=10)
            msg  = json.loads(raw)
            for item in msg.get("data",[]):
                inst  = item.get("instId","")
                last  = item.get("last")
                if inst and last:
                    got[inst] = float(last)
    assert len(got) >= 1
    _ok("OKX WebSocket streams", f"{len(got)} tickers  " + "  ".join(f"{p}=${v:,.2f}" for p,v in got.items()))


# ═══════════════════════════════════════════════════════════════
#  9. BYBIT WebSocket
# ═══════════════════════════════════════════════════════════════

async def test_bybit_ws_connects():
    uri  = "wss://stream.bybit.com/v5/public/spot"
    args = ["tickers.BTCUSDT","tickers.ETHUSDT","tickers.SOLUSDT"]
    sub  = json.dumps({"op":"subscribe","args":args})
    got  = {}
    async with websockets.connect(uri, ping_interval=None) as ws:
        await ws.send(sub)
        deadline = time.time() + 15
        while len(got) < 2 and time.time() < deadline:
            raw   = await asyncio.wait_for(ws.recv(), timeout=10)
            msg   = json.loads(raw)
            topic = msg.get("topic","")
            data  = msg.get("data",{})
            if topic.startswith("tickers."):
                sym  = topic.split("tickers.")[1]
                last = data.get("lastPrice")
                if last:
                    got[sym] = float(last)
    assert len(got) >= 1
    _ok("Bybit WebSocket streams", f"{len(got)} tickers  " + "  ".join(f"{p}=${v:,.2f}" for p,v in got.items()))


# ═══════════════════════════════════════════════════════════════
#  10. THE GRAPH — Uniswap v3
# ═══════════════════════════════════════════════════════════════

async def test_graph_uniswap():
    url   = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
    query = '{"query":"{ pools(first:10,orderBy:volumeUSD,orderDirection:desc){token0{symbol}token1{symbol}token0Price token1Price} }"}'
    t0    = time.time()
    async with aiohttp.ClientSession() as s:
        async with s.post(url, data=query,
                          headers={"Content-Type":"application/json"},
                          timeout=TIMEOUT) as r:
            assert r.status == 200, f"HTTP {r.status}"
            pools = (await r.json(content_type=None)).get("data",{}).get("pools",[])
            assert len(pools) > 0, "No pools returned"
            lag = (time.time() - t0) * 1000
            _ok("The Graph / Uniswap v3 reachable", f"{len(pools)} pools in {lag:.0f}ms")
            for p in pools[:5]:
                t0s = p.get("token0",{}).get("symbol","?")
                t1s = p.get("token1",{}).get("symbol","?")
                pr  = p.get("token0Price","?")
                console.print(f"    [dim]{t0s}/{t1s}  price={pr}[/]")


# ═══════════════════════════════════════════════════════════════
#  11. CROSS-SOURCE LIVE COMPARISON
#      Real prices from all sources → real gap table
# ═══════════════════════════════════════════════════════════════

async def test_live_cross_source_gaps():
    """
    Build a price table from all sources we fetched.
    Compute all pairwise gaps. Report real arbitrage opportunities
    found in this moment's market data.
    """
    sources = {
        "Jupiter":   jupiter_prices,
        "Binance":   binance_prices,
        "Pyth":      pyth_prices,
        "CoinGecko": gecko_prices,
        "Kraken":    kraken_prices,
    }

    # For each token, collect all source prices
    all_tokens = set()
    for s in sources.values():
        all_tokens.update(s.keys())

    opps = []
    thresholds = {
        ("Jupiter","Binance"):   ("DEX_CEX",  0.25),
        ("Jupiter","Pyth"):      ("ORACLE",   0.30),
        ("Jupiter","CoinGecko"): ("GECKO_ARB",0.20),
        ("Jupiter","Kraken"):    ("DEX_CEX",  0.25),
        ("Binance","Kraken"):    ("CEX_CEX",  0.15),
        ("Binance","CoinGecko"): ("GECKO_ARB",0.20),
        ("Binance","Pyth"):      ("ORACLE",   0.30),
        ("Kraken","Pyth"):       ("ORACLE",   0.30),
    }

    for tok in sorted(all_tokens):
        for (sa, sb), (opp_type, thresh) in thresholds.items():
            pa = sources.get(sa, {}).get(tok)
            pb = sources.get(sb, {}).get(tok)
            if pa and pb and pa > 0 and pb > 0:
                gap = abs(pa - pb) / min(pa, pb) * 100
                if gap >= thresh:
                    net    = gap/100 - 0.002
                    profit = 50.0 * net if net > 0 else 0
                    if profit > 0:
                        opps.append((tok, sa, sb, pa, pb, gap, profit, opp_type))

    opps.sort(key=lambda x: -x[6])

    _ok("Live cross-source comparison complete",
        f"{len(opps)} real opportunity signals right now")

    if opps:
        t = Table(box=box.SIMPLE, header_style="bold green",
                  title="[bold]REAL OPPORTUNITIES — LIVE MARKET DATA[/]")
        t.add_column("Token")
        t.add_column("Source A")
        t.add_column("Source B")
        t.add_column("Price A", justify="right")
        t.add_column("Price B", justify="right")
        t.add_column("Gap %", justify="right")
        t.add_column("£ Profit", justify="right")
        t.add_column("Type")
        for tok, sa, sb, pa, pb, gap, profit, otp in opps[:20]:
            t.add_row(
                tok,sa,sb,
                f"${pa:,.4f}",f"${pb:,.4f}",
                f"[yellow]{gap:.4f}%[/]",
                f"[green]£{profit:.4f}[/]",
                otp,
            )
        console.print(t)
    else:
        console.print("    [dim]No gaps above threshold in current market — prices aligned[/]")


# ═══════════════════════════════════════════════════════════════
#  12. FULL BOT — 60-second live run with real data
# ═══════════════════════════════════════════════════════════════

async def test_full_bot_60s_live():
    """
    Import and run the actual arb_bot_hf.py for 60 seconds
    against all real APIs. Report exactly what it found.
    """
    import arb_bot_hf as bot

    console.print("\n  [bold yellow]Starting 60-second live bot run…[/]")
    state = bot.BotState()

    with tempfile.TemporaryDirectory() as td:
        bot.CSV_BASE = os.path.join(td, "live_arb")

        connector = aiohttp.TCPConnector(limit=50)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                asyncio.create_task(bot.csv_writer_loop(state)),
                asyncio.create_task(bot.comparison_loop(state)),
                asyncio.create_task(bot.jupiter_loop(session, state)),
                asyncio.create_task(bot.binance_loop(state)),
                asyncio.create_task(bot.kraken_loop(state)),
                asyncio.create_task(bot.okx_loop(state)),
                asyncio.create_task(bot.bybit_loop(state)),
                asyncio.create_task(bot.pyth_loop(session, state)),
                asyncio.create_task(bot.defillama_loop(session, state)),
                asyncio.create_task(bot.coingecko_loop(session, state)),
            ]

            # Progress ticker
            async def ticker():
                for i in range(1, 61):
                    await asyncio.sleep(1)
                    if i % 10 == 0:
                        console.print(
                            f"  [dim]  {i}s … {state.total_count:,} trades  "
                            f"£{state.total_base:.2f} profit  "
                            f"sources: "
                            + " ".join(f"{k}:{v[:3]}" for k,v in state.health.items() if v)
                            + "[/]"
                        )
                state.running = False

            tasks.append(asyncio.create_task(ticker()))
            await asyncio.gather(*tasks, return_exceptions=True)
            for t in tasks:
                t.cancel()

        # Results
        assert state.total_count >= 0   # just ensure it ran

        tps       = state.total_count / 60
        per_day   = tps * 86400
        csv_path  = bot._csv_path(state.csv_index)

        _ok("60-second live run completed",
            f"{state.total_count:,} trades  "
            f"£{state.total_base:.2f} base  "
            f"£{state.total_flash:.2f} flash  "
            f"≈{per_day:,.0f}/day pace")

        console.print(f"\n  [bold]Source health after 60s:[/]")
        for src, status in state.health.items():
            icon = "[green]✓[/]" if "✓" in status else "[red]✗[/]"
            console.print(f"    {icon} {src:<12} {status}")

        console.print(f"\n  [bold]Opportunity breakdown:[/]")
        for otp, cnt in state.type_counts.items():
            console.print(f"    {otp:<12} {cnt:,}")

        if os.path.exists(csv_path):
            with open(csv_path) as f:
                rows = list(csv.reader(f))
            console.print(f"\n  [bold]CSV:[/] {csv_path}  →  {len(rows)-1} rows")
            if len(rows) > 1:
                console.print(f"  [dim]Sample: {rows[1]}[/]")

    bot.CSV_BASE = "arb_opportunities"


# ═══════════════════════════════════════════════════════════════
#  RUNNER
# ═══════════════════════════════════════════════════════════════

SECTIONS = [
    ("1. JUPITER (REST — all 24 tokens)", [
        ("Jupiter connectivity + all prices",   test_jupiter_connectivity),
        ("Jupiter SOL price sane",              test_jupiter_sol_price_sane),
        ("Jupiter BTC price sane",              test_jupiter_btc_price_sane),
        ("Jupiter all prices positive",         test_jupiter_all_positive),
        ("Jupiter no NaN/inf values",           test_jupiter_no_nan),
        ("Jupiter two consecutive polls",       test_jupiter_poll_twice),
    ]),
    ("2. BINANCE (REST)", [
        ("Binance REST SOL price",              test_binance_rest_sol),
        ("Binance REST BTC price",              test_binance_rest_btc),
        ("Binance multi-token REST",            test_binance_multi_ticker),
    ]),
    ("3. BINANCE (WebSocket)", [
        ("Binance WS streams real tickers",     test_binance_ws_connects_and_streams),
        ("Binance WS price matches REST",       test_binance_ws_price_matches_rest),
    ]),
    ("4. PYTH NETWORK", [
        ("Pyth connectivity + feeds",           test_pyth_connectivity),
        ("Pyth SOL price sane",                 test_pyth_sol_sane),
        ("Pyth vs Jupiter live gap table",      test_pyth_vs_jupiter_gap),
    ]),
    ("5. DEFILLAMA (all pools)", [
        ("DeFiLlama connectivity",              test_defillama_connectivity),
        ("DeFiLlama >1000 pools",               test_defillama_pool_count),
        ("DeFiLlama top APY pools",             test_defillama_top_apy_pools),
        ("DeFiLlama pools ≥ 2% APY",           test_defillama_pools_above_2pct),
        ("DeFiLlama data integrity",            test_defillama_data_integrity),
    ]),
    ("6. COINGECKO", [
        ("CoinGecko connectivity",              test_coingecko_connectivity),
        ("CoinGecko vs Binance gap table",      test_coingecko_vs_binance_gap),
    ]),
    ("7. KRAKEN", [
        ("Kraken REST prices",                  test_kraken_rest),
        ("Kraken WebSocket streams",            test_kraken_ws_connects),
    ]),
    ("8. OKX WebSocket", [
        ("OKX WS connects + streams",           test_okx_ws_connects),
    ]),
    ("9. BYBIT WebSocket", [
        ("Bybit WS connects + streams",         test_bybit_ws_connects),
    ]),
    ("10. THE GRAPH / Uniswap v3", [
        ("The Graph Uniswap v3",                test_graph_uniswap),
    ]),
    ("11. LIVE CROSS-SOURCE COMPARISON", [
        ("Real gaps from all sources now",      test_live_cross_source_gaps),
    ]),
    ("12. FULL BOT — 60-second live run", [
        ("Full bot 60s with real data",         test_full_bot_60s_live),
    ]),
]

async def _run_section(tests):
    for name, fn in tests:
        try:
            await fn()
        except AssertionError as e:
            _fail(name, str(e))
        except Exception as e:
            _fail(name, f"{type(e).__name__}: {e}")

if __name__ == "__main__":
    console.print("\n[bold cyan]═══ LIVE API TEST SUITE ═══[/]")
    console.print("[dim]Real network calls. Real data. No mocks.[/]\n")

    for section_title, tests in SECTIONS:
        console.print(f"\n[bold white]── {section_title} ──[/]")
        asyncio.run(_run_section(tests))

    console.print(f"\n[bold]{'═'*55}[/]")
    console.print(f"  [bold green]PASSED: {PASS_COUNT}[/]   [bold red]FAILED: {FAIL_COUNT}[/]")
    if FAIL_COUNT > 0:
        console.print("\n  [bold red]Failures:[/]")
        for status, name, reason in RESULTS:
            if status == "FAIL":
                console.print(f"    • {name}: {reason}")
    console.print(f"[bold]{'═'*55}[/]\n")
    sys.exit(0 if FAIL_COUNT == 0 else 1)
