"""
intelligence_engine.py  –  Advanced intelligence features
Powers: Watchlist, Sentiment, Correlations, Threat Board,
        Portfolio, Briefing Scheduler, Trend Analysis, Risk Scores, Alerts
"""
import json, os, re, time, threading, hashlib
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

# ── file paths ────────────────────────────────────────────────────────────────
WATCHLIST_F  = "watchlist.json"
PORTFOLIO_F  = "portfolio.json"
ALERTS_F     = "alerts.json"
BRIEFS_F     = "briefs_history.json"
RISK_F       = "risk_scores.json"

def _now(): return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()
def _ago(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        m = int((_now()-dt).total_seconds()/60)
        if m<1: return "just now"
        if m<60: return f"{m}m ago"
        if m<1440: return f"{m//60}h ago"
        return f"{m//1440}d ago"
    except: return ""

def _jload(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def _jsave(path, data):
    with open(path,"w") as f: json.dump(data, f, indent=2, ensure_ascii=False)

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 1 — WATCHLIST
# ═══════════════════════════════════════════════════════════════════════════════
def watchlist_get():
    return _jload(WATCHLIST_F, {"items":[], "hits":[]})

def watchlist_add(keyword, label="", category="all", notify=True):
    wl = watchlist_get()
    wid = hashlib.md5(keyword.lower().encode()).hexdigest()[:8]
    # Remove if exists
    wl["items"] = [i for i in wl["items"] if i["id"]!=wid]
    wl["items"].append({
        "id": wid, "keyword": keyword.strip(), "label": label or keyword,
        "category": category, "notify": notify,
        "created": _iso(), "hit_count": 0, "last_hit": ""
    })
    _jsave(WATCHLIST_F, wl)
    return wid

def watchlist_remove(wid):
    wl = watchlist_get()
    wl["items"] = [i for i in wl["items"] if i["id"]!=wid]
    _jsave(WATCHLIST_F, wl)

def watchlist_scan_articles(articles):
    """Check all articles against watchlist, return new hits."""
    wl  = watchlist_get()
    if not wl["items"]: return []
    new_hits = []
    seen_hit_ids = {h["hit_id"] for h in wl.get("hits",[])}
    for item in wl["items"]:
        kw  = item["keyword"].lower()
        cat = item["category"]
        for a in articles:
            if cat != "all" and a.get("cat","") != cat: continue
            text = (a.get("title","")+" "+a.get("summary","")).lower()
            if kw in text:
                hid = item["id"]+"_"+a["id"]
                if hid not in seen_hit_ids:
                    hit = {
                        "hit_id":    hid,
                        "watch_id":  item["id"],
                        "keyword":   item["keyword"],
                        "label":     item["label"],
                        "article_id":a["id"],
                        "title":     a["title"],
                        "source":    a.get("source",""),
                        "cat":       a.get("cat",""),
                        "pub":       a.get("pub",""),
                        "ts":        _iso(),
                        "ago":       _ago(a.get("pub","")),
                    }
                    new_hits.append(hit)
                    seen_hit_ids.add(hid)
                    item["hit_count"] = item.get("hit_count",0)+1
                    item["last_hit"]  = _iso()
    if new_hits:
        wl["hits"] = (new_hits + wl.get("hits",[])) [:500]
        _jsave(WATCHLIST_F, wl)
    return new_hits

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 2 — SENTIMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
BULL_KW = ["rally","surge","gain","rise","jump","soar","record high","bullish","growth","recovery",
           "breakthrough","ceasefire","deal","agreement","stability","positive","optimism","upgrade",
           "beat expectations","strong","robust","above forecast","advance"]
BEAR_KW = ["crash","plunge","fall","drop","decline","fear","recession","crisis","war","attack",
           "escalation","sanctions","default","downgrade","miss","below forecast","weak","slump",
           "selloff","collapse","invasion","militant","explosion","bombing","killed","conflict"]

def _sentiment_score(text):
    """Returns score from -100 (very bearish) to +100 (very bullish)."""
    tl = text.lower()
    b  = sum(1 for w in BULL_KW if w in tl)
    br = sum(1 for w in BEAR_KW if w in tl)
    total = b + br
    if total == 0: return 0
    return round(((b - br) / total) * 100)

def compute_sentiment(articles):
    """Compute sentiment breakdown by category and top topics."""
    by_cat   = defaultdict(list)
    by_hour  = defaultdict(list)
    by_topic = defaultdict(list)

    for a in articles:
        text   = a.get("title","") + " " + a.get("summary","")
        score  = _sentiment_score(text)
        cat    = a.get("cat","other")
        by_cat[cat].append(score)
        try:
            dt   = datetime.fromisoformat(a.get("pub",""))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            hour = dt.strftime("%Y-%m-%dT%H:00:00+00:00")
            by_hour[hour].append(score)
        except: pass
        for tag in a.get("tags",[]):
            by_topic[tag].append(score)

    def avg(lst): return round(sum(lst)/len(lst)) if lst else 0

    cat_scores = {cat: {"score": avg(scores), "count": len(scores),
                         "bull": sum(1 for s in scores if s>10),
                         "bear": sum(1 for s in scores if s<-10),
                         "neutral": sum(1 for s in scores if -10<=s<=10)}
                  for cat, scores in by_cat.items()}

    # Hourly timeline (last 24 hours)
    now_dt = _now()
    timeline = []
    for h in range(23, -1, -1):
        dt   = now_dt - timedelta(hours=h)
        hkey = dt.strftime("%Y-%m-%dT%H:00:00+00:00")
        scores = by_hour.get(hkey, [])
        timeline.append({"hour": dt.strftime("%H:00"), "score": avg(scores), "count": len(scores)})

    # Top bearish / bullish topics
    topic_scores = {t: avg(s) for t, s in by_topic.items() if len(s)>=2}
    top_bearish  = sorted(topic_scores.items(), key=lambda x:x[1])[:5]
    top_bullish  = sorted(topic_scores.items(), key=lambda x:-x[1])[:5]

    return {
        "by_category": cat_scores,
        "timeline":    timeline,
        "top_bearish": [{"topic":t,"score":s} for t,s in top_bearish],
        "top_bullish": [{"topic":t,"score":s} for t,s in top_bullish],
        "overall":     avg([s for sl in by_cat.values() for s in sl]),
        "ts":          _iso(),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 3 — CORRELATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
CONFLICT_ASSET_MAP = {
    "yemen":          ["CL=F","BZ=F","HG=F"],   # Oil, Brent, Copper
    "ukraine_russia": ["NG=F","ZW=F","GC=F"],   # Gas, Wheat, Gold
    "israel_gaza":    ["GC=F","CL=F"],           # Gold, Oil
    "iran_israel":    ["GC=F","CL=F","BZ=F"],    # Gold, Oil, Brent
    "taiwan_strait":  ["EURUSD=X","^HSI"],       # EUR/USD, Hang Seng
    "drc_m23":        ["HG=F"],                  # Copper (DRC produces ~75%)
    "sahel":          ["ZC=F","ZW=F"],           # Corn, Wheat (food security)
    "sudan":          ["GC=F"],                  # Gold (Sudan gold mines)
}

KNOWN_CORRELATIONS = [
    {"type":"conflict→commodity","from":"Yemen Houthi Attacks","to":"Oil (WTI/Brent)",
     "direction":"↑","strength":"STRONG","note":"Red Sea shipping disruption raises oil shipping cost. Each escalation → +2-4% oil spike historically.","color":"#ef4444"},
    {"type":"conflict→commodity","from":"Russia–Ukraine War","to":"Natural Gas + Wheat",
     "direction":"↑","strength":"STRONG","note":"Ukraine = breadbasket. Russia cuts gas. Both assets spike on escalation news.","color":"#f97316"},
    {"type":"conflict→safe-haven","from":"Any Critical Conflict","to":"Gold + CHF + JPY",
     "direction":"↑","strength":"MODERATE","note":"Classic flight to safety. Gold +1-3% on major conflict escalations.","color":"#eab308"},
    {"type":"conflict→equity","from":"Taiwan Strait Tension","to":"US Tech + Semiconductors",
     "direction":"↓","strength":"STRONG","note":"TSMC produces 90% of advanced chips. Taiwan blockade = systemic risk for NVIDIA, Apple, AMD.","color":"#a855f7"},
    {"type":"conflict→currency","from":"Sahel Instability","to":"EUR (via France exposure)",
     "direction":"↓","strength":"WEAK","note":"France's economic exposure to former colonies. Coup waves weaken EUR sentiment.","color":"#06b6d4"},
    {"type":"sanctions→market","from":"Russia Sanctions","to":"Commodities Broadly",
     "direction":"↑","strength":"STRONG","note":"Russia = top exporter of oil, gas, wheat, fertilizer, palladium. Sanction tightening lifts all.","color":"#ef4444"},
    {"type":"conflict→commodity","from":"DRC M23 Conflict","to":"Cobalt + Copper",
     "direction":"↑","strength":"MODERATE","note":"DRC = 70% of global cobalt. Conflict disrupts mining → EV battery supply chain stress.","color":"#84cc16"},
    {"type":"policy→market","from":"Fed Rate Decisions","to":"DXY + Gold + EM Currencies",
     "direction":"varies","strength":"VERY STRONG","note":"Rate hike → DXY up, Gold down, EM sell-off. Rate cut → reverse. Most reliable correlation in markets.","color":"#3b82f6"},
]

def get_correlations(fin_data, conflict_data):
    """Enrich correlations with current price data."""
    result = []
    fd = fin_data.get("data",{})
    all_items = {i["s"]:i for cat in ["indices","commodities","forex","crypto_yf"] for i in fd.get(cat,[])}

    for cor in KNOWN_CORRELATIONS:
        result.append({**cor})

    # Dynamic: check which conflict-linked assets moved today
    dynamic = []
    for cid, assets in CONFLICT_ASSET_MAP.items():
        conf = next((c for c in conflict_data if c.get("id")==cid), None)
        if not conf: continue
        if conf.get("trend")=="escalating":
            for sym in assets:
                item = all_items.get(sym,{})
                if item.get("pct"):
                    pct = item.get("pct",0)
                    if abs(pct) > 0.5:
                        dynamic.append({
                            "type":"live-correlation","from":conf["name"],
                            "to":item.get("n",sym),
                            "direction":"↑" if pct>0 else "↓",
                            "strength":"LIVE",
                            "note":f"Conflict escalating. {item.get('n',sym)} moved {pct:+.2f}% today.",
                            "color":"#22c55e" if pct>0 else "#ef4444",
                            "live":True, "pct":pct,
                        })
    return {"static": result, "dynamic": dynamic, "ts": _iso()}

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 4 — GLOBAL THREAT BOARD
# ═══════════════════════════════════════════════════════════════════════════════
THREAT_LEVELS = {5:"CRITICAL",4:"HIGH",3:"ELEVATED",2:"GUARDED",1:"LOW"}
THREAT_COLORS = {5:"#dc2626",4:"#ea580c",3:"#d97706",2:"#2563eb",1:"#16a34a"}

def compute_threat_board(articles, conflicts):
    """Auto-compute global threat level from news + conflict data."""
    # Count critical/high conflict articles in last 24h
    now_dt  = _now()
    cutoff  = now_dt - timedelta(hours=24)
    recent  = []
    for a in articles:
        try:
            dt = datetime.fromisoformat(a.get("pub",""))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff: recent.append(a)
        except: pass

    # Count violence keywords in recent articles
    viol_words = ["airstrike","attack","bombing","killed","troops","offensive","missile","invasion",
                  "nuclear","chemical weapon","coup","explosion","massacre"]
    viol_count = sum(1 for a in recent for w in viol_words if w in (a.get("title","")+a.get("summary","")).lower())

    critical_confs = [c for c in conflicts if c.get("severity")=="critical"]
    high_confs     = [c for c in conflicts if c.get("severity")=="high"]
    escalating     = [c for c in conflicts if c.get("trend")=="escalating"]

    # Compute domain scores
    scores = {}

    # Military/Security
    mil_score = min(5, 1 + len(critical_confs) + len(escalating)//2 + viol_count//10)
    scores["Military"] = {"score":mil_score,"detail":f"{len(critical_confs)} critical, {len(escalating)} escalating conflicts. {viol_count} violence signals (24h)."}

    # Economic
    eco_signals = sum(1 for a in recent if a.get("cat")=="finance" and
                      any(w in a.get("title","").lower() for w in ["recession","crash","crisis","default","collapse","sanctions"]))
    eco_score   = min(5, 1 + eco_signals//3)
    scores["Economic"] = {"score":eco_score,"detail":f"{eco_signals} economic stress signals in last 24h articles."}

    # Political
    pol_signals = sum(1 for a in recent if a.get("cat")=="us_politics" and
                      any(w in a.get("title","").lower() for w in ["shutdown","impeach","coup","election fraud","constitutional crisis"]))
    pol_score   = min(5, 1 + pol_signals//3)
    scores["Political"] = {"score":pol_score,"detail":f"{pol_signals} political instability signals in last 24h."}

    # Humanitarian
    hum_signals = sum(1 for a in recent if any(w in (a.get("title","")+a.get("summary","")).lower()
                      for w in ["famine","displacement","refugee","epidemic","flood","earthquake","disaster"]))
    hum_score   = min(5, 1 + hum_signals//4)
    scores["Humanitarian"] = {"score":hum_score,"detail":f"{hum_signals} humanitarian crisis signals."}

    # Nuclear/CBRN
    nuc_signals = sum(1 for a in recent if any(w in (a.get("title","")+a.get("summary","")).lower()
                      for w in ["nuclear","chemical weapon","biological","dirty bomb","radiation"]))
    nuc_score   = min(5, 1 + nuc_signals*2)
    scores["Nuclear/CBRN"] = {"score":nuc_score,"detail":f"{nuc_signals} nuclear/CBRN signals."}

    # Cyber
    cyb_signals = sum(1 for a in recent if any(w in (a.get("title","")+a.get("summary","")).lower()
                      for w in ["cyberattack","hack","ransomware","espionage","data breach","critical infrastructure"]))
    cyb_score   = min(5, 1 + cyb_signals//2)
    scores["Cyber"] = {"score":cyb_score,"detail":f"{cyb_signals} cyber threat signals."}

    # Overall = weighted average
    weights = {"Military":3,"Economic":2,"Political":1.5,"Humanitarian":1,"Nuclear/CBRN":2.5,"Cyber":1.5}
    total_w = sum(weights.values())
    overall = sum(scores[d]["score"]*weights[d] for d in scores) / total_w
    overall_int = min(5, max(1, round(overall)))

    return {
        "overall":       overall_int,
        "level_name":    THREAT_LEVELS[overall_int],
        "level_color":   THREAT_COLORS[overall_int],
        "domains":       {d: {**v, "level":THREAT_LEVELS[v["score"]], "color":THREAT_COLORS[v["score"]]}
                          for d,v in scores.items()},
        "recent_count":  len(recent),
        "viol_count":    viol_count,
        "ts":            _iso(),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 5 — PORTFOLIO TRACKER
# ═══════════════════════════════════════════════════════════════════════════════
def portfolio_get():
    return _jload(PORTFOLIO_F, {"holdings":[]})

def portfolio_add(symbol, name, qty, buy_price, asset_type="stock"):
    pf  = portfolio_get()
    pid = hashlib.md5(symbol.upper().encode()).hexdigest()[:8]
    pf["holdings"] = [h for h in pf["holdings"] if h["symbol"]!=symbol.upper()]
    pf["holdings"].append({
        "id": pid, "symbol": symbol.upper(), "name": name or symbol,
        "qty": float(qty), "buy_price": float(buy_price),
        "asset_type": asset_type, "added": _iso()
    })
    _jsave(PORTFOLIO_F, pf)
    return pid

def portfolio_remove(symbol):
    pf = portfolio_get()
    pf["holdings"] = [h for h in pf["holdings"] if h["symbol"]!=symbol.upper()]
    _jsave(PORTFOLIO_F, pf)

def portfolio_enrich(fin_data):
    """Enrich portfolio with live prices and P&L."""
    pf  = portfolio_get()
    fd  = fin_data.get("data",{})
    all_items = {}
    for cat in ["indices","commodities","forex","crypto_yf","crypto_cg"]:
        for item in fd.get(cat,[]):
            sym = item.get("s") or item.get("sym")
            if sym: all_items[sym.upper()] = item
    # Also try by name for crypto_cg
    for c in fd.get("crypto_cg",[]):
        all_items[(c.get("sym","")).upper()] = c

    enriched = []
    total_invested = 0; total_current = 0
    for h in pf["holdings"]:
        sym   = h["symbol"]
        item  = all_items.get(sym,{})
        price = item.get("price") or item.get("current_price")
        qty   = h["qty"]; buy = h["buy_price"]
        invested = qty * buy
        current  = qty * price if price else None
        pnl      = current - invested if current else None
        pnl_pct  = (pnl/invested*100) if pnl is not None and invested>0 else None
        total_invested += invested
        if current: total_current += current
        enriched.append({**h,
            "current_price": price,
            "pct_today":     item.get("pct",0),
            "invested":      round(invested,2),
            "current_value": round(current,2) if current else None,
            "pnl":           round(pnl,2)     if pnl is not None else None,
            "pnl_pct":       round(pnl_pct,2) if pnl_pct is not None else None,
        })
    total_pnl     = total_current - total_invested if total_current else None
    total_pnl_pct = (total_pnl/total_invested*100) if total_pnl is not None and total_invested>0 else None
    return {
        "holdings":        enriched,
        "total_invested":  round(total_invested,2),
        "total_current":   round(total_current,2) if total_current else None,
        "total_pnl":       round(total_pnl,2)     if total_pnl is not None else None,
        "total_pnl_pct":   round(total_pnl_pct,2) if total_pnl_pct is not None else None,
        "ts":              _iso(),
    }

def portfolio_get_news(articles):
    """Get news relevant to portfolio holdings."""
    pf   = portfolio_get()
    if not pf["holdings"]: return []
    keywords = [(h["symbol"].lower(), h["name"].lower()) for h in pf["holdings"]]
    relevant = []
    seen = set()
    for a in articles:
        text = (a.get("title","")+" "+a.get("summary","")).lower()
        for sym, name in keywords:
            if sym in text or (len(name)>3 and name in text):
                if a["id"] not in seen:
                    relevant.append({**a,"matched":sym.upper()})
                    seen.add(a["id"])
                    break
    return sorted(relevant, key=lambda x: x.get("pub",""), reverse=True)[:30]

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 6 — BRIEFING SCHEDULER + HISTORY
# ═══════════════════════════════════════════════════════════════════════════════
def briefs_get():
    return _jload(BRIEFS_F, {"briefs":[], "schedule_hours":6})

def briefs_save_new(text, brief_type="master", model=""):
    db = briefs_get()
    bid = hashlib.md5((_iso()+text[:50]).encode()).hexdigest()[:10]
    db["briefs"].insert(0, {
        "id":    bid,
        "type":  brief_type,
        "text":  text,
        "model": model,
        "ts":    _iso(),
        "ago":   "just now",
    })
    db["briefs"] = db["briefs"][:20]  # Keep last 20
    _jsave(BRIEFS_F, db)
    return bid

def briefs_list():
    db = briefs_get()
    for b in db["briefs"]: b["ago"] = _ago(b.get("ts",""))
    return db["briefs"]

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 7 — TREND ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
def compute_trend_analysis(articles, conflicts):
    """Article volume over time per conflict + sentiment trend."""
    now_dt   = _now()
    results  = {}

    for conf in conflicts[:14]:
        cid  = conf["id"]
        kws  = conf.get("kw",[])
        if not kws: continue

        # Bin articles by day (last 30 days)
        day_counts    = defaultdict(int)
        day_sentiment = defaultdict(list)

        for a in articles:
            text = (a.get("title","")+" "+a.get("summary","")).lower()
            if not any(kw in text for kw in kws): continue
            try:
                dt  = datetime.fromisoformat(a.get("pub",""))
                if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                if (_now()-dt).days > 30: continue
                day = dt.strftime("%m-%d")
                day_counts[day]   += 1
                day_sentiment[day].append(_sentiment_score(text))
            except: pass

        if not day_counts: continue

        # Build 14-day timeline (fill zeros)
        timeline = []
        for d in range(13,-1,-1):
            dt  = now_dt - timedelta(days=d)
            key = dt.strftime("%m-%d")
            sc  = day_sentiment.get(key,[])
            timeline.append({
                "date":      key,
                "count":     day_counts.get(key,0),
                "sentiment": round(sum(sc)/len(sc)) if sc else 0,
            })

        peak = max(day_counts.values()) if day_counts else 0
        results[cid] = {
            "name":     conf["name"],
            "timeline": timeline,
            "peak":     peak,
            "total":    sum(day_counts.values()),
            "trend":    conf.get("trend","stable"),
            "color":    conf.get("color","#888"),
        }

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 8 — GEOPOLITICAL RISK SCORES
# ═══════════════════════════════════════════════════════════════════════════════
COUNTRY_CONFLICT_MAP = {
    "Ukraine":    ["ukraine_russia"],"Russia":["ukraine_russia"],
    "Israel":     ["israel_gaza","iran_israel"],"Gaza/Palestine":["israel_gaza"],
    "Iran":       ["iran_israel"],"Lebanon":["israel_gaza"],
    "Sudan":      ["sudan"],"Congo (DRC)":["drc_m23"],
    "Myanmar":    ["myanmar"],"Yemen":["yemen"],
    "Mali":       ["sahel"],"Burkina Faso":["sahel"],"Niger":["sahel"],
    "Haiti":      ["haiti"],"Taiwan":["taiwan_strait"],
    "India":      ["kashmir"],"Pakistan":["kashmir"],
    "Ethiopia":   ["ethiopia_amhara"],"Nigeria":["nigeria_banditry"],
    "Georgia":    ["russia_georgia_tension"],
}

def compute_risk_scores(conflicts, articles):
    """Score countries/regions by conflict + news volume."""
    # Severity weights
    sev_w = {"critical":100,"high":70,"medium":40,"low":20,"monitoring":10}
    trend_w = {"escalating":1.5,"stable":1.0,"de-escalating":0.6,"emerging":1.2}

    # News frequency in last 7 days per keyword
    now_dt  = _now()
    cutoff  = now_dt - timedelta(days=7)
    kw_freq = defaultdict(int)
    for a in articles:
        try:
            dt = datetime.fromisoformat(a.get("pub",""))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff: continue
        except: continue
        text = (a.get("title","")+" "+a.get("summary","")).lower()
        for conf in conflicts:
            for kw in conf.get("kw",[]):
                if kw in text:
                    kw_freq[conf["id"]] += 1
                    break

    conf_map = {c["id"]:c for c in conflicts}
    results  = []
    for country, cids in COUNTRY_CONFLICT_MAP.items():
        score  = 0
        detail = []
        for cid in cids:
            c = conf_map.get(cid,{})
            if not c: continue
            base = sev_w.get(c.get("severity","low"),10)
            tw   = trend_w.get(c.get("trend","stable"),1.0)
            freq = min(50, kw_freq.get(cid,0))  # cap at 50
            s    = (base * tw) + (freq * 0.5)
            score += s
            detail.append(f"{c.get('name','?')} ({c.get('severity','?')}, {c.get('trend','?')})")

        score = min(100, round(score))
        level = "CRITICAL" if score>=80 else "HIGH" if score>=60 else "ELEVATED" if score>=40 else "MODERATE" if score>=20 else "LOW"
        color = "#dc2626" if score>=80 else "#ea580c" if score>=60 else "#d97706" if score>=40 else "#2563eb" if score>=20 else "#16a34a"
        results.append({
            "country": country, "score": score, "level": level,
            "color": color, "conflicts": detail, "news_7d": sum(kw_freq.get(c,0) for c in cids)
        })

    results.sort(key=lambda x: -x["score"])
    return results[:25]

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 9 — ALERT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
def alerts_get():
    return _jload(ALERTS_F, {"rules":[],"history":[]})

def alerts_add(keyword, label="", severity="any", sound=True):
    db  = alerts_get()
    aid = hashlib.md5((keyword+_iso()).encode()).hexdigest()[:8]
    db["rules"].append({
        "id":       aid,
        "keyword":  keyword.strip(),
        "label":    label or keyword,
        "severity": severity,
        "sound":    sound,
        "created":  _iso(),
        "active":   True,
        "hit_count":0,
    })
    _jsave(ALERTS_F, db)
    return aid

def alerts_remove(aid):
    db = alerts_get()
    db["rules"] = [r for r in db["rules"] if r["id"]!=aid]
    _jsave(ALERTS_F, db)

def alerts_check(articles):
    """Return new alert triggers."""
    db   = alerts_get()
    if not db["rules"]: return []
    seen = {h["trigger_id"] for h in db.get("history",[])}
    new_alerts = []
    for rule in db["rules"]:
        if not rule.get("active"): continue
        kw = rule["keyword"].lower()
        for a in articles:
            text = (a.get("title","")+" "+a.get("summary","")).lower()
            if kw in text:
                tid = rule["id"]+"_"+a["id"]
                if tid not in seen:
                    alert = {
                        "trigger_id":  tid,
                        "rule_id":     rule["id"],
                        "keyword":     rule["keyword"],
                        "label":       rule["label"],
                        "article_id":  a["id"],
                        "title":       a["title"],
                        "source":      a.get("source",""),
                        "cat":         a.get("cat",""),
                        "pub":         a.get("pub",""),
                        "ts":          _iso(),
                        "sound":       rule.get("sound",True),
                    }
                    new_alerts.append(alert)
                    seen.add(tid)
                    rule["hit_count"] = rule.get("hit_count",0)+1
    if new_alerts:
        db["history"] = (new_alerts + db.get("history",[])) [:300]
        _jsave(ALERTS_F, db)
    return new_alerts

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 10 — ARTICLE COMPARATOR
# ═══════════════════════════════════════════════════════════════════════════════
def find_similar_articles(article_id, articles, limit=8):
    """Find articles covering the same story from different sources."""
    target = next((a for a in articles if a["id"]==article_id), None)
    if not target: return []

    # Extract key nouns from title (3+ letter words, capitalized)
    words = re.findall(r'\b([A-Z][a-z]{2,}|[A-Z]{2,})\b', target["title"])
    words = [w.lower() for w in words if w.lower() not in ("the","and","for","with","that","this","from","after","into","over","about","been","have")]

    if not words: return []

    scored = []
    for a in articles:
        if a["id"] == article_id: continue
        text  = a["title"].lower()
        score = sum(1 for w in words if w in text)
        if score >= 2 and abs(datetime.fromisoformat(a.get("pub","1970-01-01")).replace(tzinfo=timezone.utc).timestamp() -
                              datetime.fromisoformat(target.get("pub","1970-01-01")).replace(tzinfo=timezone.utc).timestamp()) < 86400*3:
            scored.append((score, a))

    scored.sort(key=lambda x:-x[0])
    results = []
    seen_srcs = set()
    for score, a in scored[:limit*2]:
        if a["source"] not in seen_srcs:
            a_copy = {**a, "match_score": score}
            a_copy["sentiment"] = _sentiment_score(a.get("title","")+" "+a.get("summary",""))
            results.append(a_copy)
            seen_srcs.add(a["source"])
        if len(results) >= limit: break
    return results
