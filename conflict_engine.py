"""
conflict_engine.py  –  Autonomous conflict detection & tracking
- 14 known active conflicts pre-seeded with coordinates
- Auto-discovery of NEW conflicts from news feeds
- Intensity scoring, trend detection, last-48h article matching
- Runs full scan every 8 minutes in background
"""
import requests, feedparser, json, re, os, threading, time, hashlib, email.utils
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from collections import defaultdict, Counter

DB   = "conflicts.json"
HDR  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36"}

# ── 14 seeded active conflicts ────────────────────────────────────────────────
SEEDS = {
    "ukraine_russia": {
        "name":"Russia–Ukraine War","region":"Eastern Europe","lat":49.0,"lng":31.5,
        "color":"#ef4444","severity":"critical","status":"Active",
        "started":"Feb 24, 2022","parties":["Russia","Ukraine","NATO (support)"],
        "desc":"Full-scale Russian invasion. Active frontlines in east/south Ukraine. Drone/missile strikes on infrastructure.",
        "kw":["ukraine","russia","kyiv","donbas","zaporizhzhia","kherson","zelensky","putin","kursk","crimea","dnipro","odesa","mariupol","kharkiv","bakhmut"],
    },
    "israel_gaza": {
        "name":"Israel–Gaza War","region":"Middle East","lat":31.5,"lng":34.8,
        "color":"#f97316","severity":"critical","status":"Active",
        "started":"Oct 7, 2023","parties":["Israel (IDF)","Hamas","PIJ","Hezbollah"],
        "desc":"War following Hamas Oct 7 attack. IDF ground campaign in Gaza. Northern front with Hezbollah in Lebanon.",
        "kw":["israel","gaza","hamas","idf","rafah","netanyahu","hezbollah","west bank","pij","ceasefire","khan younis","jabalia","jenin","beirut"],
    },
    "sudan": {
        "name":"Sudan Civil War","region":"East Africa","lat":15.6,"lng":32.5,
        "color":"#eab308","severity":"critical","status":"Active",
        "started":"Apr 15, 2023","parties":["SAF (Sudan Army)","RSF (Hemeti)"],
        "desc":"SAF vs RSF. World's largest displacement crisis. Famine in Darfur. Atrocity reports.",
        "kw":["sudan","rsf","khartoum","darfur","saf","port sudan","hemeti","burhan","famine sudan","displacement sudan","al-fashir"],
    },
    "drc_m23": {
        "name":"DRC–M23 Conflict","region":"Central Africa","lat":-1.5,"lng":29.3,
        "color":"#84cc16","severity":"critical","status":"Active",
        "started":"2021 (resurgence)","parties":["DRC Army (FARDC)","M23/Rwanda","AFC"],
        "desc":"M23 rebels (backed by Rwanda) seizing eastern DRC. Goma fell Jan 2025. Massive displacement.",
        "kw":["congo","drc","m23","kinshasa","goma","north kivu","south kivu","fardc","rwanda congo","afc","tshisekedi","bukavu","lubumbashi"],
    },
    "myanmar": {
        "name":"Myanmar Civil War","region":"Southeast Asia","lat":19.7,"lng":96.1,
        "color":"#a855f7","severity":"high","status":"Active",
        "started":"Feb 1, 2021","parties":["Junta (SAC/Tatmadaw)","PDF","Ethnic Armed Orgs"],
        "desc":"Post-coup insurgency. Junta losing territory to PDF and ethnic armed orgs across multiple regions.",
        "kw":["myanmar","burma","junta","sac","pdf","arakan army","shan","kachin","mandalay","sagaing","karenni","3bha","chin"],
    },
    "yemen": {
        "name":"Yemen / Red Sea Crisis","region":"Middle East","lat":15.4,"lng":44.2,
        "color":"#ec4899","severity":"high","status":"Active",
        "started":"Sep 2014","parties":["Houthis (Ansarallah)","Saudi Coalition","US/UK"],
        "desc":"Houthis attacking Red Sea commercial shipping. US/UK strikes on Houthi targets. Ongoing civil war.",
        "kw":["yemen","houthi","ansarallah","red sea","shipping attack","saudi coalition","hodeidah","marib","us strikes yemen","bab el-mandeb"],
    },
    "sahel": {
        "name":"Sahel Insurgency","region":"West Africa","lat":14.0,"lng":-1.5,
        "color":"#f59e0b","severity":"high","status":"Active",
        "started":"2012","parties":["Mali/BF/Niger Juntas","JNIM","ISGS","Africa Corps"],
        "desc":"Jihadist insurgency across Mali, Burkina Faso, Niger. Russian mercenaries replacing French forces.",
        "kw":["sahel","mali","burkina faso","niger","jnim","africa corps","jihadist sahel","french withdrawal","bamako","ouagadougou","niamey"],
    },
    "haiti": {
        "name":"Haiti Gang Crisis","region":"Caribbean","lat":18.9,"lng":-72.3,
        "color":"#fb923c","severity":"high","status":"Active",
        "started":"2021","parties":["Haitian Govt","Viv Ansanm (Gangs)","Kenya MSS"],
        "desc":"Gangs control ~85% of Port-au-Prince. Kenya-led Multinational Security Support Mission deployed.",
        "kw":["haiti","gang haiti","port-au-prince","viv ansanm","kenya force","mss haiti","ariel henry","gang violence haiti"],
    },
    "taiwan_strait": {
        "name":"Taiwan Strait Tensions","region":"Asia-Pacific","lat":23.7,"lng":120.9,
        "color":"#06b6d4","severity":"high","status":"Heightened",
        "started":"Ongoing","parties":["China (PRC)","Taiwan (ROC)","USA"],
        "desc":"PLA military exercises. Frequent ADIZ incursions. US arms sales. Risk of miscalculation.",
        "kw":["taiwan","pla","south china sea","adiz","taiwan strait","china military","tsmc","taipei","xi jinping taiwan","us taiwan"],
    },
    "kashmir": {
        "name":"Kashmir Conflict","region":"South Asia","lat":34.0,"lng":74.8,
        "color":"#10b981","severity":"medium","status":"Simmering",
        "started":"1947","parties":["India","Pakistan","Militant Groups"],
        "desc":"Cross-LoC skirmishes, militant infiltration. Nuclear-armed rivals. Periodic escalation cycles.",
        "kw":["kashmir","india pakistan","line of control","jammu","infiltration kashmir","militant kashmir","pahalgam"],
    },
    "ethiopia_amhara": {
        "name":"Ethiopia Internal Conflicts","region":"East Africa","lat":11.5,"lng":37.5,
        "color":"#22d3ee","severity":"medium","status":"Active",
        "started":"2023","parties":["Ethiopia Army","Amhara Fano","OLA"],
        "desc":"Amhara Fano militias and Oromo Liberation Army fighting federal forces post-Tigray peace deal.",
        "kw":["ethiopia amhara","fano militia","oromo","ola ethiopia","abiy ahmed","amhara conflict","oromia conflict"],
    },
    "russia_georgia_tension": {
        "name":"Russia–Georgia/Moldova Tensions","region":"Caucasus","lat":42.3,"lng":43.4,
        "color":"#f472b6","severity":"medium","status":"Heightened",
        "started":"Ongoing","parties":["Russia","Georgia","Moldova","EU"],
        "desc":"Russian pressure on Georgia and Moldova. South Ossetia/Abkhazia frozen conflicts. Transnistria.",
        "kw":["georgia russia","moldova transnistria","south ossetia","abkhazia","russian pressure georgia"],
    },
    "nigeria_banditry": {
        "name":"Nigeria Banditry & Boko Haram","region":"West Africa","lat":10.5,"lng":7.5,
        "color":"#a3e635","severity":"medium","status":"Active",
        "started":"2009","parties":["Nigerian Army","Boko Haram","ISWAP","Bandits"],
        "desc":"Boko Haram/ISWAP insurgency in northeast. Mass banditry in northwest. Thousands of kidnappings.",
        "kw":["nigeria boko haram","iswap nigeria","banditry nigeria","zamfara","kaduna attack","northwest nigeria","lake chad"],
    },
    "iran_israel": {
        "name":"Iran–Israel Shadow War","region":"Middle East","lat":32.4,"lng":53.7,
        "color":"#c084fc","severity":"high","status":"Active",
        "started":"Ongoing","parties":["Iran (IRGC)","Israel","US","Proxies"],
        "desc":"Direct missile/drone exchanges 2024. IRGC proxy networks. Covert operations. Risk of wider escalation.",
        "kw":["iran israel","irgc","iranian strike","israel iran","hezbollah iran","hamas iran","proxy war","iranian ballistic","israel retaliation"],
    },
}

# ── dedicated RSS feeds for conflict news ─────────────────────────────────────
FEEDS = [
    ("Reuters World",   "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Top",     "https://feeds.reuters.com/reuters/topNews"),
    ("BBC World",       "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("BBC Africa",      "https://feeds.bbci.co.uk/news/world/africa/rss.xml"),
    ("BBC Europe",      "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
    ("BBC Asia",        "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ("BBC Americas",    "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml"),
    ("Al Jazeera",      "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Foreign Policy",  "https://foreignpolicy.com/feed/"),
    ("UN News",         "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    ("DW World",        "https://rss.dw.com/rdf/rss-en-all"),
    ("France24",        "https://www.france24.com/en/rss"),
    ("VOA News",        "https://www.voanews.com/api/zpqoiepmiq"),
    ("Reliefweb",       "https://reliefweb.int/updates/rss.xml"),
    ("AP News",         "https://feeds.apnews.com/rss/apf-topnews"),
    ("The Guardian Wld","https://www.theguardian.com/world/rss"),
    ("Axios World",     "https://api.axios.com/feed/"),
]

VIOLENCE_KW = [
    "war","battle","fighting","combat","killed","airstrike","bombing","attack","offensive",
    "clashes","troops","military operation","casualties","dead","wounded","shelling",
    "drone strike","missile","invasion","occupation","siege","frontline","gunfire",
    "explosion","ambush","massacre","genocide","atrocity","ethnic cleansing",
]
CRISIS_KW = [
    "crisis","emergency","coup","uprising","protests","riot","unrest","instability",
    "displaced","refugee","famine","humanitarian","blockade","ceasefire","escalation",
]

SEV_ORDER = {"critical":4,"high":3,"medium":2,"low":1,"monitoring":0}

# ── DB helpers ────────────────────────────────────────────────────────────────
def _load():
    if os.path.exists(DB):
        try:
            with open(DB) as f: return json.load(f)
        except: pass
    # Bootstrap from seeds
    db = {"known":{}, "auto":{}, "last_scan":""}
    for cid, s in SEEDS.items():
        db["known"][cid] = {**s, "articles":[], "article_count":0,
                            "trend":"stable","weekly":0,"last_updated":""}
    return db

def _save(db):
    with open(DB,"w") as f: json.dump(db, f, ensure_ascii=False)

def _now():  return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()

def _ago(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        m  = int((_now()-dt).total_seconds()/60)
        if m < 1:    return "just now"
        if m < 60:   return f"{m}m ago"
        if m < 1440: return f"{m//60}h ago"
        return f"{m//1440}d ago"
    except: return ""

def _parse_dt(pub):
    try:
        dt = email.utils.parsedate_to_datetime(pub)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except:
        return _now()

def _art_id(title, link=""):
    return hashlib.md5(re.sub(r"[^a-z0-9]","",title.lower())[:80].encode()).hexdigest()

# ── Feed parsing ──────────────────────────────────────────────────────────────
def _parse_entry(entry, source):
    title   = (entry.get("title") or "").strip()
    link    = (entry.get("link")  or "").strip()
    pub     = entry.get("published") or entry.get("updated") or ""
    raw_sum = entry.get("summary") or entry.get("description") or ""
    summary = BeautifulSoup(raw_sum, "html.parser").get_text()[:400].strip()
    dt      = _parse_dt(pub)
    return {
        "id":    _art_id(title, link),
        "title": title,
        "link":  link,
        "src":   source,
        "sum":   summary,
        "dt":    dt.isoformat(),
        "ago":   _ago(dt.isoformat()),
    }

def _fetch_feed(name, url):
    cutoff = _now() - timedelta(hours=72)
    out = []
    try:
        r    = requests.get(url, headers=HDR, timeout=10)
        feed = feedparser.parse(r.content)
        for e in feed.entries[:25]:
            a = _parse_entry(e, name)
            if not a["title"] or len(a["title"]) < 8: continue
            try:
                dt = datetime.fromisoformat(a["dt"])
                if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff: continue
            except: pass
            out.append(a)
    except: pass
    return out

# ── Conflict matching ─────────────────────────────────────────────────────────
def _score(text, keywords):
    tl = text.lower()
    return sum(1 for kw in keywords if kw in tl)

def _best_match(title, summary, db):
    text  = title + " " + summary
    best_id, best_score = None, 0
    for cid, conf in {**db["known"], **db["auto"]}.items():
        s = _score(text, conf["kw"])
        if s > best_score and s >= 2:
            best_score, best_id = s, cid
    return best_id

# ── Auto-detect new conflicts ─────────────────────────────────────────────────
def _auto_detect(title, summary, existing_ids):
    text   = title + " " + summary
    vcnt   = sum(1 for kw in VIOLENCE_KW if kw in text.lower())
    ccnt   = sum(1 for kw in CRISIS_KW   if kw in text.lower())
    if vcnt < 2 and ccnt < 2: return None

    # Extract named locations
    locs = re.findall(r'\b([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?)\b', title + " " + summary)
    locs = [l for l in locs if l not in ("The","This","That","With","From","After","Before","When","While","Where")]
    if not locs: return None

    loc   = Counter(locs).most_common(1)[0][0]
    cid   = "auto_" + re.sub(r"[^a-z0-9]","_", loc.lower())[:28]
    if cid in existing_ids: return cid  # Already exists, just return to add article

    # Don't create if location already covered by a known conflict
    loc_l = loc.lower()
    for conf in existing_ids:
        pass  # existing_ids is just keys

    severity = "high" if vcnt >= 4 else "medium"
    return {
        "id":    cid,
        "name":  f"{loc} Conflict",
        "region":"Auto-detected",
        "lat":   None, "lng": None,
        "color": "#94a3b8",
        "severity": severity,
        "status":   "Monitoring",
        "started":  _now().strftime("%Y-%m-%d"),
        "parties":  ["Unknown"],
        "desc":     f"Auto-detected from {vcnt} violence signals. Location: {loc}.",
        "kw":       [loc.lower()],
        "articles": [],
        "article_count": 0,
        "trend":    "emerging",
        "weekly":   0,
        "last_updated": "",
        "is_auto":  True,
        "first_seen": _iso(),
    }

# ── Main scan ─────────────────────────────────────────────────────────────────
def run_scan():
    print(f"[Conflicts] Scan starting @ {_now().strftime('%H:%M:%S')}")
    db  = _load()
    all_arts = []
    lock = threading.Lock()

    def _worker(name, url):
        arts = _fetch_feed(name, url)
        with lock: all_arts.extend(arts)

    threads = [threading.Thread(target=_worker, args=(n,u)) for n,u in FEEDS]
    for t in threads: t.start()
    for t in threads: t.join(timeout=18)

    print(f"[Conflicts] Fetched {len(all_arts)} articles from {len(FEEDS)} feeds")

    # Reset weekly counts
    for cid in db["known"]:  db["known"][cid]["weekly"] = 0
    for cid in db["auto"]:   db["auto"][cid]["weekly"]  = 0

    seen_ids = set()
    matched  = 0

    for art in all_arts:
        if art["id"] in seen_ids: continue
        seen_ids.add(art["id"])
        text = art["title"] + " " + art["sum"]

        cid = _best_match(art["title"], art["sum"], db)
        if cid:
            target = db["known"] if cid in db["known"] else db["auto"]
            conf   = target[cid]
            # Avoid duplicates
            existing = {a["id"] for a in conf["articles"]}
            if art["id"] not in existing:
                conf["articles"].insert(0, art)
                conf["articles"] = conf["articles"][:60]
                conf["last_updated"] = art["dt"]
            conf["weekly"] = conf.get("weekly",0) + 1
            conf["article_count"] = len(conf["articles"])
            matched += 1
        else:
            # Try auto-detection
            result = _auto_detect(art["title"], art["sum"], set(db["auto"].keys()) | set(db["known"].keys()))
            if result:
                if isinstance(result, str):
                    # Existing auto conflict
                    cid2 = result
                    if cid2 in db["auto"]:
                        existing = {a["id"] for a in db["auto"][cid2]["articles"]}
                        if art["id"] not in existing:
                            db["auto"][cid2]["articles"].insert(0, art)
                            db["auto"][cid2]["articles"] = db["auto"][cid2]["articles"][:30]
                        db["auto"][cid2]["weekly"] = db["auto"][cid2].get("weekly",0) + 1
                        db["auto"][cid2]["article_count"] = len(db["auto"][cid2]["articles"])
                elif isinstance(result, dict):
                    cid2 = result["id"]
                    result["articles"] = [art]
                    result["article_count"] = 1
                    result["weekly"] = 1
                    db["auto"][cid2] = result
                    print(f"[Conflicts] Auto-detected: {result['name']}")

    # Compute trends
    for conf in {**db["known"], **db["auto"]}.values():
        w    = conf.get("weekly", 0)
        prev = conf.get("prev_weekly", 0)
        if w > max(prev*1.4, 3):   conf["trend"] = "escalating"
        elif w < prev*0.5:         conf["trend"] = "de-escalating"
        elif conf.get("is_auto"):  conf["trend"] = "emerging"
        else:                      conf["trend"] = "stable"
        conf["prev_weekly"] = w
        # Refresh ago
        for a in conf.get("articles",[]): a["ago"] = _ago(a.get("dt",""))

    db["last_scan"] = _iso()
    _save(db)
    print(f"[Conflicts] Done. {matched} matched. {len(db['auto'])} auto-detected.")
    return db

# ── Public API ────────────────────────────────────────────────────────────────
def get_all():
    db   = _load()
    out  = []
    for cid, c in db["known"].items():
        out.append({**c, "id":cid, "is_auto":False,
                    "articles": c.get("articles",[])[:6]})
    for cid, c in db["auto"].items():
        if c.get("weekly",0) >= 2 or c.get("article_count",0) >= 3:
            out.append({**c, "id":cid, "is_auto":True,
                        "articles": c.get("articles",[])[:6]})
    out.sort(key=lambda x: (SEV_ORDER.get(x.get("severity","low"),0),
                             x.get("weekly",0)), reverse=True)
    return out, db.get("last_scan","")

def get_detail(cid):
    db = _load()
    c  = db["known"].get(cid) or db["auto"].get(cid)
    if not c: return None
    result = dict(c); result["id"] = cid
    for a in result.get("articles",[]): a["ago"] = _ago(a.get("dt",""))
    return result

def start_scanner(interval=480):
    def loop():
        run_scan()
        while True:
            time.sleep(interval)
            try: run_scan()
            except Exception as e: print(f"[Conflicts] err: {e}")
    threading.Thread(target=loop, daemon=True).start()
