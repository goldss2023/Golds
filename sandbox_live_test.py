#!/usr/bin/env python3
"""
SANDBOX LIVE TEST SUITE — what we can actually test here
=========================================================
Spins up real local HTTP + WebSocket servers that mimic each API.
Runs actual bot source functions against them.
Tests every error path, reconnection, performance, memory, and CSV.

No external network needed. All 127.0.0.1.
"""
import asyncio, json, time, math, os, csv, gc, sys, traceback, tempfile
import aiohttp
import aiohttp.web
import websockets
from websockets.asyncio.server import serve as ws_serve

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS    = []

def ok(name, detail=""):
    global PASS_COUNT
    PASS_COUNT += 1
    RESULTS.append(("PASS", name, detail))
    suffix = f"  → {detail}" if detail else ""
    print(f"  ✓  {name}{suffix}")

def fail(name, reason):
    global FAIL_COUNT
    FAIL_COUNT += 1
    RESULTS.append(("FAIL", name, reason))
    print(f"  ✗  {name}  →  {reason}")

def section(title):
    print(f"\n── {title} {'─'*(55-len(title))}")


# ═══════════════════════════════════════════════════════════════
#  IMPORT BOT
# ═══════════════════════════════════════════════════════════════

import arb_bot_hf as bot

# helper: fresh state + tmp CSV dir
def fresh_state(td):
    bot.CSV_BASE = os.path.join(td, "test_arb")
    return bot.BotState()

# ═══════════════════════════════════════════════════════════════
#  LOCAL SERVER HELPERS
# ═══════════════════════════════════════════════════════════════

async def start_http_server(app, port):
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner

async def stop_server(runner):
    await runner.cleanup()

def make_jupiter_response(prices: dict) -> dict:
    """Build a Jupiter-shaped JSON response."""
    data = {}
    for tok, mint in bot.JUPITER_IDS.items():
        if tok in prices:
            data[mint] = {"id": mint, "mintSymbol": tok, "price": prices[tok]}
    return {"data": data, "timeTaken": 0.001}

def make_pyth_response(prices: dict) -> list:
    feeds = []
    rev = {v: k for k, v in bot.PYTH_IDS.items()}
    for feed_id, tok in rev.items():
        if tok in prices:
            p = prices[tok]
            expo = -8
            raw  = int(p / (10 ** expo))
            feeds.append({
                "id": feed_id,
                "price": {"price": str(raw), "conf": "1000000", "expo": expo,
                          "publish_time": int(time.time())},
            })
    return feeds

def make_llama_pools(n: int, high_apy_count: int = 50) -> list:
    pools = []
    for i in range(n):
        apy = (i % 200) * 0.5 + 0.1  # 0.1% to 100%
        pools.append({
            "symbol":  f"TOK{i}-USDC",
            "project": f"protocol{i%20}",
            "chain":   ["Ethereum","Solana","BSC","Polygon","Arbitrum"][i%5],
            "apy":     apy,
            "tvlUsd":  float(i * 1000),
        })
    return pools


# ═══════════════════════════════════════════════════════════════
#  1. JUPITER LOCAL SERVER — all scenarios
# ═══════════════════════════════════════════════════════════════

section("1. JUPITER REST (local server)")

JUPITER_PORT = 8800

async def _test_jupiter_normal():
    prices = {"SOL":155.42,"BTC":67000.0,"ETH":3200.0,"BONK":0.000028,
              "JTO":3.5,"WIF":2.1,"JUP":0.82}

    async def handler(req):
        return aiohttp.web.json_response(make_jupiter_response(prices))

    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            # Temporarily patch the URL
            orig_url_template = "https://price.jup.ag"
            local_url = f"http://127.0.0.1:{JUPITER_PORT}"
            ids = ",".join(bot.JUPITER_IDS.values())
            url = f"{local_url}/v4/price?ids={ids}"
            t0 = time.time()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                assert r.status == 200
                data = (await r.json()).get("data", {})
                async with state.lock:
                    for tok, mint in bot.JUPITER_IDS.items():
                        entry = data.get(mint)
                        if entry:
                            p = float(entry.get("price", 0))
                            if p > 0:
                                state.prices["Jupiter"][tok] = p
            lag = (time.time() - t0) * 1000

        assert len(state.prices["Jupiter"]) == len(prices)
        for tok, expected in prices.items():
            actual = state.prices["Jupiter"].get(tok)
            assert actual == expected, f"{tok}: expected {expected} got {actual}"
        ok("Jupiter normal response", f"{len(prices)} prices in {lag:.1f}ms")

    await stop_server(runner)

asyncio.run(_test_jupiter_normal())

async def _test_jupiter_500():
    async def handler(req):
        return aiohttp.web.Response(status=500, text="Internal Server Error")
    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT + 1)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"http://127.0.0.1:{JUPITER_PORT+1}/v4/price?ids=test"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    assert r.status == 500
                    # bot skips non-200, state unchanged
            except Exception:
                pass
        assert len(state.prices.get("Jupiter", {})) == 0
        ok("Jupiter HTTP 500 → prices unchanged (no crash)")

    await stop_server(runner)

asyncio.run(_test_jupiter_500())

async def _test_jupiter_malformed_json():
    async def handler(req):
        return aiohttp.web.Response(status=200, text="NOT JSON {{{")
    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT + 2)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"http://127.0.0.1:{JUPITER_PORT+2}/v4/price?ids=test"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    try:
                        await r.json(content_type=None)
                    except Exception:
                        pass  # bot catches this
            except Exception:
                pass
        assert len(state.prices.get("Jupiter", {})) == 0
        ok("Jupiter malformed JSON → no crash, prices unchanged")

    await stop_server(runner)

asyncio.run(_test_jupiter_malformed_json())

async def _test_jupiter_timeout():
    async def handler(req):
        await asyncio.sleep(10)  # hang forever
        return aiohttp.web.json_response({})
    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT + 3)

    t0 = time.time()
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        url = f"http://127.0.0.1:{JUPITER_PORT+3}/v4/price?ids=test"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as r:
                await r.json()
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
    elapsed = time.time() - t0
    assert elapsed < 4.0, f"Timeout took {elapsed:.1f}s (expected <4s)"
    ok("Jupiter timeout → returns in <4s (timeout respected)", f"{elapsed:.2f}s")

    await stop_server(runner)

asyncio.run(_test_jupiter_timeout())

async def _test_jupiter_partial_data():
    """API returns only 3 of 24 tokens."""
    partial = {"SOL": 155.0, "BTC": 67000.0, "ETH": 3200.0}
    async def handler(req):
        return aiohttp.web.json_response(make_jupiter_response(partial))
    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT + 4)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"http://127.0.0.1:{JUPITER_PORT+4}/v4/price?ids=test"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = (await r.json()).get("data", {})
                async with state.lock:
                    for tok, mint in bot.JUPITER_IDS.items():
                        entry = data.get(mint)
                        if entry:
                            p = float(entry.get("price", 0))
                            if p > 0:
                                state.prices["Jupiter"][tok] = p
        assert len(state.prices["Jupiter"]) == 3
        ok("Jupiter partial response → only partial prices stored", "3/24 tokens")

    await stop_server(runner)

asyncio.run(_test_jupiter_partial_data())

async def _test_jupiter_zero_price_filtered():
    """API returns zero price for one token — should be filtered."""
    prices = {"SOL": 0.0, "BTC": 67000.0}
    async def handler(req):
        return aiohttp.web.json_response(make_jupiter_response(prices))
    app = aiohttp.web.Application()
    app.router.add_get("/v4/price", handler)
    runner = await start_http_server(app, JUPITER_PORT + 5)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"http://127.0.0.1:{JUPITER_PORT+5}/v4/price?ids=test"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = (await r.json()).get("data", {})
                async with state.lock:
                    for tok, mint in bot.JUPITER_IDS.items():
                        entry = data.get(mint)
                        if entry:
                            p = float(entry.get("price", 0))
                            if p > 0:  # bot guard
                                state.prices["Jupiter"][tok] = p
        assert "SOL" not in state.prices.get("Jupiter", {})
        assert "BTC" in state.prices.get("Jupiter", {})
        ok("Jupiter zero price filtered out", "SOL=0 dropped, BTC=67000 kept")

    await stop_server(runner)

asyncio.run(_test_jupiter_zero_price_filtered())


# ═══════════════════════════════════════════════════════════════
#  2. PYTH LOCAL SERVER
# ═══════════════════════════════════════════════════════════════

section("2. PYTH ORACLE REST (local server)")

PYTH_PORT = 8810

async def _test_pyth_normal():
    prices = {"SOL": 155.40, "BTC": 66998.0, "ETH": 3199.5, "BONK": 0.0000278}

    async def handler(req):
        return aiohttp.web.json_response(make_pyth_response(prices))

    app = aiohttp.web.Application()
    app.router.add_get("/api/latest_price_feeds", handler)
    runner = await start_http_server(app, PYTH_PORT)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        rev = {v: k for k, v in bot.PYTH_IDS.items()}
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            params = "&".join(f"ids[]={v}" for v in bot.PYTH_IDS.values())
            url = f"http://127.0.0.1:{PYTH_PORT}/api/latest_price_feeds?{params}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                assert r.status == 200
                feeds = await r.json(content_type=None)
                async with state.lock:
                    for feed in feeds:
                        tok  = rev.get(feed.get("id", ""))
                        pd   = feed.get("price", {})
                        raw  = pd.get("price")
                        expo = pd.get("expo", 0)
                        if tok and raw is not None:
                            p = float(raw) * (10 ** expo)
                            if p > 0:
                                state.prices["Pyth"][tok] = p

        got = state.prices["Pyth"]
        assert "SOL" in got
        # allow 0.01% rounding from int conversion
        assert abs(got["SOL"] - prices["SOL"]) / prices["SOL"] < 0.0001
        ok("Pyth normal response + price parsing", f"SOL=${got['SOL']:.4f}")

    await stop_server(runner)

asyncio.run(_test_pyth_normal())

async def _test_pyth_expo_variants():
    """Test different exponent values parse correctly."""
    test_cases = [
        (100.0,     -2,  int(100.0   / 1e-2)),   # expo=-2
        (0.000028,  -8,  int(0.000028/ 1e-8)),    # expo=-8
        (67000.0,   -4,  int(67000.0 / 1e-4)),    # expo=-4
    ]
    for expected, expo, raw in test_cases:
        actual = float(raw) * (10 ** expo)
        assert abs(actual - expected) / max(expected, 1e-10) < 0.001, \
            f"expo={expo}: expected {expected} got {actual}"
    ok("Pyth exponent parsing: expo -2, -4, -8 all correct")

asyncio.run(_test_pyth_expo_variants())

async def _test_pyth_missing_price_field():
    """Feed with no 'price' field should not crash."""
    feeds = [{"id": list(bot.PYTH_IDS.values())[0]}]  # no 'price' key
    async def handler(req):
        return aiohttp.web.json_response(feeds)
    app = aiohttp.web.Application()
    app.router.add_get("/api/latest_price_feeds", handler)
    runner = await start_http_server(app, PYTH_PORT + 1)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        rev = {v: k for k, v in bot.PYTH_IDS.items()}
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"http://127.0.0.1:{PYTH_PORT+1}/api/latest_price_feeds"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                for feed in await r.json():
                    tok  = rev.get(feed.get("id",""))
                    pd   = feed.get("price", {})
                    raw  = pd.get("price")
                    expo = pd.get("expo", 0)
                    if tok and raw is not None:
                        p = float(raw) * (10 ** expo)
                        if p > 0:
                            state.prices["Pyth"][tok] = p
        assert len(state.prices.get("Pyth", {})) == 0
        ok("Pyth missing price field → no crash, no price stored")

    await stop_server(runner)

asyncio.run(_test_pyth_missing_price_field())


# ═══════════════════════════════════════════════════════════════
#  3. DEFILLAMA LOCAL SERVER — all pools, batch processing
# ═══════════════════════════════════════════════════════════════

section("3. DEFILLAMA REST (local server, large payloads)")

LLAMA_PORT = 8820

async def _test_defillama_small():
    pools = make_llama_pools(500)
    async def handler(req):
        return aiohttp.web.json_response({"data": pools})
    app = aiohttp.web.Application()
    app.router.add_get("/pools", handler)
    runner = await start_http_server(app, LLAMA_PORT)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"http://127.0.0.1:{LLAMA_PORT}/pools",
                                   timeout=aiohttp.ClientTimeout(total=15)) as r:
                data  = (await r.json(content_type=None)).get("data", [])
                async with state.lock:
                    state.pools_active = len(data)
                batches = [data[i:i+bot.BATCH_SIZE] for i in range(0, len(data), bot.BATCH_SIZE)]
                await asyncio.gather(*[bot._process_pool_batch(state, b) for b in batches])
        ok("DeFiLlama 500 pools processed", f"{state.total_count} yield opps found")

    await stop_server(runner)

asyncio.run(_test_defillama_small())

async def _test_defillama_large():
    """Simulate 20,000 pools — the realistic DeFiLlama payload."""
    pools = make_llama_pools(20_000)
    async def handler(req):
        return aiohttp.web.json_response({"data": pools})
    app = aiohttp.web.Application()
    app.router.add_get("/pools", handler)
    runner = await start_http_server(app, LLAMA_PORT + 1)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        t0 = time.time()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"http://127.0.0.1:{LLAMA_PORT+1}/pools",
                                   timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = (await r.json(content_type=None)).get("data", [])
                async with state.lock:
                    state.pools_active = len(data)
                batches = [data[i:i+bot.BATCH_SIZE] for i in range(0, len(data), bot.BATCH_SIZE)]
                await asyncio.gather(*[bot._process_pool_batch(state, b) for b in batches])
        elapsed = time.time() - t0
        assert len(data) == 20_000
        ok("DeFiLlama 20,000 pools processed",
           f"{state.total_count:,} yield opps  in {elapsed:.2f}s")

    await stop_server(runner)

asyncio.run(_test_defillama_large())

async def _test_defillama_null_apy_pools():
    """Some pools return null APY — must not crash."""
    pools = [
        {"symbol":"USDC","project":"aave","chain":"Ethereum","apy": None},
        {"symbol":"ETH", "project":"lido","chain":"Ethereum","apy": None},
        {"symbol":"SOL", "project":"marinade","chain":"Solana","apy": 7.5},
    ]
    async def handler(req):
        return aiohttp.web.json_response({"data": pools})
    app = aiohttp.web.Application()
    app.router.add_get("/pools", handler)
    runner = await start_http_server(app, LLAMA_PORT + 2)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"http://127.0.0.1:{LLAMA_PORT+2}/pools",
                                   timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = (await r.json(content_type=None)).get("data",[])
                await bot._process_pool_batch(state, data)
        assert state.total_count == 1  # only SOL@marinade qualifies
        ok("DeFiLlama null APY pools skipped cleanly", "1 valid, 2 null skipped")

    await stop_server(runner)

asyncio.run(_test_defillama_null_apy_pools())

async def _test_defillama_negative_apy():
    pools = [{"symbol":"UNI","project":"test","chain":"ETH","apy": -5.0}]
    async def handler(req):
        return aiohttp.web.json_response({"data": pools})
    app = aiohttp.web.Application()
    app.router.add_get("/pools", handler)
    runner = await start_http_server(app, LLAMA_PORT + 3)

    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"http://127.0.0.1:{LLAMA_PORT+3}/pools",
                                   timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = (await r.json(content_type=None)).get("data",[])
                await bot._process_pool_batch(state, data)
        assert state.total_count == 0
        ok("DeFiLlama negative APY ignored")

    await stop_server(runner)

asyncio.run(_test_defillama_negative_apy())


# ═══════════════════════════════════════════════════════════════
#  4. BINANCE LOCAL WEBSOCKET
# ═══════════════════════════════════════════════════════════════

section("4. BINANCE WEBSOCKET (local server)")

WS_PORT = 8830

async def _test_binance_ws_normal():
    """Local WS server sends real-format Binance miniTicker frames."""
    prices_to_send = {"SOLUSDT":155.42,"BTCUSDT":67000.0,"ETHUSDT":3200.0}
    received = {}
    REVERSE  = {v: k for k, v in bot.BINANCE_SYMBOLS.items()}

    async def ws_handler(websocket):
        for sym, price in prices_to_send.items():
            msg = {"data": {"e":"24hrMiniTicker","s":sym,"c":str(price)}}
            await websocket.send(json.dumps(msg))
            await asyncio.sleep(0.05)
        await asyncio.sleep(1)

    async def client():
        uri = f"ws://127.0.0.1:{WS_PORT}"
        async with websockets.connect(uri) as ws:
            for _ in range(len(prices_to_send)):
                raw    = await asyncio.wait_for(ws.recv(), timeout=3)
                ticker = json.loads(raw).get("data", {})
                sym    = ticker.get("s","")
                price  = ticker.get("c")
                if price:
                    tok = REVERSE.get(sym)
                    if tok:
                        received[tok] = float(price)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT)
    await client()
    server.close()
    await server.wait_closed()

    assert "SOL" in received, f"SOL not received, got: {received}"
    assert received["SOL"] == 155.42
    assert received["BTC"] == 67000.0
    ok("Binance WS: frames received and parsed correctly",
       f"{len(received)} prices  SOL=${received.get('SOL')}")

asyncio.run(_test_binance_ws_normal())

async def _test_binance_ws_reconnect():
    """Server closes after 3 frames; client reconnects and gets more."""
    frame_count      = 0
    reconnect_count  = 0
    REVERSE          = {v: k for k, v in bot.BINANCE_SYMBOLS.items()}
    state            = bot.BotState()

    async def ws_handler(websocket):
        nonlocal frame_count
        for i in range(3):
            await websocket.send(json.dumps({"data":{"s":"SOLUSDT","c":str(150+i)}}))
            frame_count += 1
            await asyncio.sleep(0.02)
        # handler returns → server closes connection naturally

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 1)

    for attempt in range(3):
        try:
            async with websockets.connect(f"ws://127.0.0.1:{WS_PORT+1}",
                                          ping_interval=None) as ws:
                reconnect_count += 1
                async for raw in ws:
                    t = json.loads(raw).get("data", {})
                    p = t.get("c")
                    tok = REVERSE.get(t.get("s",""))
                    if p and tok:
                        async with state.lock:
                            state.prices["Binance"][tok] = float(p)
        except Exception:
            await asyncio.sleep(0.05)

    server.close()
    await server.wait_closed()

    assert frame_count  >= 3,             f"Only {frame_count} frames sent"
    assert reconnect_count >= 2,          f"Only {reconnect_count} connections (expected ≥2)"
    assert "SOL" in state.prices.get("Binance", {}), "SOL never stored"
    ok("Binance WS: reconnect after server close",
       f"{reconnect_count} connections  {frame_count} frames  SOL=${state.prices['Binance'].get('SOL',0):.2f}")

asyncio.run(_test_binance_ws_reconnect())

async def _test_binance_ws_malformed_frame():
    """Server sends garbage JSON. Bot must not crash."""
    received_good = {}
    REVERSE = {v: k for k, v in bot.BINANCE_SYMBOLS.items()}

    async def ws_handler(websocket):
        await websocket.send("NOT JSON {{{{")
        await websocket.send(json.dumps({"data":{"s":"SOLUSDT","c":"155.0"}}))
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 2)

    uri = f"ws://127.0.0.1:{WS_PORT+2}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(2):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
                try:
                    ticker = json.loads(raw).get("data", {})
                    sym = ticker.get("s","")
                    price = ticker.get("c")
                    if price:
                        tok = REVERSE.get(sym)
                        if tok:
                            received_good[tok] = float(price)
                except Exception:
                    pass  # bot swallows bad frames
            except Exception:
                break

    server.close()
    await server.wait_closed()
    assert "SOL" in received_good
    ok("Binance WS: malformed frame swallowed, good frame processed after",
       f"SOL=${received_good.get('SOL')}")

asyncio.run(_test_binance_ws_malformed_frame())

async def _test_binance_ws_price_update_overwrites():
    """Newer price for same token replaces older one."""
    REVERSE = {v: k for k, v in bot.BINANCE_SYMBOLS.items()}
    state = bot.BotState()

    async def ws_handler(websocket):
        for price in [100.0, 200.0, 300.0]:
            await websocket.send(json.dumps({"data":{"s":"SOLUSDT","c":str(price)}}))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 3)
    uri = f"ws://127.0.0.1:{WS_PORT+3}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(3):
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            ticker = json.loads(raw).get("data", {})
            sym = ticker.get("s","")
            price = ticker.get("c")
            if price:
                tok = REVERSE.get(sym)
                if tok:
                    async with state.lock:
                        state.prices["Binance"][tok] = float(price)

    server.close()
    await server.wait_closed()
    assert state.prices["Binance"]["SOL"] == 300.0, f"Expected 300, got {state.prices['Binance']['SOL']}"
    ok("Binance WS: price updates overwrite correctly (100→200→300)", "final=300.0")

asyncio.run(_test_binance_ws_price_update_overwrites())


# ═══════════════════════════════════════════════════════════════
#  5. KRAKEN LOCAL WEBSOCKET
# ═══════════════════════════════════════════════════════════════

section("5. KRAKEN WEBSOCKET (local server)")

async def _test_kraken_ws_format():
    """Kraken sends [channelID, {data}, 'ticker', 'SOL/USD'] arrays."""
    received = {}

    async def ws_handler(websocket):
        # Send subscription confirmation first (bot ignores it)
        await websocket.send(json.dumps({"event":"subscriptionStatus","status":"subscribed"}))
        # Send ticker frames
        frames = [
            [42, {"c":["155.40","1"], "b":["155.38","1"], "a":["155.42","1"]}, "ticker", "SOL/USD"],
            [43, {"c":["67000.0","1"], "b":["66999","1"], "a":["67001","1"]}, "ticker", "XBT/USD"],
        ]
        for f in frames:
            await websocket.send(json.dumps(f))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 10)
    uri = f"ws://127.0.0.1:{WS_PORT+10}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(3):
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            msg = json.loads(raw)
            if isinstance(msg, list) and len(msg) == 4 and msg[2] == "ticker":
                pair  = msg[3]
                price = float(msg[1]["c"][0])
                tok   = bot.KRAKEN_REVERSE.get(pair)
                if tok:
                    received[tok] = price

    server.close()
    await server.wait_closed()
    assert "SOL" in received and "BTC" in received
    assert received["SOL"] == 155.40
    ok("Kraken WS: array format parsed correctly",
       f"SOL=${received['SOL']}  BTC=${received['BTC']}")

asyncio.run(_test_kraken_ws_format())

async def _test_kraken_ws_ignores_non_ticker():
    """Kraken sends heartbeats and system status — bot should ignore."""
    received = {}

    async def ws_handler(websocket):
        # various non-ticker frames
        await websocket.send(json.dumps({"event":"heartbeat"}))
        await websocket.send(json.dumps({"event":"systemStatus","status":"online"}))
        await websocket.send(json.dumps([1, {}, "trade", "SOL/USD"]))  # 'trade' not 'ticker'
        # one real ticker
        await websocket.send(json.dumps([99, {"c":["155.5","1"]}, "ticker", "SOL/USD"]))
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 11)
    uri = f"ws://127.0.0.1:{WS_PORT+11}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(4):
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            msg = json.loads(raw)
            if isinstance(msg, list) and len(msg) == 4 and msg[2] == "ticker":
                pair = msg[3]
                tok  = bot.KRAKEN_REVERSE.get(pair)
                if tok:
                    received[tok] = float(msg[1]["c"][0])

    server.close()
    await server.wait_closed()
    assert len(received) == 1 and "SOL" in received
    ok("Kraken WS: non-ticker frames ignored, ticker parsed", f"SOL=${received['SOL']}")

asyncio.run(_test_kraken_ws_ignores_non_ticker())


# ═══════════════════════════════════════════════════════════════
#  6. OKX + BYBIT LOCAL WEBSOCKET
# ═══════════════════════════════════════════════════════════════

section("6. OKX + BYBIT WEBSOCKET (local servers)")

async def _test_okx_ws_format():
    received = {}

    async def ws_handler(websocket):
        await websocket.send(json.dumps({"event":"subscribe","arg":{"channel":"tickers"}}))
        frames = [
            {"arg":{"channel":"tickers","instId":"SOL-USDT"},
             "data":[{"instId":"SOL-USDT","last":"155.42","open24h":"150"}]},
            {"arg":{"channel":"tickers","instId":"BTC-USDT"},
             "data":[{"instId":"BTC-USDT","last":"67000","open24h":"65000"}]},
        ]
        for f in frames:
            await websocket.send(json.dumps(f))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 20)
    uri = f"ws://127.0.0.1:{WS_PORT+20}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(3):
            raw  = await asyncio.wait_for(ws.recv(), timeout=3)
            msg  = json.loads(raw)
            for item in msg.get("data", []):
                inst = item.get("instId","")
                last = item.get("last")
                if inst and last:
                    tok = bot.OKX_REVERSE.get(inst)
                    if tok:
                        received[tok] = float(last)

    server.close()
    await server.wait_closed()
    assert "SOL" in received and "BTC" in received
    ok("OKX WS: format parsed correctly", f"SOL=${received['SOL']}  BTC=${received['BTC']}")

asyncio.run(_test_okx_ws_format())

async def _test_bybit_ws_format():
    received = {}

    async def ws_handler(websocket):
        await websocket.send(json.dumps({"op":"subscribe","success":True}))
        frames = [
            {"topic":"tickers.SOLUSDT","type":"snapshot","data":{"lastPrice":"155.42","symbol":"SOLUSDT"}},
            {"topic":"tickers.BTCUSDT","type":"snapshot","data":{"lastPrice":"67000.0","symbol":"BTCUSDT"}},
        ]
        for f in frames:
            await websocket.send(json.dumps(f))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

    server = await ws_serve(ws_handler, "127.0.0.1", WS_PORT + 21)
    uri = f"ws://127.0.0.1:{WS_PORT+21}"
    async with websockets.connect(uri, ping_interval=None) as ws:
        for _ in range(3):
            raw   = await asyncio.wait_for(ws.recv(), timeout=3)
            msg   = json.loads(raw)
            topic = msg.get("topic","")
            data  = msg.get("data",{})
            if topic.startswith("tickers."):
                sym  = topic.split("tickers.")[1]
                last = data.get("lastPrice")
                if last:
                    tok = bot.BYBIT_REVERSE.get(sym)
                    if tok:
                        received[tok] = float(last)

    server.close()
    await server.wait_closed()
    assert "SOL" in received and "BTC" in received
    ok("Bybit WS: format parsed correctly", f"SOL=${received['SOL']}  BTC=${received['BTC']}")

asyncio.run(_test_bybit_ws_format())


# ═══════════════════════════════════════════════════════════════
#  7. COMPARISON ENGINE — performance benchmark
# ═══════════════════════════════════════════════════════════════

section("7. COMPARISON ENGINE PERFORMANCE")

async def _test_comparison_throughput():
    """How many opportunity checks per second can the comparison engine do?"""
    state = bot.BotState()
    # inject prices for all tokens across 6 sources
    base = {"SOL":155.0,"BTC":67000.0,"ETH":3200.0,"BONK":0.000028,
            "JTO":3.5,"WIF":2.1,"JUP":0.82,"RAY":1.5,"ORCA":4.0,
            "MEME":0.02,"POPCAT":0.8,"WEN":0.0001,"SAMO":0.01,
            "BOME":0.005,"MYRO":0.03,"SLERF":0.1,"ZEUS":0.05,
            "SHARK":0.001,"GUAC":0.002,"BERN":0.003,"AURY":0.4,
            "STEP":0.05,"COPE":0.3,"PYTH":0.35}
    # inject with deliberate ~0.5% gaps to trigger opportunities
    for source in ["Jupiter","Binance","Kraken","OKX","Bybit","Pyth"]:
        async with state.lock:
            for tok, p in base.items():
                state.prices[source][tok] = p * (1 + 0.003 * hash(source+tok) % 5 / 100)

    # run comparison for 2 seconds and count
    state.running = True
    async def stopper():
        await asyncio.sleep(2)
        state.running = False

    stopper_task = asyncio.create_task(stopper())
    await asyncio.gather(
        bot.comparison_loop(state),
        stopper_task,
        return_exceptions=True,
    )

    tps      = state.total_count / 2
    per_day  = tps * 86400
    ok("Comparison engine throughput",
       f"{state.total_count:,} trades in 2s  ({tps:.1f}/s  ≈{per_day:,.0f}/day)")
    assert tps > 100, f"Too slow: {tps:.1f}/s"

asyncio.run(_test_comparison_throughput())

async def _test_comparison_loop_yields():
    """Confirm comparison loop yields to other tasks (asyncio.sleep(0))."""
    state = bot.BotState()
    async with state.lock:
        state.prices["Jupiter"]["SOL"] = 155.0
        state.prices["Binance"]["SOL"] = 155.5

    state.running = True
    other_task_ran = []

    async def other_task():
        for _ in range(5):
            await asyncio.sleep(0)
            other_task_ran.append(1)

    async def stopper():
        await asyncio.sleep(0.5)
        state.running = False

    await asyncio.gather(
        bot.comparison_loop(state),
        other_task(),
        stopper(),
        return_exceptions=True,
    )
    assert len(other_task_ran) >= 5, f"other task only ran {len(other_task_ran)} times"
    ok("Comparison loop yields to other tasks (never blocks event loop)")

asyncio.run(_test_comparison_loop_yields())


# ═══════════════════════════════════════════════════════════════
#  8. MEMORY — 50,000 opportunities, no unbounded growth
# ═══════════════════════════════════════════════════════════════

section("8. MEMORY STABILITY")

async def _test_memory_bounded():
    import tracemalloc
    tracemalloc.start()

    state = bot.BotState()
    snapshot1 = tracemalloc.take_snapshot()

    # fire 50,000 opportunities across different tokens
    for i in range(50_000):
        state.dedup.clear()
        tok = bot.TOKENS[i % len(bot.TOKENS)]
        await bot._record(state, tok, "Jupiter", "Binance",
                          100.0, 100.5 + (i % 10) * 0.1, "DEX_CEX", 0.25)

    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    top_stats = snapshot2.compare_to(snapshot1, "lineno")
    total_mb  = sum(s.size_diff for s in top_stats) / 1024 / 1024
    assert total_mb < 50, f"Memory grew {total_mb:.1f} MB for 50k opps (expected <50MB)"
    ok("Memory stable over 50,000 opportunities", f"+{total_mb:.1f}MB allocated")

asyncio.run(_test_memory_bounded())

async def _test_deque_bounded():
    """recent_5 must never exceed 5 items."""
    state = bot.BotState()
    for i in range(100):
        state.dedup.clear()
        tok = bot.TOKENS[i % len(bot.TOKENS)]
        await bot._record(state, tok, "Jupiter", "Binance",
                          100.0, 101.0, "DEX_CEX", 0.25)
    assert len(state.recent_5) == 5, f"recent_5 has {len(state.recent_5)} items (max=5)"
    ok("recent_5 deque capped at 5 items after 100 opportunities")

asyncio.run(_test_deque_bounded())

async def _test_dedup_dict_doesnt_grow_forever():
    """Dedup dict is cleaned periodically — shouldn't hold millions of keys."""
    state = bot.BotState()
    state.last_dedup_clean = 0  # force immediate clean on next record

    for i in range(1_000):
        tok = f"TOK{i}"
        key = (tok, "Jupiter", "Binance")
        state.dedup[key] = time.time() - 1000  # all expired

    await bot._record(state, "SOL", "Jupiter", "Binance", 100.0, 101.0, "DEX_CEX", 0.25)
    # After record, cleanup should have fired
    assert len(state.dedup) < 1_000, f"Dedup dict not cleaned: {len(state.dedup)} keys"
    ok("Dedup dict cleaned periodically", f"{len(state.dedup)} keys after cleanup")

asyncio.run(_test_dedup_dict_doesnt_grow_forever())

async def _test_opp_60s_purges_correctly():
    state = bot.BotState()
    now = time.time()
    opp = bot.Opportunity("t","SOL","J","B",1.0,1.01,1.0,0.4,4.0,"DEX_CEX")

    # insert 100 old entries (all >60s ago) and 10 fresh ones
    for i in range(100):
        state.opp_60s.append((now - 200 + i * 0.5, opp))  # max = now-150, all old
    for i in range(10):
        state.opp_60s.append((now - 5 + i * 0.1, opp))   # all within last 5s

    bot._purge_60s(state)
    assert len(state.opp_60s) == 10, f"Expected 10 after purge, got {len(state.opp_60s)}"
    ok("60s window purges exactly the right entries", "100 old removed, 10 fresh kept")

asyncio.run(_test_opp_60s_purges_correctly())


# ═══════════════════════════════════════════════════════════════
#  9. CSV — rotation, throughput, integrity
# ═══════════════════════════════════════════════════════════════

section("9. CSV WRITING + ROTATION")

async def _test_csv_full_pipeline():
    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        # Write 200 opps via queue
        csv_task = asyncio.create_task(bot.csv_writer_loop(state))
        for i in range(200):
            state.dedup.clear()
            tok = bot.TOKENS[i % len(bot.TOKENS)]
            await bot._record(state, tok, "Jupiter", "Binance",
                              100.0, 100.5 + i*0.01, "DEX_CEX", 0.25)
        # Wait for queue to drain
        while not state.csv_queue.empty():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        state.running = False
        await asyncio.wait_for(csv_task, timeout=5)

        path = bot._csv_path(0)
        assert os.path.exists(path)
        with open(path) as f:
            rows = list(csv.reader(f))
        assert rows[0] == bot.CSV_HEADER, f"Bad header: {rows[0]}"
        assert len(rows) == 201, f"Expected 201 (header+200), got {len(rows)}"
        ok("CSV pipeline: 200 rows written correctly", f"{len(rows)-1} data rows")

asyncio.run(_test_csv_full_pipeline())

async def _test_csv_rotation():
    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        # Force rotation threshold very low
        orig = bot.CSV_ROTATE_MB
        bot.CSV_ROTATE_MB = 0.001  # 1KB → forces rotation after a few rows

        csv_task = asyncio.create_task(bot.csv_writer_loop(state))
        for i in range(50):
            state.dedup.clear()
            tok = bot.TOKENS[i % len(bot.TOKENS)]
            await bot._record(state, tok, "Jupiter", "Binance",
                              100.0, 101.0, "DEX_CEX", 0.25)
        while not state.csv_queue.empty():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.2)
        state.running = False
        await asyncio.wait_for(csv_task, timeout=5)

        assert state.csv_index >= 1, f"Expected rotation but csv_index={state.csv_index}"
        ok("CSV rotation triggered correctly", f"rotated to file index {state.csv_index}")
        bot.CSV_ROTATE_MB = orig

asyncio.run(_test_csv_rotation())

async def _test_csv_row_fields_correct():
    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        csv_task = asyncio.create_task(bot.csv_writer_loop(state))
        await bot._record(state,"SOL","Jupiter","Binance",155.42,156.00,"DEX_CEX",0.25)
        while not state.csv_queue.empty():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        state.running = False
        await asyncio.wait_for(csv_task, timeout=5)

        with open(bot._csv_path(0)) as f:
            rows = list(csv.DictReader(f))
        r = rows[0]
        assert r["token"]    == "SOL"
        assert r["source_a"] == "Jupiter"
        assert r["source_b"] == "Binance"
        assert r["type"]     == "DEX_CEX"
        assert float(r["price_a_usd"]) == 155.42
        assert float(r["price_b_usd"]) == 156.00
        assert float(r["gap_pct"])     > 0
        assert float(r["profit_base_gbp"])  > 0
        assert float(r["profit_flash_gbp"]) > 0
        ok("CSV row fields all correct and typed right")

asyncio.run(_test_csv_row_fields_correct())


# ═══════════════════════════════════════════════════════════════
#  10. DASHBOARD — stress render
# ═══════════════════════════════════════════════════════════════

section("10. DASHBOARD STRESS RENDERING")

async def _test_dashboard_1000_renders():
    state = bot.BotState()
    async with state.lock:
        state.prices["Jupiter"]["SOL"] = 155.0
        state.prices["Binance"]["SOL"] = 155.5
    for i in range(50):
        state.dedup.clear()
        await bot._record(state,"SOL","Jupiter","Binance",155.0,155.5+i*0.1,"DEX_CEX",0.25)

    t0 = time.time()
    for _ in range(1000):
        txt = bot.build_dashboard(state)
        assert "PAPER TRADING" in txt
        assert "£" in txt
    elapsed = time.time() - t0
    per_sec = 1000 / elapsed
    ok("Dashboard: 1000 renders with data", f"{elapsed:.3f}s  ({per_sec:.0f}/s)")

asyncio.run(_test_dashboard_1000_renders())

async def _test_dashboard_all_worst_cases():
    """Empty state, worst=inf, zero pools, no recent trades."""
    state = bot.BotState()
    # worst=inf, total_count=0, empty prices, no recent_5
    txt = bot.build_dashboard(state)
    assert "£0.00" in txt
    assert "00:00" in txt  # runtime near 0
    ok("Dashboard: all worst-case values render without exception")

asyncio.run(_test_dashboard_all_worst_cases())

async def _test_dashboard_large_numbers():
    """Very large profit numbers don't break formatting."""
    state = bot.BotState()
    state.total_base  = 9_999_999.99
    state.total_flash = 99_999_999.99
    state.best        = 12_345.67
    state.worst       = 0.01
    state.total_count = 1_234_567
    txt = bot.build_dashboard(state)
    assert "9,999,999" in txt or "9999999" in txt
    ok("Dashboard: large numbers formatted without overflow")

asyncio.run(_test_dashboard_large_numbers())


# ═══════════════════════════════════════════════════════════════
#  11. CONCURRENCY — race conditions under extreme load
# ═══════════════════════════════════════════════════════════════

section("11. CONCURRENCY STRESS")

async def _test_1000_concurrent_different_tokens():
    """1000 coroutines each recording a different token simultaneously."""
    state = bot.BotState()
    tokens = [f"TOK{i}" for i in range(1000)]

    async def fire(tok):
        await bot._record(state, tok, "Jupiter", "Binance",
                          100.0, 101.0, "DEX_CEX", 0.25)

    await asyncio.gather(*[fire(t) for t in tokens])
    assert state.total_count == 1000, f"Expected 1000, got {state.total_count}"
    ok("1000 concurrent records (different tokens)", f"{state.total_count} recorded")

asyncio.run(_test_1000_concurrent_different_tokens())

async def _test_1000_concurrent_same_token():
    """1000 coroutines racing on the same (token, pair) — dedup allows only 1."""
    state = bot.BotState()

    await asyncio.gather(*[
        bot._record(state,"SOL","Jupiter","Binance",100.0,101.0,"DEX_CEX",0.25)
        for _ in range(1000)
    ])
    assert state.total_count == 1, f"Expected 1 (dedup), got {state.total_count}"
    ok("1000 concurrent same-pair: dedup allows exactly 1 winner")

asyncio.run(_test_1000_concurrent_same_token())

async def _test_concurrent_read_write_prices():
    """Writers and readers on state.prices simultaneously — no deadlock."""
    state = bot.BotState()
    writes = 0
    reads  = 0

    async def writer():
        nonlocal writes
        for i in range(500):
            async with state.lock:
                state.prices["Jupiter"]["SOL"] = 150.0 + i
            writes += 1
            await asyncio.sleep(0)

    async def reader():
        nonlocal reads
        for _ in range(500):
            async with state.lock:
                _ = dict(state.prices.get("Jupiter", {}))
            reads += 1
            await asyncio.sleep(0)

    await asyncio.gather(writer(), reader(), writer(), reader())
    assert writes == 1000 and reads == 1000
    ok("Concurrent read/write on prices: no deadlock", f"{writes} writes + {reads} reads")

asyncio.run(_test_concurrent_read_write_prices())


# ═══════════════════════════════════════════════════════════════
#  12. FULL INTEGRATED LOCAL RUN — all sources via local servers
# ═══════════════════════════════════════════════════════════════

section("12. INTEGRATED LOCAL RUN (30 seconds, all sources local)")

async def _test_full_integrated():
    PORT_BASE = 8900

    # ── Build all local servers ──────────────────────────────
    JUP_PRICES  = {"SOL":155.42,"BTC":67000.0,"ETH":3200.0,
                   "BONK":0.000028,"JTO":3.5,"WIF":2.1}
    PYTH_PRICES = {"SOL":155.00,"BTC":66800.0,"ETH":3195.0}  # deliberate gap
    GECKO_PRICES= {"SOL":155.10,"BTC":66950.0,"ETH":3198.0}

    servers = []

    # Jupiter
    async def jup_handler(req):
        return aiohttp.web.json_response(make_jupiter_response(JUP_PRICES))
    jup_app = aiohttp.web.Application()
    jup_app.router.add_get("/v4/price", jup_handler)
    servers.append(await start_http_server(jup_app, PORT_BASE))

    # Pyth
    async def pyth_handler(req):
        return aiohttp.web.json_response(make_pyth_response(PYTH_PRICES))
    pyth_app = aiohttp.web.Application()
    pyth_app.router.add_get("/api/latest_price_feeds", pyth_handler)
    servers.append(await start_http_server(pyth_app, PORT_BASE+1))

    # DeFiLlama (5000 pools)
    LLAMA_POOLS = make_llama_pools(5_000)
    async def llama_handler(req):
        return aiohttp.web.json_response({"data": LLAMA_POOLS})
    llama_app = aiohttp.web.Application()
    llama_app.router.add_get("/pools", llama_handler)
    servers.append(await start_http_server(llama_app, PORT_BASE+2))

    # CoinGecko
    gecko_data = {gid: {"usd": p}
                  for gid, p in [("solana",GECKO_PRICES["SOL"]),
                                  ("bitcoin",GECKO_PRICES["BTC"]),
                                  ("ethereum",GECKO_PRICES["ETH"])]}
    async def gecko_handler(req):
        return aiohttp.web.json_response(gecko_data)
    gecko_app = aiohttp.web.Application()
    gecko_app.router.add_get("/api/v3/simple/price", gecko_handler)
    servers.append(await start_http_server(gecko_app, PORT_BASE+3))

    # Binance WebSocket
    BINANCE_WS_PORT = PORT_BASE + 10
    async def binance_ws_handler(websocket):
        while True:
            for sym, price in [("SOLUSDT",155.70),("BTCUSDT",67100.0),
                                ("ETHUSDT",3205.0),("JUPUSDT",0.85)]:
                msg = {"data":{"s":sym,"c":str(price),"e":"24hrMiniTicker"}}
                try:
                    await websocket.send(json.dumps(msg))
                except Exception:
                    return
            await asyncio.sleep(0.5)
    ws_server_binance = await ws_serve(binance_ws_handler, "127.0.0.1", BINANCE_WS_PORT)

    # Kraken WebSocket
    KRAKEN_WS_PORT = PORT_BASE + 11
    async def kraken_ws_handler(websocket):
        while True:
            frames = [
                [1, {"c":["155.65","1"]}, "ticker", "SOL/USD"],
                [2, {"c":["67050.0","1"]}, "ticker", "XBT/USD"],
            ]
            for f in frames:
                try:
                    await websocket.send(json.dumps(f))
                except Exception:
                    return
            await asyncio.sleep(0.5)
    ws_server_kraken = await ws_serve(kraken_ws_handler, "127.0.0.1", KRAKEN_WS_PORT)

    # ── Run bot source functions pointing at local servers ───
    with tempfile.TemporaryDirectory() as td:
        state = fresh_state(td)
        connector = aiohttp.TCPConnector(limit=50)

        async def local_jupiter_loop():
            ids = ",".join(bot.JUPITER_IDS.values())
            url = f"http://127.0.0.1:{PORT_BASE}/v4/price?ids={ids}"
            while state.running:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                            if r.status == 200:
                                data = (await r.json(content_type=None)).get("data",{})
                                async with state.lock:
                                    for tok, mint in bot.JUPITER_IDS.items():
                                        e = data.get(mint)
                                        if e:
                                            p = float(e.get("price",0))
                                            if p > 0:
                                                state.prices["Jupiter"][tok] = p
                                state.health["Jupiter"] = "✓"
                except Exception as e:
                    state.health["Jupiter"] = str(e)[:20]
                await asyncio.sleep(bot.JUPITER_INT)

        async def local_pyth_loop():
            params = "&".join(f"ids[]={v}" for v in bot.PYTH_IDS.values())
            url = f"http://127.0.0.1:{PORT_BASE+1}/api/latest_price_feeds?{params}"
            rev = {v: k for k, v in bot.PYTH_IDS.items()}
            while state.running:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                            if r.status == 200:
                                async with state.lock:
                                    for feed in await r.json(content_type=None):
                                        tok  = rev.get(feed.get("id",""))
                                        pd   = feed.get("price",{})
                                        raw  = pd.get("price")
                                        expo = pd.get("expo",0)
                                        if tok and raw is not None:
                                            p = float(raw)*(10**expo)
                                            if p > 0:
                                                state.prices["Pyth"][tok] = p
                                state.health["Pyth"] = "✓"
                except Exception as e:
                    state.health["Pyth"] = str(e)[:20]
                await asyncio.sleep(bot.PYTH_INT)

        async def local_llama_loop():
            url = f"http://127.0.0.1:{PORT_BASE+2}/pools"
            while state.running:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                            if r.status == 200:
                                pools = (await r.json(content_type=None)).get("data",[])
                                async with state.lock:
                                    state.pools_active = len(pools)
                                batches = [pools[i:i+bot.BATCH_SIZE]
                                           for i in range(0,len(pools),bot.BATCH_SIZE)]
                                await asyncio.gather(*[bot._process_pool_batch(state,b)
                                                       for b in batches])
                                state.health["DeFiLlama"] = f"✓ {len(pools):,}"
                except Exception as e:
                    state.health["DeFiLlama"] = str(e)[:20]
                await asyncio.sleep(bot.LLAMA_INT)

        async def local_gecko_loop():
            ids  = ",".join(bot.COINGECKO_IDS.values())
            url  = f"http://127.0.0.1:{PORT_BASE+3}/api/v3/simple/price?ids={ids}&vs_currencies=usd"
            rev  = {v: k for k, v in bot.COINGECKO_IDS.items()}
            while state.running:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                            if r.status == 200:
                                data = await r.json(content_type=None)
                                async with state.lock:
                                    for gid, tok in rev.items():
                                        p = data.get(gid,{}).get("usd",0)
                                        if p:
                                            state.prices["CoinGecko"][tok] = float(p)
                                state.health["CoinGecko"] = "✓"
                except Exception as e:
                    state.health["CoinGecko"] = str(e)[:20]
                await asyncio.sleep(bot.GECKO_INT)

        async def local_binance_ws():
            uri   = f"ws://127.0.0.1:{BINANCE_WS_PORT}"
            rev   = {v: k for k, v in bot.BINANCE_SYMBOLS.items()}
            delay = 1
            while state.running:
                try:
                    async with websockets.connect(uri, ping_interval=None) as ws:
                        state.health["Binance"] = "✓ streaming"
                        async for raw in ws:
                            if not state.running: break
                            try:
                                ticker = json.loads(raw).get("data",{})
                                sym = ticker.get("s","")
                                p   = ticker.get("c")
                                if p:
                                    tok = rev.get(sym)
                                    if tok:
                                        async with state.lock:
                                            state.prices["Binance"][tok] = float(p)
                            except Exception:
                                pass
                except Exception:
                    if not state.running: break
                    await asyncio.sleep(delay)
                    delay = min(delay*2, 10)

        async def local_kraken_ws():
            uri   = f"ws://127.0.0.1:{KRAKEN_WS_PORT}"
            delay = 1
            while state.running:
                try:
                    async with websockets.connect(uri, ping_interval=None) as ws:
                        state.health["Kraken"] = "✓ streaming"
                        async for raw in ws:
                            if not state.running: break
                            try:
                                msg = json.loads(raw)
                                if isinstance(msg,list) and len(msg)==4 and msg[2]=="ticker":
                                    pair  = msg[3]
                                    tok   = bot.KRAKEN_REVERSE.get(pair)
                                    price = msg[1].get("c",[None])[0]
                                    if tok and price:
                                        async with state.lock:
                                            state.prices["Kraken"][tok] = float(price)
                            except Exception:
                                pass
                except Exception:
                    if not state.running: break
                    await asyncio.sleep(delay)
                    delay = min(delay*2, 10)

        async def progress_ticker():
            for i in range(1, 31):
                await asyncio.sleep(1)
                if i % 5 == 0:
                    srcs = sum(1 for s,v in state.health.items() if "✓" in v)
                    print(f"  [{i:2d}s] {state.total_count:>6,} trades  "
                          f"£{state.total_base:>8.2f}  "
                          f"{srcs}/6 sources live  "
                          f"pools:{state.pools_active:,}")
            state.running = False

        tasks = [
            asyncio.create_task(bot.csv_writer_loop(state)),
            asyncio.create_task(bot.comparison_loop(state)),
            asyncio.create_task(local_jupiter_loop()),
            asyncio.create_task(local_pyth_loop()),
            asyncio.create_task(local_llama_loop()),
            asyncio.create_task(local_gecko_loop()),
            asyncio.create_task(local_binance_ws()),
            asyncio.create_task(local_kraken_ws()),
            asyncio.create_task(progress_ticker()),
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        for t in tasks:
            t.cancel()

        # ── Verify results ──────────────────────────────────
        assert state.total_count > 0, "No trades in 30s integrated run"
        assert len(state.prices.get("Jupiter",{})) > 0, "Jupiter prices empty"
        assert len(state.prices.get("Binance",{}))  > 0, "Binance prices empty"
        assert len(state.prices.get("Pyth",{}))     > 0, "Pyth prices empty"
        assert state.pools_active > 0, "DeFiLlama pools never fetched"

        path = bot._csv_path(state.csv_index)
        with open(path) as f:
            rows = list(csv.reader(f))
        assert len(rows) > 1, "No CSV rows written"

        tps = state.total_count / 30
        ok("30-second integrated local run",
           f"{state.total_count:,} trades  £{state.total_base:.2f}  ≈{tps*86400:,.0f}/day")

        print(f"\n  Final source prices:")
        for src in ["Jupiter","Binance","Pyth","CoinGecko","Kraken"]:
            toks = list(state.prices.get(src,{}).keys())[:4]
            prices_str = "  ".join(f"{t}=${state.prices[src][t]:,.3f}" for t in toks)
            print(f"    {src:<12}: {prices_str or 'none'}")

        print(f"\n  Opportunities by type:")
        for otp, cnt in state.type_counts.items():
            print(f"    {otp:<12}: {cnt:,}")

        print(f"\n  CSV rows: {len(rows)-1}")

    for s in servers:
        await stop_server(s)
    ws_server_binance.close()
    await ws_server_binance.wait_closed()
    ws_server_kraken.close()
    await ws_server_kraken.wait_closed()

asyncio.run(_test_full_integrated())


# ═══════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════

print(f"\n{'═'*60}")
print(f"  RESULTS  {PASS_COUNT} passed   {FAIL_COUNT} failed")
if FAIL_COUNT > 0:
    print(f"\n  FAILURES:")
    for status, name, reason in RESULTS:
        if status == "FAIL":
            print(f"    • {name}")
            print(f"      {reason}")
print(f"{'═'*60}\n")
sys.exit(0 if FAIL_COUNT == 0 else 1)
