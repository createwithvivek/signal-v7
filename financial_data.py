"""
financial_data.py  –  Live market data (no API key needed)
Sources: Yahoo Finance v7, CoinGecko, alternative.me, stooq.com
Refreshes every 90 seconds in background thread.
"""
import requests, json, time, threading, os
from datetime import datetime, timezone

CACHE  = "fin_cache.json"
UA     = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HDR    = {"User-Agent": UA, "Accept": "application/json"}

# ── symbol catalogue ─────────────────────────────────────────────────────────
INDICES = [
    {"s":"^GSPC",  "n":"S&P 500",     "cat":"US"},
    {"s":"^IXIC",  "n":"NASDAQ",      "cat":"US"},
    {"s":"^DJI",   "n":"Dow Jones",   "cat":"US"},
    {"s":"^RUT",   "n":"Russell 2000","cat":"US"},
    {"s":"^VIX",   "n":"VIX",         "cat":"US"},
    {"s":"^FTSE",  "n":"FTSE 100",    "cat":"EU"},
    {"s":"^GDAXI", "n":"DAX",         "cat":"EU"},
    {"s":"^FCHI",  "n":"CAC 40",      "cat":"EU"},
    {"s":"^N225",  "n":"Nikkei 225",  "cat":"Asia"},
    {"s":"^HSI",   "n":"Hang Seng",   "cat":"Asia"},
    {"s":"000001.SS","n":"Shanghai",  "cat":"Asia"},
    {"s":"^BSESN", "n":"Sensex",      "cat":"Asia"},
    {"s":"^NSEI",  "n":"Nifty 50",    "cat":"Asia"},
]

COMMODITIES = [
    {"s":"GC=F",  "n":"Gold",          "u":"$/oz"},
    {"s":"SI=F",  "n":"Silver",        "u":"$/oz"},
    {"s":"CL=F",  "n":"Crude Oil WTI", "u":"$/bbl"},
    {"s":"BZ=F",  "n":"Brent Crude",   "u":"$/bbl"},
    {"s":"NG=F",  "n":"Natural Gas",   "u":"$/MMBtu"},
    {"s":"HG=F",  "n":"Copper",        "u":"$/lb"},
    {"s":"PL=F",  "n":"Platinum",      "u":"$/oz"},
    {"s":"PA=F",  "n":"Palladium",     "u":"$/oz"},
    {"s":"ZW=F",  "n":"Wheat",         "u":"¢/bu"},
    {"s":"ZC=F",  "n":"Corn",          "u":"¢/bu"},
    {"s":"ZS=F",  "n":"Soybeans",      "u":"¢/bu"},
    {"s":"KC=F",  "n":"Coffee",        "u":"¢/lb"},
    {"s":"SB=F",  "n":"Sugar",         "u":"¢/lb"},
]

FOREX = [
    {"s":"EURUSD=X","n":"EUR/USD"},
    {"s":"GBPUSD=X","n":"GBP/USD"},
    {"s":"USDJPY=X","n":"USD/JPY"},
    {"s":"USDCNY=X","n":"USD/CNY"},
    {"s":"USDINR=X","n":"USD/INR"},
    {"s":"USDCHF=X","n":"USD/CHF"},
    {"s":"AUDUSD=X","n":"AUD/USD"},
    {"s":"USDCAD=X","n":"USD/CAD"},
    {"s":"USDKRW=X","n":"USD/KRW"},
    {"s":"USDBRL=X","n":"USD/BRL"},
    {"s":"DX-Y.NYB","n":"DXY Index"},
]

CRYPTO_YF = [
    {"s":"BTC-USD","n":"Bitcoin",  "sym":"BTC"},
    {"s":"ETH-USD","n":"Ethereum", "sym":"ETH"},
    {"s":"BNB-USD","n":"BNB",      "sym":"BNB"},
    {"s":"SOL-USD","n":"Solana",   "sym":"SOL"},
    {"s":"XRP-USD","n":"XRP",      "sym":"XRP"},
]

ALL_SYMS = [i["s"] for i in INDICES+COMMODITIES+FOREX+CRYPTO_YF]

# ── helpers ──────────────────────────────────────────────────────────────────
def _get(url, **kw):
    try:
        r = requests.get(url, headers=HDR, timeout=12, **kw)
        return r.json()
    except Exception as e:
        print(f"[Fin] GET {url[:60]} → {e}")
        return {}

def _load():
    if os.path.exists(CACHE):
        try:
            with open(CACHE) as f: return json.load(f)
        except: pass
    return {"ts":"","data":{}}

def _save(c):
    with open(CACHE,"w") as f: json.dump(c, f)

# ── Yahoo Finance batch ───────────────────────────────────────────────────────
def _yahoo_batch(symbols):
    out = {}
    chunk = 40
    for i in range(0, len(symbols), chunk):
        syms = ",".join(symbols[i:i+chunk])
        url  = (f"https://query1.finance.yahoo.com/v7/finance/quote"
                f"?symbols={syms}&fields=shortName,regularMarketPrice,"
                f"regularMarketChange,regularMarketChangePercent,"
                f"regularMarketDayHigh,regularMarketDayLow,"
                f"regularMarketOpen,regularMarketVolume,"
                f"fiftyTwoWeekHigh,fiftyTwoWeekLow,marketCap")
        try:
            r   = requests.get(url, headers=HDR, timeout=12)
            res = r.json().get("quoteResponse",{}).get("result",[])
            for q in res:
                s   = q.get("symbol","")
                p   = q.get("regularMarketPrice")
                chg = q.get("regularMarketChange",0)
                pct = q.get("regularMarketChangePercent",0)
                out[s] = {
                    "price": round(p,6)  if p   else None,
                    "change": round(chg,4),
                    "pct":    round(pct,3),
                    "open":   q.get("regularMarketOpen"),
                    "high":   q.get("regularMarketDayHigh"),
                    "low":    q.get("regularMarketDayLow"),
                    "vol":    q.get("regularMarketVolume"),
                    "cap":    q.get("marketCap"),
                    "52h":    q.get("fiftyTwoWeekHigh"),
                    "52l":    q.get("fiftyTwoWeekLow"),
                    "name":   q.get("shortName",""),
                    "src":    "Yahoo Finance",
                }
        except Exception as e:
            print(f"[Fin] Yahoo chunk err: {e}")
        time.sleep(0.3)
    return out

# ── CoinGecko top 20 ─────────────────────────────────────────────────────────
def _coingecko():
    url = ("https://api.coingecko.com/api/v3/coins/markets"
           "?vs_currency=usd&order=market_cap_desc&per_page=20&page=1"
           "&sparkline=false&price_change_percentage=1h,24h,7d")
    data = _get(url)
    if not isinstance(data, list): return []
    out = []
    for c in data:
        out.append({
            "id":    c.get("id"),
            "name":  c.get("name"),
            "sym":   (c.get("symbol") or "").upper(),
            "price": c.get("current_price"),
            "pct1h": round(c.get("price_change_percentage_1h_in_currency") or 0, 2),
            "pct24": round(c.get("price_change_percentage_24h_in_currency") or 0, 2),
            "pct7d": round(c.get("price_change_percentage_7d_in_currency") or 0, 2),
            "cap":   c.get("market_cap"),
            "vol24": c.get("total_volume"),
            "rank":  c.get("market_cap_rank"),
            "ath":   c.get("ath"),
            "atl":   c.get("atl"),
        })
    return out

# ── Fear & Greed ──────────────────────────────────────────────────────────────
def _fng():
    data = _get("https://api.alternative.me/fng/?limit=7")
    items = data.get("data", [])
    if not items: return {}
    hist = [{"v": int(x.get("value",50)), "cls": x.get("value_classification",""),
             "ts": x.get("timestamp","")} for x in items]
    return {"current": hist[0], "history": hist}

# ── Stooq US Treasury yields ──────────────────────────────────────────────────
def _yields():
    tickers = {"2Y":"dgs2.us","5Y":"dgs5.us","10Y":"dgs10.us","30Y":"dgs30.us"}
    out = {}
    for label, sym in tickers.items():
        try:
            url  = f"https://stooq.com/q/d/l/?s={sym}&i=d"
            r    = requests.get(url, headers=HDR, timeout=8)
            rows = r.text.strip().split("\n")
            if len(rows) >= 2:
                cols = rows[-1].split(",")
                if len(cols) >= 5 and cols[4]:
                    out[label] = {"rate": float(cols[4]), "date": cols[0]}
        except: pass
    return out

# ── Global economic calendar (free Tradays feed) ─────────────────────────────
def _econ_calendar():
    try:
        url  = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        data = _get(url)
        if isinstance(data, list):
            high = [e for e in data if e.get("impact","") in ("High","Medium")]
            return sorted(high, key=lambda x: x.get("date",""))[:20]
    except: pass
    return []

# ── Full fetch ────────────────────────────────────────────────────────────────
def fetch_all():
    print("[Fin] Full fetch starting…")
    raw  = _yahoo_batch(ALL_SYMS)
    ts   = datetime.now(timezone.utc).isoformat()

    def enrich(items):
        out = []
        for item in items:
            q = raw.get(item["s"], {})
            out.append({**item, **q, "ts": ts})
        return out

    data = {
        "indices":    enrich(INDICES),
        "commodities":enrich(COMMODITIES),
        "forex":      enrich(FOREX),
        "crypto_yf":  enrich(CRYPTO_YF),
        "crypto_cg":  _coingecko(),
        "fng":        _fng(),
        "yields":     _yields(),
        "econ_cal":   _econ_calendar(),
    }
    cache = {"ts": ts, "data": data}
    _save(cache)
    print(f"[Fin] Done. Yahoo:{len(raw)} CG:{len(data['crypto_cg'])} "
          f"Yields:{list(data['yields'].keys())}")
    return cache

def get_cache():
    c = _load()
    if not c.get("data"): return fetch_all()
    return c

def start_updater(interval=90):
    def loop():
        fetch_all()
        while True:
            time.sleep(interval)
            try: fetch_all()
            except Exception as e: print(f"[Fin] loop err: {e}")
    threading.Thread(target=loop, daemon=True).start()
