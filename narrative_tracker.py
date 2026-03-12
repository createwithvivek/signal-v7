"""
narrative_tracker.py  —  Media Narrative Analysis Engine
Tracks story evolution, detects bias/spin, compares coverage across sources
"""
import json, os, re, hashlib
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

NARR_F = "narratives.json"

# Source bias classifications (simplified, educational)
SOURCE_LEAN = {
    "Reuters":          "center",       "AP":               "center",
    "BBC":              "center-left",  "Guardian":         "left",
    "CNN":              "center-left",  "Fox News":         "right",
    "NYT":              "center-left",  "Wall Street Journal":"center-right",
    "Washington Post":  "center-left",  "Breitbart":        "right",
    "CNBC":             "center",       "Bloomberg":        "center",
    "Al Jazeera":       "center-left",  "RT":               "state-media",
    "TASS":             "state-media",  "Xinhua":           "state-media",
    "Financial Times":  "center",       "The Economist":    "center",
    "Politico":         "center",       "NPR":              "center-left",
    "Axios":            "center",       "The Hill":         "center",
    "Zero Hedge":       "right",        "Jacobin":          "left",
    "Vox":              "left",         "National Review":  "right",
    "Hacker News":      "center",       "Reddit":           "center",
}
LEAN_COLOR = {
    "left":         "#6b3fa0",
    "center-left":  "#3b82f6",
    "center":       "#8a9bb0",
    "center-right": "#f97316",
    "right":        "#ef4444",
    "state-media":  "#dc2626",
}

# Framing detection keywords
FRAMING_SIGNALS = {
    "alarmist":   ["catastrophic","devastating","unprecedented crisis","total collapse","apocalyptic","dire","alarming","shocking"],
    "minimizing": ["minor incident","small-scale","isolated","contained","manageable","routine","nothing to see"],
    "emotional":  ["tragic","heartbreaking","outrage","horrifying","terrifying","brave","heroic","courageous"],
    "technical":  ["analysis","report","study","data","statistics","percentage","gdp","metrics","quarterly"],
    "nationalistic":["our troops","our country","the enemy","they attacked us","defend our","patriots"],
    "diplomatic": ["negotiations","talks","ceasefire","agreement","dialogue","diplomacy","summit","treaty"],
}

PROPAGANDA_SIGNALS = [
    ("emotional_overload",  ["horrific","barbaric","genocide","evil","monster","tyrant","regime","terrorists"],    3),
    ("dehumanization",      ["animals","vermin","rats","insects","subhuman","filth"],                              1),
    ("false_certainty",     ["definitely","certainly will","100%","guaranteed","no doubt","proven conspiracy"],    3),
    ("us_vs_them",          ["either with us or against us","betrayal","traitors","enemies within"],               2),
    ("victim_narrative",    ["unfair","targeted","persecuted","discriminated","scapegoated"],                      3),
]

def _now(): return datetime.now(timezone.utc)

def _load():
    if os.path.exists(NARR_F):
        try:
            with open(NARR_F) as f: return json.load(f)
        except: pass
    return {"topics": {}, "source_stats": {}, "last_analysis": ""}

def _save(db):
    with open(NARR_F, "w") as f: json.dump(db, f, indent=2, ensure_ascii=False)

def detect_framing(text):
    """Detect framing style in text."""
    text_l = text.lower()
    scores = {}
    for frame, keywords in FRAMING_SIGNALS.items():
        scores[frame] = sum(1 for kw in keywords if kw in text_l)
    dominant = max(scores, key=scores.get) if any(scores.values()) else "neutral"
    return {"scores": scores, "dominant": dominant if scores[dominant] > 0 else "neutral"}

def detect_propaganda(text):
    """Detect propaganda techniques."""
    text_l = text.lower(); hits = []
    for name, keywords, threshold in PROPAGANDA_SIGNALS:
        count = sum(1 for kw in keywords if kw in text_l)
        if count >= threshold:
            hits.append({"technique": name, "count": count})
    return hits

def get_source_lean(source):
    """Get bias lean for a source."""
    for key, lean in SOURCE_LEAN.items():
        if key.lower() in source.lower():
            return lean
    return "center"

def extract_topic_cluster(articles, min_cluster=3):
    """Group articles by topic using keyword overlap."""
    # Extract keywords from titles
    STOP = {"the","a","an","and","or","but","in","on","at","to","for","of","with","is","are",
            "was","were","has","have","had","by","from","as","be","this","that","it","not"}
    def kw(title):
        words = re.findall(r'\b[A-Za-z]{4,}\b', title)
        return {w.lower() for w in words if w.lower() not in STOP}

    clusters = []; used = set()
    arts = [a for a in articles if a.get("pub","") > ((_now()-timedelta(hours=72)).isoformat())]
    arts.sort(key=lambda x: x.get("pub",""), reverse=True)

    for i, a in enumerate(arts):
        if i in used: continue
        kws_a = kw(a.get("title",""))
        cluster = [a]; used.add(i)
        for j, b in enumerate(arts):
            if j in used or j == i: continue
            kws_b = kw(b.get("title",""))
            if len(kws_a & kws_b) >= 2:
                cluster.append(b); used.add(j)
        if len(cluster) >= min_cluster:
            clusters.append(cluster)

    return clusters[:12]

def analyze_narratives(articles):
    """Full narrative analysis."""
    db = _load()
    clusters = extract_topic_cluster(articles, min_cluster=2)
    topics = []

    for cluster in clusters[:10]:
        # Get anchor title (most recent)
        anchor   = cluster[0]
        all_text = " ".join(a.get("title","")+" "+a.get("summary","") for a in cluster)
        sources  = [a.get("source","") for a in cluster]
        source_c = Counter(sources)

        # Bias spectrum
        leans    = [get_source_lean(s) for s in sources]
        lean_c   = Counter(leans)

        # Framing
        framing  = detect_framing(all_text)
        prop     = detect_propaganda(all_text)

        # Coverage timeline
        timeline = []
        for a in sorted(cluster, key=lambda x: x.get("pub","")):
            try:
                dt = datetime.fromisoformat(a.get("pub",""))
                if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                hrs = int((_now()-dt).total_seconds()/3600)
                timeline.append({"hrs_ago": hrs, "source": a.get("source",""), "title": a.get("title",""), "id": a.get("id","")})
            except: pass

        # Spin score (0-100, higher = more opinionated/biased)
        spin_score = min(100, (framing["scores"].get("alarmist",0)*8) + (framing["scores"].get("emotional",0)*5) + (len(prop)*15) + (lean_c.get("state-media",0)*20))

        topic = {
            "id":           hashlib.md5(anchor.get("title","").encode()).hexdigest()[:8],
            "title":        anchor.get("title","")[:80],
            "article_count":len(cluster),
            "sources":      [{"name": k, "count": v, "lean": get_source_lean(k), "color": LEAN_COLOR.get(get_source_lean(k),"#888")} for k,v in source_c.most_common(8)],
            "lean_spectrum": {"left": lean_c.get("left",0)+lean_c.get("center-left",0), "center": lean_c.get("center",0), "right": lean_c.get("right",0)+lean_c.get("center-right",0), "state": lean_c.get("state-media",0)},
            "framing":      framing,
            "propaganda":   prop,
            "spin_score":   spin_score,
            "spin_level":   "High" if spin_score>60 else "Medium" if spin_score>30 else "Low",
            "spin_color":   "#f26c5c" if spin_score>60 else "#ffd060" if spin_score>30 else "#4cc870",
            "timeline":     timeline[:12],
            "ts":           _now().isoformat(),
        }
        topics.append(topic)

    # Source reliability stats
    source_stats = {}
    for a in articles[:300]:
        src  = a.get("source","Unknown")
        lean = get_source_lean(src)
        if src not in source_stats:
            source_stats[src] = {"count":0, "lean":lean, "color":LEAN_COLOR.get(lean,"#888"), "cats":Counter()}
        source_stats[src]["count"] += 1
        source_stats[src]["cats"][a.get("cat","?")] += 1

    top_sources = sorted(source_stats.items(), key=lambda x:-x[1]["count"])[:25]
    source_list = [{"name":k,"count":v["count"],"lean":v["lean"],"color":v["color"]} for k,v in top_sources]

    db["topics"]        = topics
    db["source_stats"]  = {k:v for k,v in top_sources}
    db["last_analysis"] = _now().isoformat()
    _save(db)
    return {"topics": topics, "sources": source_list, "last_analysis": db["last_analysis"]}

def get_narratives():
    db = _load()
    return {"topics": db.get("topics",[]), "sources": list(db.get("source_stats",{}).items())[:20], "last_analysis": db.get("last_analysis","")}

def build_narrative_prompt(topics, articles):
    """Build AI prompt for narrative analysis."""
    topic_sum = "\n".join(f"• Topic: '{t['title'][:60]}' — {t['article_count']} articles, spin={t['spin_score']}/100 ({t['spin_level']}), framing={t['framing']['dominant']}, propaganda signals={len(t['propaganda'])}" for t in topics[:8])
    src_sum   = Counter(a.get("source","") for a in articles[:200]).most_common(10)
    src_str   = ", ".join(f"{s[0]}({s[1]})" for s in src_sum)
    return f"""You are a media intelligence analyst specializing in narrative analysis, propaganda detection, and information warfare.

TOP STORY CLUSTERS (72h):
{topic_sum if topic_sum else 'Insufficient data for clustering yet'}

TOP SOURCES BY VOLUME: {src_str}

Analyze the current media landscape:

## 📡 DOMINANT NARRATIVES (what stories are being amplified and why)
## 🔄 NARRATIVE SHIFTS (how stories evolved in the last 72h vs previous week)
## 🚨 SPIN & BIAS ALERTS (highest spin-score stories — who is framing what how)
## 🕵️ INFORMATION GAPS (major stories being undercovered or suppressed)
## 📢 STATE MEDIA vs INDEPENDENT COVERAGE (divergences between state-aligned and independent reporting)
## ⚠️ COORDINATION SIGNALS (stories that may reflect coordinated messaging campaigns)
## 🎯 KEY NARRATIVES TO WATCH (emerging narratives that may become dominant)"""
