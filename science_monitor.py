"""
science_monitor.py  –  Space · Medical · Tech breakthrough monitor
Separate RSS sources, keyword extraction, auto-tagging, 72h cache
"""
import requests, feedparser, json, re, os, threading, time, hashlib, email.utils
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

DB   = "science_db.json"
HDR  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SOURCES = {
    "space": [
        ("NASA",             "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
        ("SpaceNews",        "https://spacenews.com/feed/"),
        ("Space.com",        "https://www.space.com/feeds/all"),
        ("Ars Technica Space","https://feeds.arstechnica.com/arstechnica/space"),
        ("NASASpaceflight",  "https://www.nasaspaceflight.com/feed/"),
        ("ESA",              "https://www.esa.int/rssfeed/Our_Activities/Space_Science"),
        ("SpaceWeather",     "https://spaceweather.com/spaceweather.xml"),
        ("The Planetary Soc","https://www.planetary.org/news?format=rss"),
    ],
    "medical": [
        ("NIH News",         "https://www.nih.gov/rss/news.xml"),
        ("MedicalXpress",    "https://medicalxpress.com/rss-feed/"),
        ("ScienceDaily Med", "https://www.sciencedaily.com/rss/health_medicine.xml"),
        ("WHO News",         "https://www.who.int/rss-feeds/news-english.xml"),
        ("New England JM",   "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm"),
        ("The Lancet",       "https://www.thelancet.com/rssfeed/lancet_online.xml"),
        ("STAT News",        "https://www.statnews.com/feed/"),
        ("Reuters Health",   "https://feeds.reuters.com/reuters/healthNews"),
    ],
    "tech": [
        ("Ars Technica Tech","https://feeds.arstechnica.com/arstechnica/technology-lab"),
        ("MIT Tech Review",  "https://www.technologyreview.com/feed/"),
        ("The Verge",        "https://www.theverge.com/rss/index.xml"),
        ("Wired",            "https://www.wired.com/feed/rss"),
        ("TechCrunch",       "https://techcrunch.com/feed/"),
        ("IEEE Spectrum",    "https://spectrum.ieee.org/feeds/feed.rss"),
        ("Hacker News",      "https://hnrss.org/frontpage"),
        ("AI News",          "https://www.artificialintelligence-news.com/feed/"),
        ("DeepMind Blog",    "https://deepmind.google/blog/feed/basic"),
        ("OpenAI Blog",      "https://openai.com/news/rss.xml"),
    ],
}

TAG_RULES = {
    "space": {
        "launch":      ["launch","rocket","liftoff","spacecraft","satellite","orbit"],
        "mars":        ["mars","martian","red planet","perseverance","ingenuity"],
        "moon":        ["moon","lunar","artemis","gateway","moonshot"],
        "astronomy":   ["galaxy","black hole","nebula","telescope","exoplanet","james webb","hubble"],
        "commercial":  ["spacex","blue origin","rocket lab","virgin galactic","starship","falcon"],
        "iss":         ["space station","iss","astronaut","cosmonaut","crew dragon"],
        "solar":       ["solar flare","solar storm","cme","spaceweather","sun"],
        "defense":     ["space force","satellite defense","anti-satellite","missile defense"],
    },
    "medical": {
        "cancer":      ["cancer","tumor","oncology","immunotherapy","chemotherapy","crispr cancer"],
        "ai-medicine": ["ai diagnosis","machine learning medicine","medical ai","drug discovery ai"],
        "vaccine":     ["vaccine","vaccination","mrna","immunization","booster"],
        "pandemic":    ["pandemic","epidemic","outbreak","virus","pathogen","WHO"],
        "genetics":    ["gene therapy","crispr","dna","genome","genetic","rna"],
        "longevity":   ["aging","longevity","lifespan","anti-aging","senescence"],
        "drug":        ["fda approval","clinical trial","drug approval","pharmaceutical","treatment"],
        "neuroscience":["brain","neuron","alzheimer","parkinson","dementia","neural"],
    },
    "tech": {
        "ai":          ["artificial intelligence","machine learning","llm","gpt","gemini","claude","neural network"],
        "quantum":     ["quantum computing","qubit","quantum supremacy","quantum processor"],
        "chips":       ["semiconductor","chip","processor","nvidia","tsmc","intel","amd"],
        "robotics":    ["robot","robotics","humanoid","automation","autonomous"],
        "energy":      ["fusion","nuclear energy","solar energy","battery","renewable","hydrogen"],
        "cybersecurity":["cybersecurity","hack","vulnerability","zero-day","malware","ransomware"],
        "crypto-web3": ["blockchain","crypto","web3","defi","nft","ethereum"],
        "ev":          ["electric vehicle","ev","battery","tesla","charging"],
    },
}

BREAKTHRU_KW = [
    "breakthrough","first ever","world first","historic","unprecedented","discovered",
    "new study","scientists find","researchers develop","major advance","game changer",
    "revolutionary","milestone","landmark","approval","successfully","record-breaking",
]

def _now():  return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()
def _h(s):   return hashlib.md5(re.sub(r"[^a-z0-9]","",s.lower())[:80].encode()).hexdigest()

def _ago(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        m  = int((_now()-dt).total_seconds()/60)
        if m<1: return "just now"
        if m<60: return f"{m}m ago"
        if m<1440: return f"{m//60}h ago"
        return f"{m//1440}d ago"
    except: return ""

def _parse_pub(pub):
    try:
        dt = email.utils.parsedate_to_datetime(pub)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except: return _iso()

def _tags(title, summary, domain):
    text  = (title+" "+summary).lower()
    found = [t for t, kws in TAG_RULES.get(domain,{}).items() if any(k in text for k in kws)]
    return found[:4] if found else ["general"]

def _is_breakthru(title, summary):
    text = (title+" "+summary).lower()
    return any(k in text for k in BREAKTHRU_KW)

def _load():
    if os.path.exists(DB):
        try:
            with open(DB) as f: return json.load(f)
        except: pass
    return {"arts":{},"hashes":[],"last_scraped":""}

def _save(db):
    with open(DB,"w") as f: json.dump(db, f, indent=2, ensure_ascii=False)

def scrape_domain(domain, db, new_arts):
    cutoff = _now() - timedelta(hours=72)
    for name, url in SOURCES.get(domain,[]):
        try:
            r    = requests.get(url, headers=HDR, timeout=10)
            feed = feedparser.parse(r.content)
            for e in feed.entries[:15]:
                title = (e.get("title") or "").strip()
                link  = (e.get("link")  or "").strip()
                pub   = e.get("published") or e.get("updated") or ""
                raw   = e.get("summary") or e.get("description") or ""
                summ  = BeautifulSoup(raw,"html.parser").get_text()[:400].strip()
                if not title or len(title)<8: continue
                h = _h(title)
                if h in db["hashes"]: continue
                pub_iso = _parse_pub(pub)
                try:
                    dt = datetime.fromisoformat(pub_iso)
                    if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff: continue
                except: pass
                art = {
                    "id":         h,
                    "title":      title,
                    "link":       link,
                    "source":     name,
                    "domain":     domain,
                    "tags":       _tags(title, summ, domain),
                    "summary":    summ,
                    "pub":        pub_iso,
                    "scraped":    _iso(),
                    "ago":        _ago(pub_iso),
                    "breakthru":  _is_breakthru(title, summ),
                    "gemini":     "",
                }
                db["arts"][h]  = art
                db["hashes"].append(h)
                if len(db["hashes"]) > 15000: db["hashes"] = db["hashes"][-8000:]
                new_arts.append(art)
        except: pass

def run_scrape():
    print("[Science] Scrape starting…")
    db  = _load()
    new = []
    import threading as thr
    lock = thr.Lock()
    def do(domain):
        loc = []; scrape_domain(domain, db, loc)
        with lock: new.extend(loc)
    ts = [thr.Thread(target=do,args=(d,)) for d in SOURCES]
    for t in ts: t.start()
    for t in ts: t.join(timeout=22)
    db["last_scraped"] = _iso()
    _save(db)
    print(f"[Science] Done. {len(new)} new arts")
    return new, db

def get_articles(domain="", tag="", breakthru_only=False, q="", pg=1, pp=25):
    db   = _load()
    arts = list(db["arts"].values())
    if domain:         arts = [a for a in arts if a["domain"]==domain]
    if tag:            arts = [a for a in arts if tag in a.get("tags",[])]
    if breakthru_only: arts = [a for a in arts if a.get("breakthru")]
    if q:              arts = [a for a in arts if q.lower() in a["title"].lower() or q.lower() in a.get("summary","").lower()]
    arts.sort(key=lambda x: x.get("pub",""), reverse=True)
    for a in arts: a["ago"] = _ago(a.get("pub",""))
    total = len(arts); s = (pg-1)*pp
    return {"arts":arts[s:s+pp],"total":total,"pg":pg,"pages":(total+pp-1)//pp,"last_scraped":db.get("last_scraped","")}

def get_stats():
    db = _load(); arts = list(db["arts"].values())
    from collections import Counter
    dom = Counter(a["domain"] for a in arts)
    bt  = sum(1 for a in arts if a.get("breakthru"))
    return {"total":len(arts),"by_domain":dict(dom),"breakthroughs":bt,"last_scraped":db.get("last_scraped","")}

def start_monitor(interval=300):
    def loop():
        run_scrape()
        while True:
            time.sleep(interval)
            try: run_scrape()
            except Exception as e: print(f"[Science] Loop err: {e}")
    threading.Thread(target=loop, daemon=True).start()

import threading
