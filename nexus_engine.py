"""
nexus_engine.py  –  Causal Link Tree Engine
Connects: News → Conflicts → Market Impact → Political Consequence → Outcomes
Auto-builds connection graphs from shared keywords and entity co-occurrence
"""
import json, re, hashlib, os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

NEXUS_DB = "nexus_db.json"

def _now():  return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()

# ── Named entity extraction (lightweight, no NLTK needed) ────────────────────
COUNTRY_LIST = [
    "Russia","Ukraine","China","Taiwan","USA","US","Israel","Gaza","Iran","Saudi Arabia",
    "UK","France","Germany","Japan","South Korea","India","Pakistan","Turkey","Brazil",
    "Sudan","Congo","DRC","Myanmar","Yemen","Haiti","Mali","Niger","Burkina Faso","Ethiopia",
    "Nigeria","Kenya","Somalia","Lebanon","Syria","Iraq","Afghanistan","North Korea",
    "Venezuela","Cuba","Poland","Hungary","NATO","EU","UN",
]

ORG_LIST = [
    "Federal Reserve","Fed","ECB","IMF","World Bank","OPEC","NATO","WHO","UN",
    "SpaceX","Tesla","NVIDIA","Apple","Microsoft","Google","Meta","Amazon","OpenAI",
    "Hamas","Hezbollah","ISIS","Wagner","Houthi","Ansarallah","M23","RSF",
    "IDF","Pentagon","CIA","FBI","NSA","IRGC","PLA","Kremlin","White House","Congress",
]

SECTOR_MAP = {
    "oil":       ["CL=F","BZ=F","XOM","CVX","SLB","HAL"],
    "gold":      ["GC=F","GLD","NEM","GOLD"],
    "defense":   ["LMT","RTX","NOC","GD","BA","KTOS"],
    "tech":      ["NVDA","AMD","INTC","TSMC","AAPL","MSFT","GOOGL","META"],
    "crypto":    ["BTC-USD","ETH-USD","SOL-USD"],
    "wheat":     ["ZW=F","ADM","BG","MOS"],
    "copper":    ["HG=F","FCX","SCCO"],
    "pharma":    ["JNJ","PFE","MRNA","BNTX","NVO","LLY"],
    "space":     ["RKLB","SPCE","MAXR","ASTR"],
    "chips":     ["NVDA","TSM","ASML","AMD","INTC","AVGO","MU"],
}

CONFLICT_SECTOR_IMPACT = {
    "ukraine_russia": {"oil":"+","nat_gas":"+","wheat":"+","gold":"+","defense":"+","euro":"-"},
    "israel_gaza":    {"oil":"+","gold":"+","defense":"+","shipping":"-"},
    "iran_israel":    {"oil":"++","gold":"+","brent":"++","shipping":"--"},
    "yemen":          {"oil":"+","shipping":"-","gold":"+"},
    "taiwan_strait":  {"tech":"--","chips":"--","aapl":"-","nvidia":"-","tsmc":"--"},
    "drc_m23":        {"cobalt":"+","copper":"+","ev_batteries":"+"},
    "ukraine_russia+sanctions": {"russia_stocks":"--","rub":"-","energy":"+"},
}

def extract_entities(text):
    """Extract countries, orgs, tickers from text."""
    tl = text.lower()
    countries = [c for c in COUNTRY_LIST if c.lower() in tl]
    orgs      = [o for o in ORG_LIST if o.lower() in tl]
    tickers   = re.findall(r'\b([A-Z]{2,5})\b', text)
    tickers   = [t for t in tickers if t not in ("IS","AS","AT","BY","IN","ON","OR","TO","UP","AN","THE","AND","FOR","WITH","BUT","NOT","FROM")]
    return {"countries": list(set(countries)), "orgs": list(set(orgs)), "tickers": list(set(tickers[:8]))}

def build_nexus(articles, conflicts, fin_data):
    """
    Build a nexus graph connecting all data sources.
    Returns nodes + edges for visualization.
    """
    nodes = {}
    edges = []
    
    def add_node(nid, label, ntype, data=None, color=None):
        if nid not in nodes:
            nodes[nid] = {"id":nid,"label":label,"type":ntype,"data":data or {},"color":color or "#888","children":[],"parents":[]}
        return nid

    # ── Layer 1: Conflict nodes ────────────────────────────────────────────
    conf_map = {c["id"]:c for c in conflicts}
    for conf in conflicts[:12]:
        cid   = "conf_"+conf["id"]
        color = conf.get("color","#ef4444")
        add_node(cid, conf["name"], "conflict", {
            "severity":     conf.get("severity","?"),
            "trend":        conf.get("trend","?"),
            "region":       conf.get("region","?"),
            "article_count":conf.get("article_count",0),
        }, color)

    # ── Layer 2: Recent news → link to conflicts ───────────────────────────
    cutoff = _now() - timedelta(hours=48)
    for art in articles[:80]:
        try:
            dt = datetime.fromisoformat(art.get("pub",""))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff: continue
        except: continue

        text   = art["title"]+" "+art.get("summary","")
        ents   = extract_entities(text)
        aid    = "art_"+art["id"][:10]
        add_node(aid, art["title"][:60]+"…" if len(art["title"])>60 else art["title"],
                 "news", {"source":art.get("source",""),"pub":art.get("pub",""),"cat":art.get("cat",""),"id":art["id"]},
                 "#6366f1")

        # Link news → conflicts via shared keywords
        for conf in conflicts[:12]:
            kws    = conf.get("kw",[])
            score  = sum(1 for kw in kws if kw in text.lower())
            if score >= 2:
                cid = "conf_"+conf["id"]
                edges.append({"from":aid,"to":cid,"type":"reports_on","weight":score,"label":f"{score} kw matches"})
                if cid not in nodes[aid]["children"]: nodes[aid]["children"].append(cid)
                if aid not in nodes[cid]["parents"]: nodes[cid]["parents"].append(aid)

        # Link news → country nodes
        for country in ents["countries"][:3]:
            cnid = "country_"+re.sub(r"[^a-z]","_",country.lower())
            add_node(cnid, country, "country", {}, "#0ea5e9")
            edges.append({"from":aid,"to":cnid,"type":"mentions","weight":1})

    # ── Layer 3: Conflicts → Market impacts ───────────────────────────────
    fd    = fin_data.get("data",{})
    all_m = {i["s"]:i for cat in ["commodities","forex","indices","crypto_yf"] for i in fd.get(cat,[])}

    for conf in conflicts[:12]:
        cid        = "conf_"+conf["id"]
        impacts    = CONFLICT_SECTOR_IMPACT.get(conf["id"],{})
        for sector, direction in impacts.items():
            mid   = "market_"+sector
            color = "#16a34a" if "+" in direction else "#dc2626"
            add_node(mid, sector.replace("_"," ").title(), "market", {"direction":direction,"sector":sector}, color)
            edges.append({"from":cid,"to":mid,"type":"market_impact","direction":direction,"label":f"→ {direction}"})

    # ── Layer 4: Market → Stock implications ─────────────────────────────
    for sector, tickers in SECTOR_MAP.items():
        sid   = "market_"+sector
        if sid not in nodes: continue
        direction = nodes[sid].get("data",{}).get("direction","")
        for ticker in tickers[:3]:
            item = all_m.get(ticker,{})
            tid  = "stock_"+ticker
            pct  = item.get("pct",0)
            add_node(tid, ticker, "stock", {
                "price": item.get("price"),
                "pct":   pct,
                "name":  item.get("n",ticker),
            }, "#16a34a" if pct and pct>0 else "#dc2626" if pct and pct<0 else "#888")
            edges.append({"from":sid,"to":tid,"type":"affects","label":ticker})

    # ── Layer 5: Outcome predictions ─────────────────────────────────────
    OUTCOME_RULES = [
        {"trigger":"escalating","conflict_id":"ukraine_russia","outcome":"European energy crisis deepens → EUR/USD pressure","color":"#ef4444"},
        {"trigger":"escalating","conflict_id":"iran_israel","outcome":"Strait of Hormuz risk → Oil price spike +15-25%","color":"#ef4444"},
        {"trigger":"escalating","conflict_id":"taiwan_strait","outcome":"Global chip shortage → Tech sector selloff","color":"#ef4444"},
        {"trigger":"escalating","conflict_id":"drc_m23","outcome":"Cobalt supply disruption → EV battery cost spike","color":"#f97316"},
        {"trigger":"critical","conflict_id":"sudan","outcome":"Regional humanitarian crisis → aid organizations surge","color":"#eab308"},
        {"trigger":"escalating","conflict_id":"yemen","outcome":"Suez Canal shipping blocked → global trade costs +8-12%","color":"#ef4444"},
    ]
    for rule in OUTCOME_RULES:
        conf = conf_map.get(rule["conflict_id"],{})
        if conf.get("trend")==rule["trigger"] or conf.get("severity")==rule["trigger"]:
            oid  = "outcome_"+hashlib.md5(rule["outcome"].encode()).hexdigest()[:8]
            cid  = "conf_"+rule["conflict_id"]
            add_node(oid, rule["outcome"], "outcome", {"trigger":rule["trigger"]}, rule["color"])
            edges.append({"from":cid,"to":oid,"type":"potential_outcome","label":"⚠ predicted"})

    # ── Deduplicate edges ─────────────────────────────────────────────────
    seen_e = set()
    uniq_e = []
    for e in edges:
        key = e["from"]+"→"+e["to"]
        if key not in seen_e:
            seen_e.add(key)
            uniq_e.append(e)

    # ── Summary stats ─────────────────────────────────────────────────────
    type_counts = {}
    for n in nodes.values():
        type_counts[n["type"]] = type_counts.get(n["type"],0)+1

    return {
        "nodes":  list(nodes.values()),
        "edges":  uniq_e,
        "stats":  {"nodes":len(nodes),"edges":len(uniq_e),"by_type":type_counts},
        "ts":     _iso(),
    }

def get_nexus_summary(nexus):
    """Get human-readable summary of key connections."""
    outcomes = [n for n in nexus["nodes"] if n["type"]=="outcome"]
    market_impacts = [n for n in nexus["nodes"] if n["type"]=="market"]
    conflict_nodes = [n for n in nexus["nodes"] if n["type"]=="conflict"]
    return {
        "outcomes":   outcomes[:8],
        "markets":    market_impacts[:10],
        "conflicts":  [{"id":n["id"],"label":n["label"],"data":n["data"]} for n in conflict_nodes],
        "edge_count": len(nexus["edges"]),
        "node_count": len(nexus["nodes"]),
    }
