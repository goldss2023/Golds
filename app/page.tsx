const markets = [
  ["XAU/USD", "Gold / US Dollar", "2,383.60", "▲ 0.19%", "up"],
  ["EUR/USD", "Euro / US Dollar", "1.0872", "▼ 0.12%", "down"],
  ["US30", "Dow Jones 30", "39,872.90", "▲ 0.35%", "up"],
  ["NAS100", "Nasdaq 100", "18,735.20", "▲ 0.67%", "up"],
  ["BTC/USD", "Bitcoin / US Dollar", "67,842.10", "▲ 1.23%", "up"]
];

const plans = [
  ["Monthly VIP", "£50", "30 days of VIP market intelligence and manual Telegram approval."],
  ["6 Month VIP", "£265", "Longer-term access with a cleaner discounted price."],
  ["1 Year VIP", "£497", "Best value for traders who want a full year inside Midas."],
  ["1-to-1 Session", "£197", "Private Midas strategy review and execution feedback."]
];

const strategies = [
  ["Midas Momentum", "+24.37%", "AI-driven momentum strategy across asset classes."],
  ["Quantum Trend", "+18.74%", "Multi-timeframe trend following with probability filters."],
  ["Alpha Capture", "+15.89%", "Mean-reversion model with volatility adaptation."],
  ["News Sentiment", "+27.11%", "NLP-driven event analysis for fast market reactions."]
];

export default function Home() {
  return (
    <main>
      <div className="ticker">
        <span><b>S&P 500</b> 5,278.40 <em className="up">▲ 0.41%</em></span>
        <span><b>NASDAQ</b> 18,735.20 <em className="up">▲ 0.67%</em></span>
        <span><b>GOLD</b> 2,383.60 <em className="up">▲ 0.19%</em></span>
        <span><b>EUR/USD</b> 1.0872 <em className="down">▼ 0.12%</em></span>
        <span><b>BTC/USD</b> 67,842.10 <em className="up">▲ 1.23%</em></span>
      </div>

      <header className="header">
        <a className="brand" href="#">
          <svg className="mark" viewBox="0 0 64 64" fill="none"><path d="M9 54V10l23 23 23-23v44H44V35L32 47 20 35v19H9Z" fill="url(#g)"/><path d="M9 10l23 23 23-23" stroke="#ffe6a2" strokeWidth="4"/><defs><linearGradient id="g" x1="8" x2="57" y1="9" y2="55"><stop stopColor="#fff0b7"/><stop offset=".45" stopColor="#d8ad4e"/><stop offset="1" stopColor="#8e641e"/></linearGradient></defs></svg>
          <span><span className="word">MIDAS</span><span className="sub">MARKETS</span></span>
        </a>
        <nav className="nav"><a href="#vip">Trading</a><a href="#markets">Markets</a><a href="#strategies">AI Strategies</a><a href="#vip">Institutional</a><a href="#socials">Resources</a></nav>
        <div className="actions"><a className="btn gold" href="#vip">Open Account</a><a className="btn ghost" href="https://t.me/MidasMarketsai">Contact Us</a></div>
      </header>

      <section className="shell hero">
        <div>
          <h1 className="display">Trade Like Everything <span className="goldtext">Depends on It.</span></h1>
          <p className="lead">Midas Markets delivers AI-powered trading intelligence, automated crypto VIP access, weekly trade proof, and a premium workflow for traders who want cleaner decisions.</p>
          <div className="heroBtns"><a className="btn gold" href="#vip">Open Account</a><a className="btn ghost" href="#strategies">Explore Platforms</a></div>
          <div className="trust"><div><b>Verified</b>Crypto checkout</div><div><b>Institutional</b>AI liquidity reads</div><div><b>Manual</b>Telegram approval</div><div><b>24/7</b>Member portal</div></div>
        </div>

        <div className="stage">
          <div className="platform" />
          <svg className="midas" viewBox="0 0 520 520" fill="none"><defs><linearGradient id="mg" x1="81" x2="435" y1="64" y2="456"><stop stopColor="#fff1b8"/><stop offset=".34" stopColor="#d6a946"/><stop offset=".65" stopColor="#8b641d"/><stop offset="1" stopColor="#f5d678"/></linearGradient><linearGradient id="me" x1="73" x2="456" y1="451" y2="71"><stop stopColor="#241706"/><stop offset="1" stopColor="#fff0b0"/></linearGradient></defs><path d="M80 432V94h86l94 167 94-167h86v338h-84V235l-74 126h-44l-74-126v197H80Z" fill="url(#mg)" stroke="url(#me)" strokeWidth="10" strokeLinejoin="round"/><path d="M122 138h24l114 203 114-203h24" stroke="#fff7cc" strokeOpacity=".58" strokeWidth="10"/></svg>
        </div>

        <aside className="panel terminal" id="markets">
          <div className="tabs"><span>Markets</span><span>Indices</span><span>Commodities</span><span>Forex</span><span>Crypto</span></div>
          {markets.map(([symbol, label, price, change, dir]) => <div className="market" key={symbol}><div className="coin">◇</div><div><b>{symbol}</b><small>{label}</small></div><div><Spark/><p>{price}</p><small className={dir}>{change}</small></div></div>)}
        </aside>
      </section>

      <section className="shell stats">
        <div><h2 className="display">Global Markets.<br/>Limitless Opportunities.</h2><p className="lead" style={{fontSize:14}}>Access VIP signals, digital products, and weekly trade proof from one Midas account.</p></div>
        <div className="stat"><strong>£50</strong><span>Monthly VIP</span></div><div className="stat"><strong>£265</strong><span>6 Month Access</span></div><div className="stat"><strong>£497</strong><span>1 Year VIP</span></div><div className="stat"><strong>£197</strong><span>1-to-1 Session</span></div>
      </section>

      <section className="shell strategies" id="strategies">
        <div><h2 className="display">AI-Powered Strategies</h2><p className="lead" style={{fontSize:15}}>Harness artificial intelligence and market structure logic to identify high-probability opportunities before the market moves.</p></div>
        <div className="strategyGrid">{strategies.map(([name, ret, text]) => <article className="panel card" key={name}><span className="coin">✦</span><h3>{name}</h3><p>{text}</p><Spark/><small>Return YTD</small><h3 className="green">{ret}</h3></article>)}</div>
      </section>

      <section className="shell plans" id="vip"><h2 className="display">VIP Access & Products</h2><div className="planGrid">{plans.map(([name, price, text]) => <article className="panel card" key={name}><h3>{name}</h3><div className="price">{price}</div><p>{text}</p><a className="btn gold" href="https://t.me/MidasMarketsai">Pay With Crypto</a></article>)}</div></section>

      <section className="shell socials" id="socials"><a className="panel" href="https://t.me/MidasMarketsai"><b>Telegram</b><span>Open</span></a><a className="panel" href="https://www.tiktok.com/@midasmarketsai?_r=1&_t=ZN-96CpZPsme62"><b>TikTok</b><span>Open</span></a><a className="panel" href="https://www.instagram.com/midasmarketsai?igsh=Y3AzaHU1aHA0ams="><b>Instagram</b><span>Open</span></a><a className="panel" href="https://x.com/midasmarkets_?s=21"><b>X</b><span>Open</span></a></section>

      <footer className="footer shell">MIDAS MARKETS · AI trading intelligence layer</footer>
    </main>
  );
}

function Spark(){return <svg viewBox="0 0 120 34"><path d="M2 28L12 22L22 25L32 15L42 18L52 10L62 13L72 8L82 11L92 5L104 9L118 2" stroke="#3fd36f" strokeWidth="2" fill="none"/></svg>}
