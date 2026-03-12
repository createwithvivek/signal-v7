"""
report_generator.py  —  Intelligence Report Generator
Auto-builds daily/weekly HTML reports exportable as standalone files
"""
import json, os
from datetime import datetime, timezone, timedelta

REPORT_F = "reports.json"

def _now():  return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()
def _esc(s): return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _load():
    if os.path.exists(REPORT_F):
        try:
            with open(REPORT_F) as f: return json.load(f)
        except: pass
    return {"reports": []}

def _save(db):
    with open(REPORT_F, "w") as f: json.dump(db, f, indent=2, ensure_ascii=False)

def build_report_prompt(report_type, articles, conflicts, fin_data, science_arts=None, forecasts=None):
    """Build comprehensive prompt for report generation."""
    fd   = fin_data.get("data", {})
    fng  = fd.get("fng", {}).get("current", {})
    idxs = fd.get("indices", [])
    snap = ", ".join(f"{i['n']} {i.get('pct',0):+.2f}%" for i in idxs[:6] if i.get("price"))
    top_arts = sorted(articles, key=lambda x: x.get("pub",""), reverse=True)[:50]
    headlines = "\n".join(f"[{a['cat'].upper()}] {a['title']} | {a['source']}" for a in top_arts)
    conf_sum = "\n".join(f"• {c['name']} ({c['severity']}, {c['trend']}, {c.get('article_count',0)} articles)" for c in conflicts[:10])
    sci_hl = ""
    if science_arts:
        sci_hl = "\n".join(f"[{a['domain'].upper()}] {a['title']}" for a in science_arts[:10])
    fc_sum = ""
    if forecasts:
        fc_sum = "\n".join(f"• {f['icon']} {f['title']}: {f['score']}/100 ({f['level']})" for f in forecasts)
    date_str = _now().strftime("%B %d, %Y")
    if report_type == "daily":
        return f"""You are the Editor-in-Chief of a top-tier intelligence publication. Write a comprehensive DAILY INTELLIGENCE REPORT for {date_str}.

MARKET SNAPSHOT: {snap}
FEAR & GREED: {fng.get('v','?')} — {fng.get('cls','?')}

ACTIVE CONFLICTS:
{conf_sum}

TODAY'S KEY HEADLINES:
{headlines}

{'SCIENCE & TECH:' + chr(10) + sci_hl if sci_hl else ''}
{'FORECASTS:' + chr(10) + fc_sum if fc_sum else ''}

Write a professional DAILY INTELLIGENCE BRIEF with these exact sections:

# SIGNAL DAILY INTELLIGENCE REPORT — {date_str}

## EXECUTIVE SUMMARY (5 bullets, most critical developments)

## 🔴 BREAKING & CRITICAL
(Most urgent developments requiring immediate attention)

## 🌍 GEOPOLITICAL SITUATION
(Conflict updates, diplomatic developments, power shifts)

## 💹 MARKETS & ECONOMY
(Key market movements, economic signals, what they mean)

## 🏛 POLITICAL INTELLIGENCE
(US politics, elections, policy changes, legislation)

## 🔬 SCIENCE & TECHNOLOGY
(Breakthroughs, new capabilities, strategic tech developments)

## 📊 DATA POINTS OF THE DAY
(5-7 key statistics and what they signal)

## ⚠️ RISKS ON THE HORIZON
(Threats developing over next 7-30 days)

## 🎯 TOMORROW'S WATCHLIST
(5 specific things to monitor in the next 24 hours)

Write in professional intelligence style. Be specific, factual, and concise. Avoid filler language."""

    elif report_type == "weekly":
        return f"""Write a comprehensive WEEKLY INTELLIGENCE REVIEW covering the past 7 days.

MARKET SNAPSHOT: {snap}
ACTIVE CONFLICTS: {len(conflicts)} total
RECENT HEADLINES (sample):
{headlines[:2000]}

# SIGNAL WEEKLY INTELLIGENCE REVIEW — Week of {date_str}

## THIS WEEK IN SUMMARY (the 5 biggest developments)

## 🔥 STORY OF THE WEEK (deep dive on the most significant development)

## 🌍 GEOPOLITICS SCORECARD
(Rate each major theater: improving/stable/deteriorating)

## 💰 MARKETS WEEK IN REVIEW
(Market performance, key macro developments, Fed/central bank action)

## 🔬 SCIENCE & TECH ADVANCES (significant breakthroughs this week)

## 📈 SIGNALS & INDICATORS (what the data is saying across categories)

## 🔮 WEEK AHEAD PREVIEW (key events, risks, dates for next 7 days)

## 💡 STRATEGIC INSIGHT (one big-picture observation about emerging trends)"""

    elif report_type == "threat":
        return f"""Write a THREAT ASSESSMENT REPORT — a focused analysis of current global risks.

CONFLICT DATA:
{conf_sum}

RECENT INTELLIGENCE:
{headlines[:2000]}

{'FORECASTS:' + chr(10) + fc_sum if fc_sum else ''}

# SIGNAL GLOBAL THREAT ASSESSMENT — {date_str}

## THREAT LEVEL SUMMARY (overall assessment with color-coded ratings by domain)

## 🔴 CRITICAL THREATS (require immediate attention — 0-7 days)

## 🟠 HIGH THREATS (significant concern — 7-30 days)

## 🟡 EMERGING THREATS (developing situations — 30-90 days)

## ⚛️ CATASTROPHIC RISK SCENARIOS (tail risks with massive impact)

## 🛡 MITIGATION FACTORS (what is preventing escalation)

## 🗺 REGIONAL THREAT MAP (rating by region: Europe, Middle East, Indo-Pacific, Africa, Americas)

## 📡 INTELLIGENCE GAPS (what we don't know but need to)"""

    elif report_type == "market_intel":
        return f"""Write a MARKET INTELLIGENCE REPORT combining geopolitical risk with market analysis.

MARKET DATA: {snap}
FEAR & GREED: {fng.get('v','?')} — {fng.get('cls','?')}
CONFLICT RISKS: {conf_sum}
FINANCIAL NEWS: {headlines[:1500]}

# SIGNAL MARKET INTELLIGENCE REPORT — {date_str}

## MARKET RISK ENVIRONMENT (current regime: risk-on/risk-off/transitional)

## 💹 KEY MARKET SIGNALS (indices, bonds, commodities, crypto — what they're saying)

## 🌍 GEOPOLITICAL RISK PREMIUM (how conflicts are pricing into markets)

## 🏦 CENTRAL BANK INTELLIGENCE (Fed, ECB, BoJ, PBoC — current posture and next moves)

## 🛢 COMMODITY INTELLIGENCE (oil, gold, wheat, copper — supply/demand dynamics)

## 💱 CURRENCY INTELLIGENCE (DXY, EUR, JPY, EM — key moves and drivers)

## 📊 SECTOR ROTATION SIGNALS (which sectors are seeing smart money flows)

## 🎯 TRADE IDEAS (not financial advice — illustrative positioning based on current signals)

## 📅 KEY DATES FOR MARKETS (economic calendar, earnings, central bank meetings)"""

def generate_html_report(title, content, report_type="daily"):
    """Wrap AI-generated report content in styled HTML."""
    now_str = _now().strftime("%B %d, %Y — %H:%M UTC")
    type_colors = {"daily":"#f26c5c","weekly":"#58a8ff","threat":"#ff6b35","market_intel":"#4cc870"}
    accent = type_colors.get(report_type,"#f26c5c")

    # Convert markdown to HTML
    lines = content.split("\n"); html_lines = []
    for line in lines:
        if line.startswith("# "):
            html_lines.append(f'<h1 style="font:700 26px/1.3 Georgia,serif;color:#1e1a14;margin:20px 0 10px;padding-bottom:8px;border-bottom:3px solid {accent}">{_esc(line[2:])}</h1>')
        elif line.startswith("## "):
            html_lines.append(f'<h2 style="font:600 17px/1.3 Georgia,serif;color:#2d2820;margin:18px 0 8px;padding-left:10px;border-left:4px solid {accent}">{_esc(line[3:])}</h2>')
        elif line.startswith("- ") or line.startswith("• "):
            html_lines.append(f'<li style="margin:4px 0;line-height:1.7;color:#3a342a">{_esc(line[2:])}</li>')
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f'<p style="font-weight:700;color:#1e1a14;margin:6px 0">{_esc(line[2:-2])}</p>')
        elif line.strip():
            html_lines.append(f'<p style="margin:6px 0;line-height:1.75;color:#3a342a">{_esc(line)}</p>')
        else:
            html_lines.append('<br/>')

    body = "\n".join(html_lines)
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/>
<title>{_esc(title)}</title>
<style>
body{{font-family:'Georgia',serif;background:#f9f6f0;color:#1e1a14;max-width:820px;margin:0 auto;padding:30px 24px}}
.header{{background:{accent};color:#fff;padding:20px 24px;border-radius:8px;margin-bottom:24px}}
.header h1{{font:700 22px/1 Georgia,serif;margin:0 0 5px}}
.header .meta{{font:400 11px/1 monospace;opacity:.75}}
.footer{{margin-top:30px;padding:12px;background:#ece8e0;border-radius:6px;font:400 10px/1.6 monospace;color:#8a7f6e;text-align:center}}
li{{margin-left:20px}}
</style></head>
<body>
<div class="header">
  <div style="font:700 10px/1 monospace;letter-spacing:2px;opacity:.7;margin-bottom:6px">SIGNAL INTELLIGENCE PLATFORM — CONFIDENTIAL</div>
  <h1>{_esc(title)}</h1>
  <div class="meta">Generated: {now_str} | Auto-Intelligence via Gemini AI + Live Data</div>
</div>
{body}
<div class="footer">
  Generated by SIGNAL v7 Intelligence Platform · AI-assisted analysis · For informational purposes only<br/>
  Not financial, legal, or security advice · Always verify critical information from primary sources
</div>
</body></html>"""

def save_report(title, html_content, report_type):
    db = _load()
    rid = f"rpt_{int(_now().timestamp())}"
    db["reports"].insert(0, {
        "id":    rid,
        "title": title,
        "type":  report_type,
        "ts":    _iso(),
        "html":  html_content,
        "size":  len(html_content),
    })
    db["reports"] = db["reports"][:20]  # keep last 20
    _save(db)
    return rid

def get_reports():
    db = _load()
    return [{"id":r["id"],"title":r["title"],"type":r["type"],"ts":r["ts"],"size":r["size"]} for r in db.get("reports",[])]

def get_report_html(rid):
    db = _load()
    for r in db.get("reports",[]):
        if r["id"] == rid: return r.get("html","")
    return None
