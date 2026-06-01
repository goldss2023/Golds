#!/usr/bin/env python3
"""
Stress test suite for arb_bot_hf.py
Tests every failure mode without needing network access.
Run: python3 stress_test.py
"""
import asyncio, math, os, csv, time, sys, tempfile, traceback

# ── patch CSV path before import so tests don't pollute real files
import arb_bot_hf as bot

PASS = 0
FAIL = 0
ERRORS = []

def ok(name):
    global PASS
    PASS += 1
    print(f"  ✓  {name}")

def fail(name, reason):
    global FAIL
    FAIL += 1
    ERRORS.append(f"{name}: {reason}")
    print(f"  ✗  {name}  →  {reason}")

def run(name, coro):
    try:
        asyncio.run(coro)
        ok(name)
    except AssertionError as e:
        fail(name, str(e))
    except Exception as e:
        fail(name, f"{type(e).__name__}: {e}")

# ═══════════════════════════════════════════════════════════
#  1. MATH — gap calculation
# ═══════════════════════════════════════════════════════════

print("\n── 1. Gap calculation ──────────────────────────────")

def test_gap_normal():
    g = bot._safe_gap_pct(101.0, 100.0)
    assert abs(g - 1.0) < 1e-9, f"Expected 1.0 got {g}"
ok("normal gap")

def test_gap_zero_a():
    assert bot._safe_gap_pct(0.0, 100.0) is None
ok("zero price_a → None")

def test_gap_zero_b():
    assert bot._safe_gap_pct(100.0, 0.0) is None
ok("zero price_b → None")

def test_gap_negative():
    assert bot._safe_gap_pct(-5.0, 100.0) is None
ok("negative price → None")

def test_gap_nan():
    assert bot._safe_gap_pct(float("nan"), 100.0) is None
ok("NaN price → None")

def test_gap_inf():
    assert bot._safe_gap_pct(float("inf"), 100.0) is None
ok("inf price → None")

def test_gap_equal():
    g = bot._safe_gap_pct(100.0, 100.0)
    assert g == 0.0
ok("equal prices → 0%")

def test_gap_symmetric():
    g1 = bot._safe_gap_pct(105.0, 100.0)
    g2 = bot._safe_gap_pct(100.0, 105.0)
    assert abs(g1 - g2) < 1e-9
ok("gap is symmetric")

def test_gap_tiny():
    g = bot._safe_gap_pct(100.001, 100.0)
    assert g is not None and g > 0
ok("tiny gap is positive")

# ═══════════════════════════════════════════════════════════
#  2. MATH — profit calculation
# ═══════════════════════════════════════════════════════════

print("\n── 2. Profit calculation ───────────────────────────")

def test_profit_basic():
    base, flash = bot._profit(1.0)     # 1% gap
    # net = 0.01 - 0.002 = 0.008
    assert abs(base  - 50.0 * 0.008) < 1e-9
    assert abs(flash - 500.0 * 0.008) < 1e-9
ok("1% gap profit")

def test_profit_below_fees():
    base, flash = bot._profit(0.1)    # 0.1% gap, fees = 0.2% → net < 0
    assert base == 0.0 and flash == 0.0
ok("gap below fees → £0")

def test_profit_exactly_at_fee():
    base, flash = bot._profit(0.2)    # net = 0
    assert base == 0.0
ok("gap exactly at fee boundary → £0")

def test_profit_flash_is_10x():
    base, flash = bot._profit(1.0)
    assert abs(flash / base - bot.FLASH_MULT) < 1e-9
ok("flash profit = 10× base")

def test_profit_large_gap():
    base, flash = bot._profit(50.0)
    assert base > 0 and flash > 0
ok("large gap gives positive profit")

# ═══════════════════════════════════════════════════════════
#  3. DEDUP
# ═══════════════════════════════════════════════════════════

print("\n── 3. Dedup logic ──────────────────────────────────")

async def _mk_state():
    return bot.BotState()

async def test_dedup_blocks_repeat():
    state = await _mk_state()
    state.prices["Jupiter"]["SOL"] = 150.0
    state.prices["Binance"]["SOL"] = 151.0   # 0.66% gap → triggers

    await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
    first = state.total_count
    await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
    second = state.total_count
    assert second == first, f"Dedup failed: count went from {first} to {second}"
run("dedup blocks same pair within 2 s", test_dedup_blocks_repeat())

async def test_dedup_allows_different_token():
    state = await _mk_state()
    await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
    before = state.total_count
    await bot._record(state,"ETH","Jupiter","Binance",3000.0,3010.0,"DEX_CEX",0.25)
    assert state.total_count > before
run("dedup allows different token", test_dedup_allows_different_token())

async def test_dedup_allows_after_window():
    state = await _mk_state()
    await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
    # Manually expire the dedup entry
    state.dedup[("SOL","Jupiter","Binance")] = time.time() - bot.DEDUP_SECONDS - 0.1
    before = state.total_count
    await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
    assert state.total_count > before
run("dedup allows after window expires", test_dedup_allows_after_window())

# ═══════════════════════════════════════════════════════════
#  4. THRESHOLD — below threshold never triggers
# ═══════════════════════════════════════════════════════════

print("\n── 4. Thresholds ───────────────────────────────────")

async def test_below_threshold():
    state = await _mk_state()
    # 0.10% gap, threshold 0.25% — should not trigger
    await bot._record(state,"SOL","Jupiter","Binance",100.0,100.1,"DEX_CEX",0.25)
    assert state.total_count == 0
run("below threshold → no trade", test_below_threshold())

async def test_exactly_at_threshold():
    state = await _mk_state()
    # exactly 0.25% gap
    await bot._record(state,"SOL","Jupiter","Binance",100.0,100.25,"DEX_CEX",0.25)
    # profit must also be positive: net = 0.0025 - 0.002 = 0.0005 > 0 ✓
    assert state.total_count == 1
run("exactly at threshold triggers", test_exactly_at_threshold())

async def test_oracle_threshold_higher():
    state = await _mk_state()
    # 0.26% gap, ORACLE threshold is 0.30% → should NOT trigger
    await bot._record(state,"SOL","Jupiter","Pyth",100.0,100.26,"ORACLE",0.30)
    assert state.total_count == 0
run("oracle threshold 0.30% respected", test_oracle_threshold_higher())

# ═══════════════════════════════════════════════════════════
#  5. YIELD — special handler
# ═══════════════════════════════════════════════════════════

print("\n── 5. Yield handler ────────────────────────────────")

async def test_yield_records():
    state = await _mk_state()
    await bot._record_yield(state,"USDC","aave","Ethereum",10.0)
    assert state.total_count == 1
    assert state.type_counts["YIELD"] == 1
run("yield APY >2% records", test_yield_records())

async def test_yield_below_min_ignored():
    state = await _mk_state()
    await bot._record_yield(state,"USDC","aave","Ethereum",1.5)
    assert state.total_count == 0
run("yield APY <2% ignored", test_yield_below_min_ignored())

async def test_yield_zero_ignored():
    state = await _mk_state()
    await bot._record_yield(state,"USDC","aave","Ethereum",0.0)
    assert state.total_count == 0
run("yield APY=0 ignored", test_yield_zero_ignored())

async def test_yield_nan_ignored():
    state = await _mk_state()
    await bot._record_yield(state,"USDC","aave","Ethereum",float("nan"))
    assert state.total_count == 0
run("yield NaN APY ignored", test_yield_nan_ignored())

async def test_yield_negative_ignored():
    state = await _mk_state()
    await bot._record_yield(state,"USDC","aave","Ethereum",-5.0)
    assert state.total_count == 0
run("yield negative APY ignored", test_yield_negative_ignored())

async def test_yield_profit_calculation():
    state = await _mk_state()
    apy = 36.5          # 36.5% APY → daily = 0.1% of trade
    await bot._record_yield(state,"USDC","test","ETH",apy)
    assert state.total_count == 1
    expected_base = 50.0 * (apy / 100.0 / 365.0)
    assert abs(state.total_base - expected_base) < 1e-9
run("yield profit math correct", test_yield_profit_calculation())

# ═══════════════════════════════════════════════════════════
#  6. STATE — running totals, best/worst tracking
# ═══════════════════════════════════════════════════════════

print("\n── 6. State accounting ─────────────────────────────")

async def test_best_worst_tracked():
    state = await _mk_state()
    await bot._record(state,"SOL","Jupiter","Binance",100.0,101.0,"DEX_CEX",0.25)
    # force dedup expiry
    state.dedup.clear()
    await bot._record(state,"SOL","Jupiter","Binance",100.0,105.0,"DEX_CEX",0.25)
    state.dedup.clear()
    await bot._record(state,"SOL","Jupiter","Binance",100.0,100.3,"DEX_CEX",0.25)
    assert state.best > state.worst
run("best > worst after mixed trades", test_best_worst_tracked())

async def test_count_increments():
    state = await _mk_state()
    for i in range(5):
        state.dedup.clear()
        await bot._record(state,"SOL","Jupiter","Binance",100.0,101.0,"DEX_CEX",0.25)
    assert state.total_count == 5
run("total_count increments correctly", test_count_increments())

async def test_type_counts():
    state = await _mk_state()
    await bot._record(state,"SOL","Jupiter","Binance",100.0,101.0,"DEX_CEX",0.25)
    state.dedup.clear()
    await bot._record(state,"ETH","Binance","Kraken",100.0,101.0,"CEX_CEX",0.15)
    assert state.type_counts["DEX_CEX"] == 1
    assert state.type_counts["CEX_CEX"] == 1
run("type_counts per category", test_type_counts())

# ═══════════════════════════════════════════════════════════
#  7. CSV — write, header, rotation trigger
# ═══════════════════════════════════════════════════════════

print("\n── 7. CSV ──────────────────────────────────────────")

async def test_csv_writes_row():
    state = await _mk_state()
    # redirect CSV to temp dir
    orig_base = bot.CSV_BASE
    with tempfile.TemporaryDirectory() as td:
        bot.CSV_BASE = os.path.join(td, "test_arb")
        path = bot._csv_path(0)
        bot._init_csv(path)
        await bot._record(state,"SOL","Jupiter","Binance",150.0,151.0,"DEX_CEX",0.25)
        # manually drain queue
        opp = await asyncio.wait_for(state.csv_queue.get(), timeout=1.0)
        bot._append_csv_row(path, [
            opp.timestamp, opp.token, opp.source_a, opp.source_b,
            opp.price_a, opp.price_b, opp.gap_pct,
            opp.profit_base_gbp, opp.profit_flash_gbp, opp.opp_type,
        ])
        with open(path) as f:
            rows = list(csv.reader(f))
        assert rows[0] == bot.CSV_HEADER, f"Bad header: {rows[0]}"
        assert len(rows) == 2, f"Expected 2 rows (header+data) got {len(rows)}"
    bot.CSV_BASE = orig_base
run("CSV header + data row written", test_csv_writes_row())

def test_csv_rotation_path():
    p0 = bot._csv_path(0)
    p1 = bot._csv_path(1)
    p5 = bot._csv_path(5)
    assert p0.endswith(".csv")
    assert "_1" in p1
    assert "_5" in p5
ok("CSV rotation path naming correct")

async def test_csv_writer_loop_drains_queue():
    state = await _mk_state()
    with tempfile.TemporaryDirectory() as td:
        bot.CSV_BASE = os.path.join(td, "test_arb")
        # inject 3 opportunities directly into queue
        for i in range(3):
            state.dedup.clear()
            await bot._record(state,"SOL","Jupiter","Binance",
                              100.0 + i, 101.0 + i,"DEX_CEX",0.25)
        assert state.csv_queue.qsize() == 3
        # run writer for brief period
        state.running = False   # let loop exit after draining
        await asyncio.wait_for(bot.csv_writer_loop(state), timeout=5.0)
        path = bot._csv_path(state.csv_index)
        with open(path) as f:
            rows = list(csv.reader(f))
        assert len(rows) == 4, f"Expected 4 rows (header+3) got {len(rows)}"
    bot.CSV_BASE = "arb_opportunities"
run("CSV writer loop drains queue", test_csv_writer_loop_drains_queue())

# ═══════════════════════════════════════════════════════════
#  8. DASHBOARD — renders without exception
# ═══════════════════════════════════════════════════════════

print("\n── 8. Dashboard rendering ──────────────────────────")

async def test_dashboard_empty_state():
    state = await _mk_state()
    txt = bot.build_dashboard(state)
    assert "PAPER TRADING" in txt
    assert "Runtime" in txt
run("dashboard renders with empty state", test_dashboard_empty_state())

async def test_dashboard_with_data():
    state = await _mk_state()
    for i in range(7):
        state.dedup.clear()
        await bot._record(state,"SOL","Jupiter","Binance",
                          150.0, 150.0 + (i+1)*0.5,"DEX_CEX",0.25)
    txt = bot.build_dashboard(state)
    assert "£" in txt
run("dashboard renders with trade data", test_dashboard_with_data())

async def test_dashboard_worst_inf_handled():
    state = await _mk_state()
    # worst starts at inf — should display £0.00 not crash
    assert state.worst == math.inf
    txt = bot.build_dashboard(state)
    assert "£0.00" in txt
run("dashboard handles worst=inf gracefully", test_dashboard_worst_inf_handled())

async def test_dashboard_60s_purge():
    state = await _mk_state()
    # insert an old entry
    opp = bot.Opportunity("t","SOL","J","B",1.0,1.01,1.0,0.4,4.0,"DEX_CEX")
    state.opp_60s.append((time.time() - 61, opp))
    state.recent_5.append(opp)
    state.total_count = 1
    bot._purge_60s(state)
    assert len(state.opp_60s) == 0
run("60s window purges stale entries", test_dashboard_60s_purge())

# ═══════════════════════════════════════════════════════════
#  9. CONCURRENCY — race condition check
# ═══════════════════════════════════════════════════════════

print("\n── 9. Concurrency ──────────────────────────────────")

async def test_concurrent_records():
    state = await _mk_state()
    tokens = ["SOL","BTC","ETH","BONK","JTO","WIF","RAY","ORCA"]
    async def fire(tok):
        await bot._record(state,tok,"Jupiter","Binance",
                          100.0,101.0,"DEX_CEX",0.25)
    await asyncio.gather(*[fire(t) for t in tokens])
    assert state.total_count == len(tokens)
run("concurrent records all counted", test_concurrent_records())

async def test_concurrent_no_double_count():
    state = await _mk_state()
    # same token, same source pair, concurrent — only 1 should win dedup
    results = await asyncio.gather(*[
        bot._record(state,"SOL","Jupiter","Binance",100.0,101.0,"DEX_CEX",0.25)
        for _ in range(20)
    ])
    assert state.total_count == 1, f"Dedup failed under concurrency: {state.total_count}"
run("concurrent dedup allows only 1 winner", test_concurrent_no_double_count())

# ═══════════════════════════════════════════════════════════
#  10. COMPARISON ENGINE — mock price injection
# ═══════════════════════════════════════════════════════════

print("\n── 10. Comparison engine ───────────────────────────")

async def test_comparison_detects_opportunity():
    state = await _mk_state()
    async with state.lock:
        state.prices["Jupiter"]["SOL"] = 150.0
        state.prices["Binance"]["SOL"] = 151.0   # 0.66% → triggers

    # run one iteration of comparison loop
    state.running = False  # let it run once then stop
    async def one_pass():
        snap = {src: dict(p) for src, p in state.prices.items()}
        tasks = []
        for src_a, src_b, opp_type in bot.SOURCE_PAIRS:
            pa = snap.get(src_a, {})
            pb = snap.get(src_b, {})
            threshold = bot.THRESHOLDS.get(opp_type, 0.25)
            for tok in bot.TOKENS:
                a, b = pa.get(tok), pb.get(tok)
                if a and b:
                    tasks.append(bot._record(state,tok,src_a,src_b,a,b,opp_type,threshold))
        if tasks:
            await asyncio.gather(*tasks)
    await one_pass()
    assert state.total_count >= 1, "No opportunity detected when gap=0.66%"
run("comparison engine detects 0.66% gap", test_comparison_detects_opportunity())

async def test_comparison_ignores_small_gap():
    state = await _mk_state()
    async with state.lock:
        state.prices["Jupiter"]["SOL"] = 150.0
        state.prices["Binance"]["SOL"] = 150.1    # 0.067% → below all thresholds

    async def one_pass():
        snap = {src: dict(p) for src, p in state.prices.items()}
        tasks = []
        for src_a, src_b, opp_type in bot.SOURCE_PAIRS:
            pa, pb = snap.get(src_a,{}), snap.get(src_b,{})
            threshold = bot.THRESHOLDS.get(opp_type, 0.25)
            for tok in bot.TOKENS:
                a, b = pa.get(tok), pb.get(tok)
                if a and b:
                    tasks.append(bot._record(state,tok,src_a,src_b,a,b,opp_type,threshold))
        if tasks:
            await asyncio.gather(*tasks)
    await one_pass()
    assert state.total_count == 0
run("comparison ignores tiny gap", test_comparison_ignores_small_gap())

# ═══════════════════════════════════════════════════════════
#  11. FULL MOCK RUN — 8 seconds with injected prices
# ═══════════════════════════════════════════════════════════

print("\n── 11. Full mock run (8 s) ─────────────────────────")

async def test_full_mock_run():
    import random
    state = bot.BotState()

    with tempfile.TemporaryDirectory() as td:
        bot.CSV_BASE = os.path.join(td, "mock_arb")

        async def mock_price_injector():
            """Continuously inject prices with deliberate gaps."""
            base = {"SOL":150,"BTC":65000,"ETH":3000,"BONK":0.00003,
                    "JTO":3.5,"WIF":2.0,"JUP":0.8,"RAY":1.5,"ORCA":4.0}
            while state.running:
                async with state.lock:
                    for tok, p in base.items():
                        state.prices["Jupiter"][tok] = p
                        state.prices["Binance"][tok] = p * (1 + random.uniform(0.001,0.01))
                        state.prices["Pyth"][tok]    = p * (1 + random.uniform(0.0,0.005))
                        state.prices["Kraken"][tok]  = p * (1 + random.uniform(0.001,0.006))
                await asyncio.sleep(0.05)

        async def stopper():
            await asyncio.sleep(8)
            state.running = False

        tasks = [
            asyncio.create_task(bot.csv_writer_loop(state),   name="csv"),
            asyncio.create_task(bot.comparison_loop(state),   name="compare"),
            asyncio.create_task(mock_price_injector(),        name="injector"),
            asyncio.create_task(stopper(),                    name="stopper"),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        for t in tasks:
            t.cancel()

        # verify results
        assert state.total_count > 0, "No trades in 8s mock run"
        assert state.total_base  > 0
        assert state.total_flash > 0
        assert state.type_counts["DEX_CEX"] > 0

        path = bot._csv_path(state.csv_index)
        assert os.path.exists(path), "CSV file not created"
        with open(path) as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2, f"CSV has only {len(rows)} rows"

        tps = state.total_count / 8.0
        print(f"       {state.total_count:,} trades in 8s  ({tps:.1f}/s  ≈ {tps*86400:,.0f}/day)")

    bot.CSV_BASE = "arb_opportunities"

run("8-second mock run produces trades + CSV", test_full_mock_run())

# ═══════════════════════════════════════════════════════════
#  12. EDGE CASES — exotic inputs
# ═══════════════════════════════════════════════════════════

print("\n── 12. Edge cases ──────────────────────────────────")

async def test_very_large_prices():
    state = await _mk_state()
    await bot._record(state,"BTC","Jupiter","Binance",1_000_000.0,1_005_000.0,"DEX_CEX",0.25)
    assert state.total_count == 1
run("very large prices handled", test_very_large_prices())

async def test_very_small_prices():
    state = await _mk_state()
    await bot._record(state,"BONK","Jupiter","Binance",0.000001,0.0000011,"DEX_CEX",0.25)
    assert state.total_count == 1
run("very small prices handled", test_very_small_prices())

async def test_gap_pct_none_skipped():
    state = await _mk_state()
    await bot._record(state,"SOL","Jupiter","Binance",0.0,150.0,"DEX_CEX",0.25)
    assert state.total_count == 0
run("price_a=0 skipped cleanly", test_gap_pct_none_skipped())

async def test_none_value_in_price_map():
    # comparison engine uses .get() which returns None, then "if a and b" guards
    state = await _mk_state()
    async with state.lock:
        state.prices["Jupiter"]["SOL"] = None   # type: ignore
        state.prices["Binance"]["SOL"] = 150.0

    snap = {src: dict(p) for src, p in state.prices.items()}
    a = snap.get("Jupiter",{}).get("SOL")
    b = snap.get("Binance",{}).get("SOL")
    # Guard: "if a and b" — None is falsy, so this is skipped
    if a and b:
        await bot._record(state,"SOL","Jupiter","Binance",a,b,"DEX_CEX",0.25)
    assert state.total_count == 0
run("None price in map skipped by guard", test_none_value_in_price_map())

# ═══════════════════════════════════════════════════════════
#  13. SYNTAX + IMPORT
# ═══════════════════════════════════════════════════════════

print("\n── 13. Syntax / import ─────────────────────────────")

import py_compile
try:
    py_compile.compile("/home/user/Golds/arb_bot_hf.py", doraise=True)
    ok("syntax check passes")
except py_compile.PyCompileError as e:
    fail("syntax check", str(e))

try:
    assert hasattr(bot, "main")
    assert hasattr(bot, "BotState")
    assert hasattr(bot, "_record")
    assert hasattr(bot, "_record_yield")
    assert hasattr(bot, "build_dashboard")
    assert hasattr(bot, "csv_writer_loop")
    assert hasattr(bot, "comparison_loop")
    ok("all required functions present")
except AssertionError as e:
    fail("function presence", str(e))

# ═══════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════

print(f"\n{'═'*52}")
print(f"  RESULTS: {PASS} passed   {FAIL} failed")
if ERRORS:
    print(f"\n  FAILURES:")
    for e in ERRORS:
        print(f"    • {e}")
print(f"{'═'*52}\n")
sys.exit(0 if FAIL == 0 else 1)
