"""
scraper_engine.py  –  Multi-source news scraper with deduplication & tagging
"""
import requests, feedparser, json, hashlib, re, threading, time, os, email.utils
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from collections import defaultdict

DB_PATH = "news_db.json"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TAG_RULES = {
    "finance": {
        "stocks":       ["stock","equity","nasdaq","dow jones","s&p 500","shares","ipo","nyse","rally","selloff","bull market","bear market","wall street","ticker"],
        "crypto":       ["bitcoin","crypto","ethereum","blockchain","defi","binance","coinbase","btc","eth","solana","xrp","altcoin","nft","web3","stablecoin","cbdc"],
        "economy":      ["gdp","inflation","recession","economy","economic growth","unemployment","cpi","pce","jobs report","payrolls","consumer spending","retail sales","stagflation"],
        "fed/rates":    ["federal reserve","interest rate","rate hike","powell","fomc","rate cut","monetary policy","fed meeting","basis points","quantitative","taper"],
        "banking":      ["bank","jpmorgan","goldman sachs","morgan stanley","citibank","wells fargo","bank of america","deutsche bank","barclays","hsbc","lending","deposit"],
        "markets":      ["market","trading","hedge fund","etf","oil price","gold price","commodity","futures","options","volatility","vix","correction","crash"],
        "earnings":     ["earnings","revenue","profit","loss","quarterly results","forecast","guidance","eps","q1","q2","q3","q4","beat estimates","miss estimates"],
        "trade":        ["tariff","trade war","import","export","wto","trade deal","supply chain","sanctions","trade deficit","trade surplus","protectionism"],
        "bonds":        ["treasury","bond","yield","10-year","2-year yield","debt ceiling","deficit","credit rating","spread","junk bond","sovereign debt","fixed income"],
        "real-estate":  ["housing","mortgage","real estate","home prices","rent","reit","property market","home sales","construction","foreclosure"],
        "commodities":  ["oil","crude","natural gas","gold","silver","copper","wheat","corn","soybean","lithium","cobalt","opec","energy prices"],
        "vc/startups":  ["startup","venture capital","vc","series a","series b","unicorn","fundraising","valuation","seed round","acquisition","merger"],
        "india-markets":["nifty","sensex","bse","nse","rbi","reserve bank of india","rupee","sebi","mutual fund india","fii","fdi india"],
    },
    "geopolitics": {
        "war/conflict": ["war","conflict","missile","airstrike","troops","military","battle","ceasefire","offensive","drone attack","bombardment","casualties","front line"],
        "diplomacy":    ["diplomat","treaty","summit","united nations","nato","negotiations","accord","g7","g20","sanctions","foreign minister","state department","bilateral"],
        "middle-east":  ["israel","gaza","iran","saudi arabia","lebanon","syria","iraq","hamas","hezbollah","persian gulf","west bank","idf","netanyahu","houthi"],
        "asia-pacific": ["china","taiwan","north korea","south korea","japan","indo-pacific","south china sea","pla","xi jinping","philippines","quad"],
        "europe":       ["russia","ukraine","european union","nato europe","germany","france","poland","baltic","zelensky","putin","kremlin","moldova","belarus"],
        "africa":       ["africa","sudan","ethiopia","nigeria","kenya","sahel","mali","congo","somalia","coup","junta","peacekeeping","african union"],
        "nuclear":      ["nuclear","warhead","icbm","nuclear deterrence","nonproliferation","atomic","enrichment","iaea","npt"],
        "cyber":        ["cyberattack","hack","espionage","intelligence leak","ransomware","state-sponsored","data breach","critical infrastructure","apt"],
        "terrorism":    ["terrorism","terrorist","extremist","isis","al-qaeda","jihad","bombing","radicalization","counterterrorism"],
        "latin-america":["mexico","brazil","venezuela","colombia","argentina","chile","cuba","nicaragua","cartel","election latin"],
        "south-asia":   ["india","pakistan","afghanistan","bangladesh","kashmir","modi","sri lanka","nepal","line of control"],
    },
    "us_politics": {
        "trump":          ["trump","maga","mar-a-lago","executive order","doge","elon musk doge","deport","tariff trump","trump administration","jd vance"],
        "democrats":      ["democrat","harris","pelosi","schumer","progressive","biden","aoc","bernie","gavin newsom","democratic party"],
        "congress":       ["congress","senate","house of representatives","legislation","bill passed","vote congress","filibuster","speaker","committee hearing"],
        "supreme-court":  ["supreme court","scotus","ruling","justice","constitutional","overturned","kavanaugh","barrett","alito","sotomayor","chief justice"],
        "immigration":    ["immigration","border","migrants","asylum","dhs","ice","deportation","visa","green card","border patrol","refugee"],
        "elections":      ["election","poll","ballot","voting","campaign","primary","midterm","electoral college","swing state","debate","2026","2028"],
        "economy-policy": ["inflation policy","jobs bill","budget","deficit spending","tax cut","stimulus","debt ceiling","irs","social security","medicare"],
        "foreign-policy": ["nato policy","china policy","iran policy","ukraine aid","israel aid","foreign policy","state department","pentagon","cia"],
        "doj-fbi":        ["department of justice","fbi","attorney general","indictment","arrest","charges","trial","verdict","investigation","special counsel"],
        "tech-policy":    ["antitrust","big tech","regulate","section 230","ai regulation","data privacy","tiktok ban","google antitrust","tech monopoly"],
        "media-politics": ["fox news","cnn","msnbc","misinformation","fake news","censorship","first amendment","press freedom"],
        "state-politics": ["governor","state legislature","abortion law","gun control","red state","blue state","florida","texas politics","california"],
    },
    "technology": {
        "ai":             ["artificial intelligence","machine learning","llm","gpt","claude","gemini","openai","anthropic","deepmind","large language model","chatgpt","ai safety"],
        "semiconductors": ["chip","semiconductor","tsmc","nvidia","intel","amd","qualcomm","arm","foundry","export controls","chips act","silicon","wafer"],
        "big-tech":       ["apple","google","microsoft","amazon","meta","alphabet","tesla","spacex","nvidia","google antitrust","microsoft ai","aws"],
        "cybersecurity":  ["hack","vulnerability","ransomware","zero-day","breach","malware","phishing","cybersecurity","exploit","patch","cve"],
        "space":          ["nasa","spacex","rocket launch","satellite","orbit","moon","mars","starship","space station","artemis","blue origin"],
        "startups":       ["startup","venture","funding","series","unicorn","ipo","acquisition","merger","valuation","y combinator"],
        "ev-auto":        ["electric vehicle","tesla","ev","battery","autonomous","self-driving","rivian","lucid","ford ev","gm electric"],
    },
}

SOURCES = {
    # ── FINANCE & MARKETS ────────────────────────────────────────────────────
    "finance": [
        # Major wires & newspapers
        ("Reuters Business",       "https://feeds.reuters.com/reuters/businessNews"),
        ("Reuters Finance",        "https://feeds.reuters.com/news/wealth"),
        ("AP Business",            "https://feeds.apnews.com/rss/apf-business"),
        ("Bloomberg Markets",      "https://feeds.bloomberg.com/markets/news.rss"),
        ("Bloomberg Technology",   "https://feeds.bloomberg.com/technology/news.rss"),
        ("FT Markets",             "https://www.ft.com/markets?format=rss"),
        ("FT Companies",           "https://www.ft.com/companies?format=rss"),
        ("WSJ Markets",            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("WSJ Economy",            "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
        ("The Economist Finance",  "https://www.economist.com/finance-and-economics/rss.xml"),
        ("The Economist Business", "https://www.economist.com/business/rss.xml"),
        # TV / Digital financial media
        ("CNBC Top News",          "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("CNBC Markets",           "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("CNBC Economy",           "https://www.cnbc.com/id/20910274/device/rss/rss.html"),
        ("CNBC Investing",         "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
        ("Yahoo Finance",          "https://finance.yahoo.com/news/rssindex"),
        ("MarketWatch Top",        "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
        ("MarketWatch Economy",    "https://feeds.content.dowjones.io/public/rss/mw_economy"),
        ("Seeking Alpha",          "https://seekingalpha.com/market_currents.xml"),
        ("Seeking Alpha News",     "https://seekingalpha.com/feed.xml"),
        ("Investopedia",           "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline"),
        ("Barron's",               "https://www.barrons.com/feed/rss/topics/markets"),
        ("Kiplinger",              "https://www.kiplinger.com/rss/channel/investing"),
        ("TheStreet",              "https://www.thestreet.com/rss/main.xml"),
        ("Business Insider",       "https://feeds.businessinsider.com/custom/all"),
        ("Forbes Business",        "https://www.forbes.com/business/feed/"),
        ("Forbes Investing",       "https://www.forbes.com/investing/feed/"),
        ("Fortune Finance",        "https://fortune.com/feed/"),
        # Crypto & digital assets
        ("CoinDesk",               "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("CoinTelegraph",          "https://cointelegraph.com/rss"),
        ("Decrypt",                "https://decrypt.co/feed"),
        ("Bitcoin Magazine",       "https://bitcoinmagazine.com/.rss/full/"),
        ("The Block",              "https://www.theblock.co/rss.xml"),
        # Macro & analysis
        ("Calculated Risk",        "https://feeds.feedburner.com/calculatedriskblog"),
        ("Zero Hedge",             "https://feeds.feedburner.com/zerohedge/feed"),
        ("Wolf Street",            "https://wolfstreet.com/feed/"),
        ("Mish Talk",              "https://mishtalk.com/feed/"),
        ("Project Syndicate Econ", "https://www.project-syndicate.org/rss"),
        # Commodities & energy
        ("Oil Price",              "https://oilprice.com/rss/main"),
        ("Rigzone",                "https://www.rigzone.com/news/rss/rigzone_latest.aspx"),
        ("Mining.com",             "https://www.mining.com/feed/"),
        ("Kitco Gold",             "https://www.kitco.com/rss/kitco-news-top-stories.rss"),
        # Real estate
        ("HousingWire",            "https://www.housingwire.com/feed/"),
        ("Realtor.com News",       "https://www.realtor.com/news/feed/"),
        # India / emerging markets
        ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("Economic Times Economy", "https://economictimes.indiatimes.com/economy/rssfeeds/1373380680.cms"),
        ("Mint Markets",           "https://www.livemint.com/rss/markets"),
        ("Moneycontrol",           "https://www.moneycontrol.com/rss/marketreports.xml"),
        ("Business Standard",      "https://www.business-standard.com/rss/markets-106.rss"),
    ],

    # ── GEOPOLITICS & WORLD NEWS ─────────────────────────────────────────────
    "geopolitics": [
        # Global wires
        ("Reuters World",          "https://feeds.reuters.com/reuters/worldNews"),
        ("Reuters Top News",       "https://feeds.reuters.com/reuters/topNews"),
        ("AP World",               "https://feeds.apnews.com/rss/apf-topnews"),
        ("AP International",       "https://feeds.apnews.com/rss/apf-intlnews"),
        ("AFP via Google",         "https://news.google.com/rss/search?q=AFP+world&hl=en"),
        # BBC
        ("BBC World",              "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("BBC Europe",             "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("BBC Middle East",        "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
        ("BBC Africa",             "https://feeds.bbci.co.uk/news/world/africa/rss.xml"),
        ("BBC Asia",               "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
        ("BBC Latin America",      "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml"),
        # International broadcasters
        ("Al Jazeera",             "https://www.aljazeera.com/xml/rss/all.xml"),
        ("DW World",               "https://rss.dw.com/rdf/rss-en-all"),
        ("France 24",              "https://www.france24.com/en/rss"),
        ("RFI English",            "https://www.rfi.fr/en/rss"),
        ("Euronews",               "https://feeds.feedburner.com/euronews/en/home"),
        ("NHK World",              "https://www3.nhk.or.jp/rss/news/cat0.xml"),
        ("South China Morning Post","https://www.scmp.com/rss/91/feed"),
        ("Times of India World",   "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms"),
        ("Hindustan Times World",  "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml"),
        # Think tanks & analysis
        ("Foreign Policy",         "https://foreignpolicy.com/feed/"),
        ("Foreign Affairs",        "https://www.foreignaffairs.com/rss.xml"),
        ("Council on Foreign Relations","https://www.cfr.org/rss.xml"),
        ("Brookings",              "https://www.brookings.edu/feed/"),
        ("RAND Corporation",       "https://www.rand.org/pubs/rss/all-published.xml"),
        ("War on the Rocks",       "https://warontherocks.com/feed/"),
        ("Bellingcat",             "https://www.bellingcat.com/feed/"),
        ("The Interpreter",        "https://www.lowyinstitute.org/the-interpreter/rss.xml"),
        # UN & international orgs
        ("UN News",                "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
        ("NATO News",              "https://www.nato.int/cps/en/natolive/news.xml"),
        ("IAEA",                   "https://www.iaea.org/feeds/topstories.xml"),
        # Conflict-specific
        ("Kyiv Independent",       "https://kyivindependent.com/feed/"),
        ("Jerusalem Post",         "https://www.jpost.com/Rss/RssFeedsHeadlines.aspx"),
        ("Haaretz",                "https://www.haaretz.com/cmlink/1.628765"),
        ("Middle East Eye",        "https://www.middleeasteye.net/rss"),
        ("The Guardian World",     "https://www.theguardian.com/world/rss"),
        ("The Guardian Global Dev","https://www.theguardian.com/global-development/rss"),
        # Defense & intelligence
        ("Defense News",           "https://www.defensenews.com/arc/outboundfeeds/rss/"),
        ("Breaking Defense",       "https://breakingdefense.com/feed/"),
        ("Jane's Defense",         "https://www.janes.com/feeds/news"),
        ("The Drive (War Zone)",   "https://www.thedrive.com/the-war-zone/feed"),
        ("Asia Times",             "https://asiatimes.com/feed/"),
    ],

    # ── US POLITICS ──────────────────────────────────────────────────────────
    "us_politics": [
        # Center / wire services
        ("Reuters Politics",       "https://feeds.reuters.com/reuters/politicsNews"),
        ("AP Politics",            "https://feeds.apnews.com/rss/apf-politics"),
        ("AP Washington",          "https://feeds.apnews.com/rss/apf-washington"),
        # Center / center-left
        ("Politico",               "https://www.politico.com/rss/politicopicks.xml"),
        ("Politico Congress",      "https://www.politico.com/rss/congress.xml"),
        ("Politico Economy",       "https://www.politico.com/rss/economy.xml"),
        ("The Hill",               "https://thehill.com/feed/"),
        ("The Hill Senate",        "https://thehill.com/homenews/senate/feed/"),
        ("The Hill House",         "https://thehill.com/homenews/house/feed/"),
        ("Axios",                  "https://api.axios.com/feed/"),
        ("Axios Politics",         "https://www.axios.com/politics"),
        ("NPR Politics",           "https://feeds.npr.org/1014/rss.xml"),
        ("NPR News",               "https://feeds.npr.org/1001/rss.xml"),
        ("PBS NewsHour",           "https://www.pbs.org/newshour/feeds/rss/politics"),
        ("Washington Post Politics","https://feeds.washingtonpost.com/rss/politics"),
        ("The Guardian US",        "https://www.theguardian.com/us-news/rss"),
        ("Slate Politics",         "https://feeds.feedburner.com/Slate"),
        ("Vox Politics",           "https://www.vox.com/rss/index.xml"),
        ("The Atlantic Politics",  "https://www.theatlantic.com/feed/channel/politics/"),
        ("New Yorker Politics",    "https://www.newyorker.com/feed/news"),
        ("Talking Points Memo",    "https://talkingpointsmemo.com/feed"),
        # Right / conservative
        ("Fox News Politics",      "https://moxie.foxnews.com/google-publisher/politics.xml"),
        ("Fox News Latest",        "https://moxie.foxnews.com/google-publisher/latest.xml"),
        ("Breitbart",              "https://feeds.feedburner.com/breitbart"),
        ("Washington Examiner",    "https://www.washingtonexaminer.com/feed"),
        ("Washington Times",       "https://www.washingtontimes.com/rss/headlines/news/politics/"),
        ("National Review",        "https://www.nationalreview.com/feed/"),
        ("The Federalist",         "https://thefederalist.com/feed/"),
        ("Daily Caller",           "https://dailycaller.com/feed/"),
        ("Daily Wire",             "https://www.dailywire.com/feeds/rss.xml"),
        ("Townhall",               "https://townhall.com/rss/all"),
        ("Red State",              "https://redstate.com/feed/"),
        ("Hot Air",                "https://hotair.com/feed/"),
        # Left / progressive
        ("Mother Jones",           "https://www.motherjones.com/feed/"),
        ("The Intercept",          "https://theintercept.com/feed/?rss"),
        ("Democracy Now",          "https://www.democracynow.org/podcast.xml"),
        ("Common Dreams",          "https://www.commondreams.org/rss.xml"),
        ("Truthout",               "https://truthout.org/feed/"),
        ("Raw Story",              "https://www.rawstory.com/feed/"),
        ("AlterNet",               "https://www.alternet.org/feed/"),
        # Policy & wonk
        ("Roll Call",              "https://rollcall.com/feed/"),
        ("Congressional Digest",   "https://congressionaldigest.com/feed/"),
        ("Pew Research Politics",  "https://www.pewresearch.org/politics/feed/"),
        ("FiveThirtyEight",        "https://fivethirtyeight.com/features/feed/"),
        ("Real Clear Politics",    "https://www.realclearpolitics.com/index.xml"),
        ("The Bulwark",            "https://thebulwark.com/feed/"),
        ("The Dispatch",           "https://thedispatch.com/feed/"),
        # Legal / Justice
        ("Law360 Politics",        "https://www.law360.com/rss/articles"),
        ("SCOTUSblog",             "https://www.scotusblog.com/feed/"),
        ("Just Security",          "https://www.justsecurity.org/feed/"),
        # Trump / MAGA specific tracking
        ("Truth Social via RSS",   "https://truthsocial.com/@realDonaldTrump.rss"),
        ("MAGA News",              "https://moxie.foxnews.com/google-publisher/trump.xml"),
    ],

    # ── TECHNOLOGY & AI ──────────────────────────────────────────────────────
    "technology": [
        ("TechCrunch",             "https://techcrunch.com/feed/"),
        ("TechCrunch AI",          "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge",              "https://www.theverge.com/rss/index.xml"),
        ("Wired",                  "https://www.wired.com/feed/rss"),
        ("Ars Technica",           "https://feeds.arstechnica.com/arstechnica/index"),
        ("MIT Tech Review",        "https://www.technologyreview.com/feed/"),
        ("IEEE Spectrum",          "https://spectrum.ieee.org/feeds/feed.rss"),
        ("Hacker News",            "https://news.ycombinator.com/rss"),
        ("VentureBeat AI",         "https://venturebeat.com/category/ai/feed/"),
        ("ZDNet",                  "https://www.zdnet.com/news/rss.xml"),
        ("CNET",                   "https://www.cnet.com/rss/news/"),
        ("9to5Google",             "https://9to5google.com/feed/"),
        ("9to5Mac",                "https://9to5mac.com/feed/"),
        ("The Register",           "https://www.theregister.com/headlines.atom"),
        ("Protocol",               "https://www.protocol.com/feeds/feed.rss"),
        ("Semiconductor Engineering","https://semiengineering.com/feed/"),
        ("Chip War Updates",       "https://feeds.feedburner.com/SemiWiki"),
    ],
}

def _load():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH,"r",encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"arts":{},"hashes":[],"stats":{"total":0,"cats":{}}}

def _save(db):
    with open(DB_PATH,"w",encoding="utf-8") as f: json.dump(db, f, indent=2, ensure_ascii=False)

def _hash(title):
    return hashlib.md5(re.sub(r"[^a-z0-9]","",title.lower())[:80].encode()).hexdigest()

def _tags(title, summary, cat):
    text  = (title + " " + summary).lower()
    found = [t for t, kws in TAG_RULES.get(cat,{}).items() if any(k in text for k in kws)]
    return found if found else ["general"]

def _parse_pub(pub):
    try:
        dt = email.utils.parsedate_to_datetime(pub)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except: return datetime.now(timezone.utc).isoformat()

def _ago(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        m  = int((datetime.now(timezone.utc)-dt).total_seconds()/60)
        if m < 1: return "just now"
        if m < 60: return f"{m}m ago"
        if m < 1440: return f"{m//60}h ago"
        return f"{m//1440}d ago"
    except: return ""

def fetch_full(url, timeout=8):
    try:
        r    = requests.get(url, headers=HDR, timeout=timeout)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header","aside","iframe","noscript"]): t.decompose()
        for sel in ["article","[class*='article-body']","[class*='story-body']","[class*='content']","main"]:
            el = soup.select_one(sel)
            if el:
                txt = el.get_text("\n",strip=True)
                if len(txt) > 200: return txt[:5000]
        paras = soup.find_all("p")
        txt   = "\n".join(p.get_text(strip=True) for p in paras if len(p.get_text(strip=True))>40)
        return txt[:5000]
    except: return ""

def scrape_url(url):
    try:
        r    = requests.get(url, headers=HDR, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        title = ""
        for sel in ["h1","[class*='headline']","[class*='title']","title"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True): title = el.get_text(strip=True)[:200]; break
        meta_d = soup.find("meta",attrs={"name":"description"}) or soup.find("meta",attrs={"property":"og:description"})
        desc   = meta_d.get("content","")[:300] if meta_d else ""
        meta_i = soup.find("meta",attrs={"property":"og:image"})
        image  = meta_i.get("content","") if meta_i else ""
        pub_el = soup.select_one("time,[class*='date'],[property='article:published_time']")
        pub    = (pub_el.get("datetime") or pub_el.get("content") or pub_el.get_text()[:40]) if pub_el else ""
        for t in soup(["script","style","nav","footer","header","aside","iframe","noscript"]): t.decompose()
        body   = ""
        for sel in ["article","[class*='article-body']","[class*='content']","main"]:
            el = soup.select_one(sel)
            if el:
                body = el.get_text("\n",strip=True)
                if len(body) > 200: break
        if not body:
            body = "\n".join(p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True))>40)

        h    = _hash(title or url)
        pub_iso = _parse_pub(pub) if pub else datetime.now(timezone.utc).isoformat()
        tl   = (title + " " + body).lower()
        cat  = "geopolitics"
        if any(k in tl for k in ["stock","market","economy","fed","inflation","earnings","crypto","nasdaq","interest rate","gdp","rbi","nifty","sensex"]):
            cat = "finance"
        elif any(k in tl for k in ["trump","congress","democrat","republican","senate","election","doge","scotus","supreme court","white house"]):
            cat = "us_politics"
        elif any(k in tl for k in ["artificial intelligence","machine learning","openai","chatgpt","nvidia","semiconductor","chip","apple","google","microsoft","amazon","meta","tesla","spacex","startup","cyber"]):
            cat = "technology"
        return {
            "id":title_hash, "title":title or url, "link":url,
            "source":r.url.split("/")[2] if "/" in r.url else url,
            "cat":cat, "tags":_tags(title,body[:400],cat),
            "summary":desc or body[:300], "full_text":body[:5000], "image":image,
            "pub":pub_iso, "scraped":datetime.now(timezone.utc).isoformat(),
            "ago":_ago(pub_iso), "gemini":"", "user":True,
        }
    except Exception as e:
        return {"error":str(e), "url":url}

# Fix typo in scrape_url
import types
_orig_scrape_url = scrape_url
def scrape_url(url):
    try:
        r    = requests.get(url, headers=HDR, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        title = ""
        for sel in ["h1","[class*='headline']","[class*='title']","title"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True): title = el.get_text(strip=True)[:200]; break
        meta_d = soup.find("meta",attrs={"name":"description"}) or soup.find("meta",attrs={"property":"og:description"})
        desc   = meta_d.get("content","")[:300] if meta_d else ""
        meta_i = soup.find("meta",attrs={"property":"og:image"})
        image  = meta_i.get("content","") if meta_i else ""
        pub_el = soup.select_one("time,[class*='date'],[property='article:published_time']")
        pub    = (pub_el.get("datetime") or pub_el.get("content") or pub_el.get_text()[:40]) if pub_el else ""
        for t in soup(["script","style","nav","footer","header","aside","iframe","noscript"]): t.decompose()
        body = ""
        for sel in ["article","[class*='article-body']","[class*='content']","main"]:
            el = soup.select_one(sel)
            if el:
                body = el.get_text("\n",strip=True)
                if len(body) > 200: break
        if not body:
            body = "\n".join(p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True))>40)
        h    = _hash(title or url)
        pub_iso = _parse_pub(pub) if pub else datetime.now(timezone.utc).isoformat()
        tl   = (title + " " + body).lower()
        cat  = "geopolitics"
        if any(k in tl for k in ["stock","market","economy","fed","inflation","earnings","crypto","nasdaq","gdp","rbi","nifty","sensex"]):
            cat = "finance"
        elif any(k in tl for k in ["trump","congress","democrat","republican","senate","election","doge","scotus","white house"]):
            cat = "us_politics"
        elif any(k in tl for k in ["artificial intelligence","machine learning","openai","chatgpt","nvidia","semiconductor","chip","apple","google","microsoft","amazon","meta","spacex","startup","cyber"]):
            cat = "technology"
        return {"id":h,"title":title or url,"link":url,
                "source":r.url.split("/")[2] if "/" in (r.url or "") else url,
                "cat":cat,"tags":_tags(title,body[:400],cat),
                "summary":desc or body[:300],"full_text":body[:5000],"image":image,
                "pub":pub_iso,"scraped":datetime.now(timezone.utc).isoformat(),
                "ago":_ago(pub_iso),"gemini":"","user":True}
    except Exception as e:
        return {"error":str(e),"url":url}

def _rss_scrape(name, url, cat, db, out):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    try:
        r    = requests.get(url, headers=HDR, timeout=10)
        feed = feedparser.parse(r.content)
        for e in feed.entries[:18]:
            title = (e.get("title") or "").strip()
            link  = (e.get("link")  or "").strip()
            pub   = e.get("published") or e.get("updated") or ""
            raw   = e.get("summary") or e.get("description") or ""
            summ  = BeautifulSoup(raw,"html.parser").get_text()[:400].strip()
            if not title or len(title) < 8: continue
            h = _hash(title)
            if h in db["hashes"]: continue
            pub_iso = _parse_pub(pub)
            try:
                dt = datetime.fromisoformat(pub_iso)
                if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff: continue
            except: pass
            art = {"id":h,"title":title,"link":link,"source":name,"cat":cat,
                   "tags":_tags(title,summ,cat),"summary":summ,"full_text":"",
                   "pub":pub_iso,"scraped":datetime.now(timezone.utc).isoformat(),
                   "ago":_ago(pub_iso),"gemini":""}
            db["arts"][h] = art
            db["hashes"].append(h)
            if len(db["hashes"]) > 25000: db["hashes"] = db["hashes"][-12000:]
            db["stats"]["total"] = db["stats"].get("total",0) + 1
            db["stats"]["cats"][cat] = db["stats"]["cats"].get(cat,0) + 1
            out.append(art)
    except: pass

def _reddit(cat, db, out):
    subs = {"finance":     ["wallstreetbets","investing","stocks","Economics","SecurityAnalysis","ValueInvesting","CryptoCurrency","Bitcoin","options","StockMarket"],
            "geopolitics": ["geopolitics","worldnews","CredibleDefense","WarCollege","GlobalPowers","UkrainianConflict","IsraelPalestine"],
            "us_politics": ["politics","PoliticalDiscussion","Conservative","Liberal","moderatepolitics","uspolitics","Government"],
            "technology":  ["technology","artificial","MachineLearning","hardware","netsec","programming","singularity","OpenAI"]}
    for sub in subs.get(cat,[]):
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=8",
                             headers={"User-Agent":"SignalBot/4.0"},timeout=8)
            for post in r.json()["data"]["children"]:
                p    = post["data"]
                title = p.get("title","").strip()
                if not title or p.get("over_18"): continue
                ts  = p.get("created_utc", time.time())
                if (time.time()-ts)/3600 > 48: continue
                link = f"https://reddit.com{p.get('permalink','')}"
                h    = _hash(title)
                if h in db["hashes"]: continue
                pub_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                summ = p.get("selftext","")[:300] or f"🔺 {p.get('ups',0):,} upvotes · r/{sub}"
                art  = {"id":h,"title":title,"link":link,"source":f"r/{sub}","cat":cat,
                        "tags":_tags(title,summ,cat),"summary":summ,"full_text":"",
                        "pub":pub_iso,"scraped":datetime.now(timezone.utc).isoformat(),
                        "ago":_ago(pub_iso),"gemini":"","ups":p.get("ups",0)}
                db["arts"][h] = art; db["hashes"].append(h)
                db["stats"]["total"] = db["stats"].get("total",0)+1
                db["stats"]["cats"][cat] = db["stats"]["cats"].get(cat,0)+1
                out.append(art)
        except: pass

def run_scrape():
    db  = _load()
    new = []
    lck = threading.Lock()
    def do_rss(n,u,c):
        loc=[]; _rss_scrape(n,u,c,db,loc)
        with lck: new.extend(loc)
    def do_red(c):
        loc=[]; _reddit(c,db,loc)
        with lck: new.extend(loc)
    ts = []
    for cat, feeds in SOURCES.items():
        for n,u in feeds:
            t = threading.Thread(target=do_rss, args=(n,u,cat)); t.start(); ts.append(t)
        t2 = threading.Thread(target=do_red, args=(cat,)); t2.start(); ts.append(t2)
    for t in ts: t.join(timeout=20)
    db["last_scraped"] = datetime.now(timezone.utc).isoformat()
    _save(db)
    return new, db

def get_full_text(aid):
    db = _load(); a = db["arts"].get(aid)
    if not a: return ""
    if a.get("full_text"): return a["full_text"]
    txt = fetch_full(a.get("link",""))
    if txt: a["full_text"] = txt; db["arts"][aid] = a; _save(db)
    return txt

def get_stats():
    db  = _load()
    arts = list(db["arts"].values())
    from collections import Counter
    tag_c = Counter(); src_c = Counter()
    for a in arts:
        for t in a.get("tags",[]): tag_c[t] += 1
        src_c[a["source"]] += 1
    return {"total":len(arts), "cats":db["stats"].get("cats",{}),
            "top_tags":tag_c.most_common(30), "top_srcs":src_c.most_common(12),
            "last_scraped":db.get("last_scraped","")}

def load_db(): return _load()
def save_db(db): _save(db)