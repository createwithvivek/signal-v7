"""
stock_advisor.py  –  AI-driven stock suggestions
Cross-references: geopolitics + financial data + sector trends + science breakthroughs
Uses Perplexity + Gemini for dual-AI analysis
"""
import json, re
from datetime import datetime, timezone

# ── Sector → conflict/event signal map ────────────────────────────────────────
SIGNAL_MAP = {
    "Defense & Aerospace": {
        "positive": ["escalating conflict","military buildup","nato expansion","defense spending","arms deal"],
        "negative": ["ceasefire","peace deal","defense budget cut"],
        "tickers":  [("LMT","Lockheed Martin"),("RTX","RTX Corp"),("NOC","Northrop Grumman"),("GD","General Dynamics"),("KTOS","Kratos Defense"),("BA","Boeing")],
        "etfs":     [("ITA","iShares Aerospace & Defense ETF"),("XAR","SPDR S&P Aerospace ETF")],
    },
    "Energy - Oil & Gas": {
        "positive": ["shipping disruption","middle east tension","opec cut","iran sanctions","red sea attack"],
        "negative": ["ceasefire","iran deal","opec increase","shale boom"],
        "tickers":  [("XOM","Exxon Mobil"),("CVX","Chevron"),("COP","ConocoPhillips"),("SLB","SLB"),("OXY","Occidental"),("BP","BP PLC")],
        "etfs":     [("XLE","Energy Select Sector ETF"),("VDE","Vanguard Energy ETF")],
    },
    "Gold & Precious Metals": {
        "positive": ["geopolitical crisis","recession fear","dollar weakness","inflation","safe haven"],
        "negative": ["rate hike","dollar strength","risk-on sentiment"],
        "tickers":  [("GLD","SPDR Gold Shares"),("NEM","Newmont"),("GOLD","Barrick Gold"),("WPM","Wheaton Precious"),("FNV","Franco-Nevada")],
        "etfs":     [("GDX","VanEck Gold Miners ETF")],
    },
    "Semiconductors & AI": {
        "positive": ["ai breakthrough","chip demand surge","data center expansion","llm scaling"],
        "negative": ["taiwan strait tension","china export ban","chip oversupply"],
        "tickers":  [("NVDA","NVIDIA"),("AMD","AMD"),("TSM","TSMC"),("ASML","ASML"),("AVGO","Broadcom"),("MU","Micron"),("INTC","Intel"),("QCOM","Qualcomm")],
        "etfs":     [("SOXX","iShares Semiconductor ETF"),("SMH","VanEck Semiconductor ETF")],
    },
    "Cybersecurity": {
        "positive": ["cyberattack","state-sponsored hack","data breach","ransomware","critical infrastructure attack"],
        "negative": ["cyber budget cut","market saturation"],
        "tickers":  [("CRWD","CrowdStrike"),("PANW","Palo Alto Networks"),("FTNT","Fortinet"),("S","SentinelOne"),("ZS","Zscaler"),("OKTA","Okta")],
        "etfs":     [("HACK","ETFMG Prime Cyber Security ETF"),("CIBR","First Trust Nasdaq Cybersecurity ETF")],
    },
    "Food & Agriculture": {
        "positive": ["ukraine war","drought","el nino","supply disruption","fertilizer shortage"],
        "negative": ["bumper crop","trade deal","fertilizer surplus"],
        "tickers":  [("ADM","Archer-Daniels-Midland"),("BG","Bunge Global"),("MOS","Mosaic"),("NTR","Nutrien"),("DE","Deere & Co")],
        "etfs":     [("MOO","VanEck Agribusiness ETF"),("DBA","Invesco DB Agriculture Fund")],
    },
    "Healthcare & Biotech": {
        "positive": ["pandemic","new drug approval","breakthrough therapy","aging population","ai drug discovery"],
        "negative": ["drug pricing reform","trial failure","patent cliff"],
        "tickers":  [("LLY","Eli Lilly"),("NVO","Novo Nordisk"),("MRNA","Moderna"),("BNTX","BioNTech"),("ABBV","AbbVie"),("JNJ","Johnson & Johnson"),("PFE","Pfizer")],
        "etfs":     [("XBI","SPDR S&P Biotech ETF"),("IBB","iShares Biotechnology ETF")],
    },
    "EV & Clean Energy": {
        "positive": ["climate policy","ev mandate","battery breakthrough","charging infrastructure","green deal"],
        "negative": ["ev slowdown","charging concern","raw material cost"],
        "tickers":  [("TSLA","Tesla"),("RIVN","Rivian"),("LCID","Lucid"),("BYD","BYD Co"),("ALB","Albemarle"),("ENPH","Enphase Energy")],
        "etfs":     [("LIT","Global X Lithium & Battery ETF"),("ICLN","iShares Global Clean Energy ETF")],
    },
    "Space Technology": {
        "positive": ["launch milestone","nasa contract","satellite constellation","space tourism","defense satellite"],
        "negative": ["launch failure","space budget cut"],
        "tickers":  [("RKLB","Rocket Lab"),("MAXR","Maxar Tech"),("ATRO","Astronics"),("ASTR","Astra Space"),("SPCE","Virgin Galactic")],
        "etfs":     [("UFO","Procure Space ETF"),("ARKX","ARK Space Exploration ETF")],
    },
    "Critical Minerals & Rare Earth": {
        "positive": ["drc conflict","china export ban","supply chain risk","ev demand","chips demand"],
        "negative": ["new mine discovery","recycling breakthrough","substitute material"],
        "tickers":  [("FCX","Freeport-McMoRan"),("MP","MP Materials"),("VALE","Vale SA"),("RIO","Rio Tinto"),("BHP","BHP Group"),("SCCO","Southern Copper")],
        "etfs":     [("REMX","VanEck Rare Earth/Strategic Metals ETF"),("PICK","iShares MSCI Global Metals Mining ETF")],
    },
}

CONFIDENCE_SCORES = {
    "STRONG BUY":  (85, "#16a34a"),
    "BUY":         (70, "#4ade80"),
    "WATCH":       (55, "#d97706"),
    "NEUTRAL":     (40, "#6b7280"),
    "AVOID":       (25, "#dc2626"),
}

def score_sector(sector_name, sector_data, articles, conflicts, fin_data):
    """Score a sector based on current signals."""
    pos_kws = sector_data["positive"]
    neg_kws = sector_data["negative"]
    
    # Scan articles for signals
    pos_hits = 0; neg_hits = 0; signal_arts = []
    for a in articles[:200]:
        text = (a.get("title","")+" "+a.get("summary","")).lower()
        ph   = sum(1 for kw in pos_kws if kw in text)
        nh   = sum(1 for kw in neg_kws if kw in text)
        if ph > 0 or nh > 0:
            pos_hits += ph; neg_hits += nh
            signal_arts.append({"title":a["title"],"source":a.get("source",""),"ago":a.get("ago",""),"signal":"+" if ph>nh else "-","id":a.get("id","")})

    # Conflict signals
    conf_boost = 0
    for conf in conflicts:
        if conf.get("trend")=="escalating" and conf.get("severity") in ["critical","high"]:
            cname = conf["name"].lower()
            if any(kw in cname for kw in ["russia","ukraine","iran","israel","yemen","taiwan"]):
                conf_boost += 15 if sector_name in ["Energy - Oil & Gas","Gold & Precious Metals","Defense & Aerospace"] else 0
                conf_boost += 20 if sector_name=="Semiconductors & AI" and "taiwan" in cname else 0

    # Base score calculation
    base = 50
    base += min(30, pos_hits * 3)
    base -= min(25, neg_hits * 3)
    base += conf_boost
    score = max(10, min(95, base))

    # Determine recommendation
    if score >= 75: rec = "STRONG BUY"
    elif score >= 60: rec = "BUY"
    elif score >= 45: rec = "WATCH"
    elif score >= 30: rec = "NEUTRAL"
    else: rec = "AVOID"

    conf_pct, color = CONFIDENCE_SCORES[rec]

    return {
        "sector":       sector_name,
        "score":        score,
        "recommendation": rec,
        "confidence":   conf_pct,
        "color":        color,
        "pos_signals":  min(pos_hits, 99),
        "neg_signals":  min(neg_hits, 99),
        "signal_arts":  signal_arts[:5],
        "tickers":      sector_data["tickers"],
        "etfs":         sector_data["etfs"],
        "rationale":    f"{pos_hits} positive signals, {neg_hits} negative signals. Conflict boost: +{conf_boost}.",
    }

def get_stock_suggestions(articles, conflicts, fin_data):
    """Full stock suggestion analysis across all sectors."""
    results = []
    for sector_name, sector_data in SIGNAL_MAP.items():
        scored = score_sector(sector_name, sector_data, articles, conflicts, fin_data)
        results.append(scored)
    
    results.sort(key=lambda x: -x["score"])
    
    # Top picks
    top_picks = []
    for sector in results[:4]:
        for ticker, name in sector["tickers"][:2]:
            top_picks.append({
                "ticker":   ticker,
                "name":     name,
                "sector":   sector["sector"],
                "rec":      sector["recommendation"],
                "score":    sector["score"],
                "color":    sector["color"],
                "reason":   sector["rationale"],
            })

    return {
        "sectors":   results,
        "top_picks": top_picks[:8],
        "ts":        datetime.now(timezone.utc).isoformat(),
        "disclaimer":"AI analysis only. Not financial advice. Always do your own research.",
    }

def build_stock_prompt(articles, conflicts, fin_data, science_arts=None):
    """Build comprehensive prompt for AI stock analysis."""
    fd = fin_data.get("data",{})
    
    # Market snapshot
    snap = [f"{i['n']}: {i.get('price','?')} ({i.get('pct',0):+.2f}%)"
            for i in fd.get("indices",[])[:8] if i.get("price")]
    fng  = fd.get("fng",{}).get("current",{})
    ylds = fd.get("yields",{})
    
    # Active conflict signals
    conf_signals = [f"⚔ {c['name']}: {c.get('severity','?')} severity, {c.get('trend','?')} trend, {c.get('article_count',0)} articles"
                    for c in conflicts[:8] if c.get("severity") in ["critical","high"]]
    
    # Top financial news
    fin_arts = sorted([a for a in articles if a.get("cat")=="finance"],
                      key=lambda x:x.get("pub",""), reverse=True)[:20]
    fin_hl   = "\n".join(f"• {a['title']} [{a['source']}]" for a in fin_arts)
    
    # Geopolitical news
    geo_arts = sorted([a for a in articles if a.get("cat")=="geopolitics"],
                      key=lambda x:x.get("pub",""), reverse=True)[:15]
    geo_hl   = "\n".join(f"• {a['title']}" for a in geo_arts)
    
    # Science/Tech news
    sci_hl = ""
    if science_arts:
        sci_hl = "\n".join(f"• [{a.get('domain','?').upper()}] {a['title']} [{a['source']}]" for a in science_arts[:12])

    prompt = f"""You are a senior investment strategist with expertise in geopolitical risk, macroeconomics, and sector analysis.

LIVE MARKET DATA:
{chr(10).join(snap[:10])}
Fear & Greed Index: {fng.get('v','?')} — {fng.get('cls','?')}
US Treasury Yields: {', '.join(f"{k}: {v.get('rate')}%" for k,v in ylds.items())}

ACTIVE GEOPOLITICAL CONFLICTS (HIGH IMPACT):
{chr(10).join(conf_signals) if conf_signals else 'No critical active conflicts'}

RECENT FINANCIAL NEWS:
{fin_hl}

RECENT GEOPOLITICAL NEWS:
{geo_hl}

{'SCIENCE & TECH DEVELOPMENTS:' + chr(10) + sci_hl if sci_hl else ''}

Based on ALL the above intelligence — geopolitical risks, market conditions, financial news, and scientific developments — provide:

## 🎯 MARKET OUTLOOK (current risk environment: Bullish/Neutral/Bearish + why)

## 🔥 TOP 5 STRONG BUY SECTORS (ranked, with specific reasoning tied to current events)

## 📊 TOP 10 SPECIFIC STOCK PICKS
For each stock provide:
- Ticker & Company Name
- Current catalyst (what geopolitical/financial event is driving this)
- Risk level (LOW/MEDIUM/HIGH)
- Time horizon (SHORT: 1-4 weeks / MEDIUM: 1-3 months / LONG: 6-12 months)
- Key risk to watch

## ⚠️ SECTORS TO AVOID RIGHT NOW (and why)

## 🌍 GEOPOLITICAL RISK PREMIUM (how current conflicts are pricing into markets)

## 🔬 SCIENCE/TECH OPPORTUNITIES (emerging tech plays from recent breakthroughs)

## 📉 TAIL RISKS (low probability, high impact events to hedge against)

IMPORTANT: Always include "This is not financial advice. Do your own research." at the end."""

    return prompt
