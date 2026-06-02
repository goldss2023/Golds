#!/usr/bin/env python3
"""
PRE-LIVE READINESS AUDIT
Tests what actually matters before risking real money.
Brutal honesty — no hype.
"""
import asyncio, json, time, math, csv, os, sys, tempfile, statistics
import aiohttp
import aiohttp.web
from websockets.asyncio.server import serve as ws_serve
import websockets

sys.path.insert(0, os.path.dirname(__file__))
import arb_bot_hf as bot

PASS = 0
FAIL = 0
WARN = 0

def ok(name, detail=""):
    global PASS; PASS += 1
    print(f"  ✓  PASS  {name}" + (f"  →  {detail}" if detail else ""))

def warn(name, detail=""):
    global WARN; WARN += 1
    print(f"  ⚠  WARN  {name}" + (f"  →  {detail}" if detail else ""))

def fail(name, detail=""):
    global FAIL; FAIL += 1
    print(f"  ✗  FAIL  {name}" + (f"  →  {detail}" if detail else ""))

def section(t):
    print(f"\n{'═'*60}")
    print(f"  {t}")
    print(f"{'═'*60}")


# ═══════════════════════════════════════════════════════════════
#  AUDIT 1 — FEE REALITY CHECK
#  The bot uses 0.1% per leg (0.2% total).
#  Real DEX fees are much higher.
# ═══════════════════════════════════════════════════════════════

section("AUDIT 1: FEE REALITY CHECK")

print("""
  What the bot assumes vs what actually happens on-chain:

  Bot assumption:    0.1% fee per leg  (0.2% round-trip)
  Jupiter DEX fee:   0.25–0.30% per swap (protocol + LP fees)
  Binance taker fee: 0.10% per trade
  Real round-trip:   0.35–0.40% minimum
  With slippage:     0.45–0.80% for small-cap tokens

  Consequence: every "opportunity" the bot finds needs to be
  re-evaluated against REAL fees.
""")

real_fee_scenarios = [
    ("Conservative (SOL/BTC/ETH)", 0.002 + 0.001),   # 0.3% total
    ("Realistic (mid-cap tokens)", 0.003 + 0.001),    # 0.4% total
    ("Worst-case (small-caps)",    0.005 + 0.002),    # 0.7% total
]

for scenario, real_fee in real_fee_scenarios:
    bot_threshold = 0.0025   # bot's 0.25% trigger
    actually_profitable_at = real_fee * 100
    pct_opps_survive = max(0, (1 - actually_profitable_at / 1.0)) * 100
    print(f"  {scenario}")
    print(f"    Bot triggers at:      0.25% gap")
    print(f"    Actually profitable:  >{actually_profitable_at:.1f}% gap")
    if actually_profitable_at > 0.25:
        fail(f"Gaps 0.25–{actually_profitable_at:.1f}% look like profit but are LOSSES after fees",
             f"scenario: {scenario}")
    else:
        ok(f"Fee model valid for {scenario}")
    print()


# ═══════════════════════════════════════════════════════════════
#  AUDIT 2 — LATENCY REALITY CHECK
#  How long does it take to execute after detection?
#  If gap closes faster than execution, profit = 0.
# ═══════════════════════════════════════════════════════════════

section("AUDIT 2: EXECUTION LATENCY vs GAP LIFETIME")

print("""
  How quickly can you actually execute after detecting a gap?

  Solana transaction finality:    ~0.4 seconds (400ms)
  Binance order execution:        ~50ms
  Total round-trip:               ~450ms minimum
  Jupiter poll interval:          4 seconds (you may see a gap
                                  3.9 seconds after it opened)
  Realistic detection-to-trade:   1–5 seconds total

  Professional arb bots:
    - Co-located servers at exchange data centres
    - Direct Solana validator connections
    - Sub-10ms detection-to-execution
    - They close every gap you detect BEFORE you can trade it
""")

# Simulate gap detection timing
async def audit_gap_detection_timing():
    PORT = 9100
    gap_open_time = None
    gap_detected_time = None

    async def jupiter_handler(req):
        nonlocal gap_open_time
        t = time.time()
        # Introduce a gap on the 3rd request (simulates gap opening)
        call_num = int(req.query.get("call", 0))
        if call_num >= 2:
            if gap_open_time is None:
                gap_open_time = t
            return aiohttp.web.json_response({"data": {
                bot.JUPITER_IDS["SOL"]: {"price": 156.0}  # gap vs Binance 155.0
            }})
        return aiohttp.web.json_response({"data": {
            bot.JUPITER_IDS["SOL"]: {"price": 155.0}
        }})

    app = aiohttp.web.Application()
    call_count = [0]

    async def handler(req):
        call_count[0] += 1
        t = time.time()
        if call_count[0] >= 3:
            if gap_open_time is None:
                nonlocal_gap_open = t
            return aiohttp.web.json_response({"data": {
                bot.JUPITER_IDS["SOL"]: {"price": 156.0}
            }})
        return aiohttp.web.json_response({"data": {
            bot.JUPITER_IDS["SOL"]: {"price": 155.0}
        }})

    app.router.add_get("/v4/price", handler)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    # Poll 5 times at 4s interval (like the bot does)
    gaps_found = []
    first_gap_poll = None
    async with aiohttp.ClientSession() as s:
        for i in range(5):
            t0 = time.time()
            url = f"http://127.0.0.1:{PORT}/v4/price?ids={bot.JUPITER_IDS['SOL']}"
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                data = (await r.json()).get("data", {})
                price = float(data.get(bot.JUPITER_IDS["SOL"], {}).get("price", 0))
                if price == 156.0 and first_gap_poll is None:
                    first_gap_poll = t0
            await asyncio.sleep(bot.JUPITER_INT)

    await runner.cleanup()

    # Gap appears on poll 3. With 4s poll interval, you detect it
    # up to 4 seconds AFTER it opened.
    max_detection_lag = bot.JUPITER_INT
    print(f"  Jupiter poll interval: {bot.JUPITER_INT}s")
    print(f"  Maximum detection lag: up to {max_detection_lag}s after gap opens")
    print(f"  Add execution time:    ~0.5s")
    print(f"  Total worst-case:      {max_detection_lag + 0.5}s after gap opens")
    print()
    warn("Jupiter gaps can be up to 4.5s old by the time you trade",
         f"poll={bot.JUPITER_INT}s + execution ~0.5s")

asyncio.run(audit_gap_detection_timing())


# ═══════════════════════════════════════════════════════════════
#  AUDIT 3 — OPPORTUNITY QUALITY ANALYSIS
#  Simulate real market-like prices and measure what % of
#  detected opportunities survive real fees.
# ═══════════════════════════════════════════════════════════════

section("AUDIT 3: OPPORTUNITY QUALITY (real fee filter)")

async def audit_opportunity_quality():
    import random
    random.seed(42)

    state = bot.BotState()
    with tempfile.TemporaryDirectory() as td:
        bot.CSV_BASE = os.path.join(td, "audit")

        # Inject realistic prices with random noise
        # Real markets: inter-exchange spread is typically 0.02–0.15%
        # True arb opportunities (after fees) are RARE
        base_prices = {"SOL":155.0,"BTC":67000.0,"ETH":3200.0,
                       "BONK":0.000028,"JTO":3.5,"WIF":2.1}

        total_detected = 0
        profitable_at_02pct = 0   # after 0.2% fees (bot's assumption)
        profitable_at_04pct = 0   # after 0.4% fees (conservative real)
        profitable_at_07pct = 0   # after 0.7% fees (realistic for small-caps)
        gap_sizes = []

        for _ in range(10000):
            tok = random.choice(list(base_prices.keys()))
            base = base_prices[tok]
            # Real market: noise is typically 0.01–0.15% between exchanges
            # True arb: <0.05% of the time a gap > 0.4% appears and is real
            noise = random.gauss(0, 0.0008)  # 0.08% std dev — realistic spread
            price_a = base * (1 + noise)
            price_b = base * (1 + random.gauss(0, 0.0008))

            gap = abs(price_a - price_b) / min(price_a, price_b) * 100
            if gap >= 0.25:
                total_detected += 1
                gap_sizes.append(gap)
                if gap >= 0.20 * 100/100:  # already accounting for 0.2%
                    net_02 = gap/100 - 0.002
                    if net_02 > 0: profitable_at_02pct += 1
                net_04 = gap/100 - 0.004
                if net_04 > 0: profitable_at_04pct += 1
                net_07 = gap/100 - 0.007
                if net_07 > 0: profitable_at_07pct += 1

        if not gap_sizes:
            warn("No gaps detected in simulation")
            return

        print(f"  Simulated 10,000 price snapshots (realistic 0.08% std dev noise)")
        print(f"  Gaps >= 0.25% detected: {total_detected}")
        print()
        print(f"  After bot's assumed fees (0.2%):  {profitable_at_02pct}/{total_detected} "
              f"= {profitable_at_02pct/max(total_detected,1)*100:.1f}% profitable")
        print(f"  After real fees (0.4%):           {profitable_at_04pct}/{total_detected} "
              f"= {profitable_at_04pct/max(total_detected,1)*100:.1f}% profitable")
        print(f"  After small-cap fees (0.7%):      {profitable_at_07pct}/{total_detected} "
              f"= {profitable_at_07pct/max(total_detected,1)*100:.1f}% profitable")
        print()
        if gap_sizes:
            print(f"  Gap size distribution:")
            print(f"    Median gap:  {statistics.median(gap_sizes):.4f}%")
            print(f"    Mean gap:    {statistics.mean(gap_sizes):.4f}%")
            print(f"    Max gap:     {max(gap_sizes):.4f}%")
            print(f"    >0.4% gaps:  {sum(1 for g in gap_sizes if g > 0.4)}")
            print(f"    >0.7% gaps:  {sum(1 for g in gap_sizes if g > 0.7)}")

        pct_real = profitable_at_04pct / max(total_detected, 1) * 100
        if pct_real < 30:
            fail("Majority of detected opportunities are UNPROFITABLE after real fees",
                 f"only {pct_real:.1f}% survive 0.4% real fee")
        else:
            ok("Opportunity quality acceptable", f"{pct_real:.1f}% profitable at real fees")

asyncio.run(audit_opportunity_quality())


# ═══════════════════════════════════════════════════════════════
#  AUDIT 4 — DATA FRESHNESS: COINGECKO & DEFILLAMA GAPS
#  These sources have 30–60s lag. "Opportunities" from them
#  are almost certainly stale data artifacts, not real arb.
# ═══════════════════════════════════════════════════════════════

section("AUDIT 4: STALE DATA SOURCE ANALYSIS")

print("""
  The bot compares these sources against each other:

  Source         Update frequency    Data age when compared
  ─────────────────────────────────────────────────────────
  Binance WS     Real-time (<10ms)   Fresh
  Kraken WS      Real-time (<10ms)   Fresh
  OKX WS         Real-time (<10ms)   Fresh
  Bybit WS       Real-time (<10ms)   Fresh
  Jupiter REST   Every 4s            Up to 4s old
  Pyth REST      Every 8s            Up to 8s old
  CoinGecko REST Every 30s           Up to 30s old  ← STALE
  DeFiLlama      Every 45s           Up to 45s old  ← STALE
  The Graph      Every 15s           Up to 15s old  ← STALE

  CoinGecko vs Binance "opportunities":
  → CoinGecko aggregates from multiple exchanges with 30s+ lag
  → Any gap you detect is the price AS IT WAS 30+ seconds ago
  → By the time you trade, the gap is already closed
  → These are FALSE POSITIVES — not real opportunities
""")

# Count how many opportunity types come from stale sources
stale_pairs = [p for p in bot.SOURCE_PAIRS
               if "CoinGecko" in p or "TheGraph" in p]
total_pairs = len(bot.SOURCE_PAIRS)
stale_pct   = len(stale_pairs) / total_pairs * 100

print(f"  {len(stale_pairs)}/{total_pairs} source pairs involve stale data sources")
warn(f"{len(stale_pairs)} of {total_pairs} comparison pairs produce unreliable signals",
     "CoinGecko (30s lag) and TheGraph (15s lag) vs real-time sources")

# DeFiLlama yield "opportunities"
print("""
  DeFiLlama YIELD opportunities:
  → These are ANNUALISED yield rates, not instant arbitrage
  → You cannot instantly capture APY — you must deposit funds
    and wait days/weeks for yield to accrue
  → The profit shown (£50 × APY/365) = daily estimate, not instant
  → These are NOT executable same-day opportunities
""")
fail("DeFiLlama YIELD opps are NOT instant — require days to accrue",
     "daily estimate only, cannot be executed as arb trades")


# ═══════════════════════════════════════════════════════════════
#  AUDIT 5 — EXECUTION GAP (CRITICAL)
#  This bot has NO execution capability whatsoever.
# ═══════════════════════════════════════════════════════════════

section("AUDIT 5: EXECUTION CAPABILITY")

print("""
  What the bot does:    DETECTS and LOGS price differences
  What the bot does NOT do:
    ✗ Connect to any wallet
    ✗ Submit any transaction to Solana
    ✗ Place any order on Binance/Kraken/OKX/Bybit
    ✗ Execute the buy side of any trade
    ✗ Execute the sell side of any trade
    ✗ Manage position sizing
    ✗ Handle partial fills
    ✗ Handle failed transactions
    ✗ Manage slippage tolerance
    ✗ Handle gas price spikes

  To go live you would need to build:
    1. Solana wallet integration (keypair management)
    2. Jupiter swap execution via their API
    3. Binance/exchange API order placement
    4. Atomic or near-simultaneous dual-leg execution
    5. Position size management
    6. Failure recovery (what if leg 1 succeeds but leg 2 fails?)
    7. Risk management and circuit breakers

  This is months of additional development, not a same-day upgrade.
""")
fail("Bot has ZERO execution capability — cannot place a single real trade",
     "detection only, no wallet, no order placement")


# ═══════════════════════════════════════════════════════════════
#  AUDIT 6 — COMPETITION REALITY
# ═══════════════════════════════════════════════════════════════

section("AUDIT 6: COMPETITION REALITY CHECK")

print("""
  DEX-CEX arbitrage on Solana is one of the most competitive
  strategies in all of crypto trading.

  Who you are competing against:
  ─────────────────────────────────────────────────────────────
  • Wintermute, Jump Trading, Alameda-successors
    → Multi-million dollar infrastructure
    → Co-located at Solana validators
    → Sub-1ms detection to execution
    → Dedicated MEV (Maximal Extractable Value) strategies

  • Hundreds of open-source arb bots running on cloud servers
    → jito-solana bundles (atomic transaction ordering)
    → They see the mempool BEFORE transactions confirm

  • Market makers with passive orders already at arb prices
    → They set the spread — by definition arb is priced in

  Reality: any gap you detect via a REST API has already been
  closed by the time your HTTP request returned.

  The 0.25% threshold means you're looking at:
  → Normal bid-ask spread variation (not real arb)
  → Data feed latency artifacts (not real arb)
  → Liquidity depth mismatches (not profitably executable)
""")
warn("DEX-CEX arb is dominated by professional HFT with ms-level execution",
     "retail API-based detection cannot compete on speed")


# ═══════════════════════════════════════════════════════════════
#  AUDIT 7 — WHAT THE PAPER PROFIT NUMBERS ACTUALLY MEAN
# ═══════════════════════════════════════════════════════════════

section("AUDIT 7: INTERPRETING THE PAPER PROFIT NUMBERS")

print("""
  The integrated test showed: £423.66 profit, 1,545 trades

  What this actually means:
  ─────────────────────────────────────────────────────────────
  ✓ The detection logic works correctly
  ✓ The math is right (given the inputs)
  ✓ The CSV logging is correct
  ✓ The concurrency is safe

  What it does NOT mean:
  ─────────────────────────────────────────────────────────────
  ✗ That £423.66 is earnable in the real world
  ✗ That those 1,545 opportunities were real
  ✗ That you could have executed any of them
  ✗ That the fee assumptions are correct
  ✗ That the opportunities lasted long enough to trade

  The paper profit is calculated assuming:
  → You can execute both legs simultaneously (impossible)
  → Fees are 0.1% per leg (too low for DEX trades)
  → No slippage (unrealistic for small-cap tokens)
  → Gap persists until you execute (it doesn't)
  → You have funds on both sides already deployed (requires capital)
""")
warn("Paper profit numbers assume perfect execution — real profit will be much lower",
     "possibly negative after real fees and slippage")


# ═══════════════════════════════════════════════════════════════
#  AUDIT 8 — WHAT YOU ACTUALLY CAN DO TODAY
# ═══════════════════════════════════════════════════════════════

section("AUDIT 8: REALISTIC PATH TO LIVE TRADING")

print("""
  What you CAN do TODAY (low risk, builds real knowledge):
  ─────────────────────────────────────────────────────────────
  1. Run the paper bot for 7 days on Replit with real internet
  2. Export the CSV and filter by:
     → Only DEX_CEX and CEX_CEX type opportunities
     → Only gaps > 0.5% (more likely to survive real fees)
     → Only SOL, BTC, ETH (deepest liquidity, lowest slippage)
  3. Manually check 20–30 of those opportunities against
     actual order books at that timestamp
  4. If >50% were still open after 1 second → strategy has merit

  What you need BEFORE going live with money:
  ─────────────────────────────────────────────────────────────
  1. A backtester against real historical tick data
     (paper bot ≠ backtest — they are different things)
  2. Execution layer (Solana + exchange APIs)
  3. Risk management (max loss per day, circuit breakers)
  4. Start with £50 MAXIMUM if you do go live
  5. Expect to lose it while learning — that is normal
  6. Never risk money you cannot afford to lose entirely

  Strategies that work for retail traders (no HFT competition):
  ─────────────────────────────────────────────────────────────
  → Funding rate arbitrage (much slower, less competition)
  → Yield farming with stablecoins (DeFiLlama data is useful here)
  → Statistical mean-reversion (slower timeframes)
  → Trend following (not arb, but well-studied)
""")


# ═══════════════════════════════════════════════════════════════
#  FINAL VERDICT
# ═══════════════════════════════════════════════════════════════

print(f"\n{'═'*60}")
print(f"  PRE-LIVE AUDIT RESULTS")
print(f"{'═'*60}")
print(f"  ✓ PASSED : {PASS}  (bot mechanics work correctly)")
print(f"  ⚠ WARNING: {WARN}  (known risks, proceed with caution)")
print(f"  ✗ FAILED : {FAIL}  (blockers — do not go live until resolved)")
print(f"{'═'*60}")
print(f"""
  VERDICT: NOT READY FOR LIVE TRADING TODAY

  The bot's code is solid. The tests prove the mechanics work.
  But "code works" is not the same as "will make money."

  The three hard blockers are:
  1. No execution layer — the bot cannot place a single trade
  2. Fee assumptions are wrong — real DEX fees are 2–3× higher
  3. Stale data sources produce false signals

  Recommended path:
  → Run paper mode for 7+ days with real internet
  → Analyse the CSV to find genuinely persistent gaps
  → Build execution on top of that analysis
  → Start with the smallest possible real position (£10–50)
  → Only scale up when you have 30+ days of real P&L data
""")
