"""routes_ai.py – All Gemini + Perplexity AI route handlers"""
from flask import request, jsonify
import threading, json
from scraper_engine  import get_full_text, load_db, save_db, _ago
from financial_data  import get_cache
from conflict_engine import get_all as conf_all, get_detail as conf_detail
from intelligence_engine import compute_sentiment, _jsave, BRIEFS_F, briefs_get, briefs_save_new
from science_monitor import get_articles as sci_get
from nexus_engine    import build_nexus, get_nexus_summary
from stock_advisor   import build_stock_prompt
import requests as req, os

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
G_PRO  = "gemini-2.5-pro"
G_FAST = "gemini-2.5-flash"
PPX_URL = "https://api.perplexity.ai/chat/completions"

_keys = {"gemini": os.environ.get("GEMINI_API_KEY",""),
         "perplexity": os.environ.get("PERPLEXITY_API_KEY","")}

def get_key(name): return _keys.get(name,"")
def set_key(name, val): _keys[name] = val.strip()

def gemini(prompt, key=None, model=None, max_tok=4096):
    k = key or _keys["gemini"]
    if not k: return {"error":"No Gemini API key set."}
    m = model or G_PRO
    try:
        r = req.post(f"{GEMINI_BASE}/{m}:generateContent?key={k}",
            json={"contents":[{"parts":[{"text":prompt}]}],
                  "generationConfig":{"temperature":0.7,"maxOutputTokens":max_tok}},
            timeout=65)
        data = r.json()
        if "candidates" in data:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text","") for p in parts if p.get("type","text") != "thinking")
            if not text: text = "".join(p.get("text","") for p in parts)
            return {"text": text, "model": m, "provider": "gemini"}
        err = data.get("error",{})
        if err and m == G_PRO:
            return gemini(prompt, key=k, model=G_FAST, max_tok=max_tok)
        return {"error": err.get("message", str(data))}
    except Exception as e: return {"error": str(e)}

def perplexity(prompt, key=None, max_tok=3000):
    k = key or _keys["perplexity"]
    if not k: return {"error":"No Perplexity API key. Get one at perplexity.ai/api"}
    try:
        r = req.post(PPX_URL,
            headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
            json={"model": "sonar-pro",
                  "messages":[
                      {"role":"system","content":"You are a comprehensive intelligence analyst with real-time web access. Always provide current, sourced analysis."},
                      {"role":"user","content": prompt}],
                  "max_tokens": max_tok,
                  "search_recency_filter": "month",
                  "return_citations": True},
            timeout=65)
        data = r.json()
        if "choices" in data:
            return {"text": data["choices"][0]["message"]["content"],
                    "citations": data.get("citations",[]),
                    "model": "sonar-pro", "provider": "perplexity"}
        return {"error": data.get("error",{}).get("message","Perplexity error")}
    except Exception as e: return {"error": str(e)}

def dual_ai(prompt, mode="both"):
    """Run Gemini + Perplexity in parallel."""
    results = {}
    def rg(): results["gemini"]     = gemini(prompt)
    def rp(): results["perplexity"] = perplexity(prompt)
    threads = []
    if mode in ("both","gemini"):     threads.append(threading.Thread(target=rg))
    if mode in ("both","perplexity"): threads.append(threading.Thread(target=rp))
    for t in threads: t.start()
    for t in threads: t.join(timeout=70)
    return results

def master_brief_text():
    db   = load_db()
    arts = sorted(db["arts"].values(), key=lambda x: x.get("pub",""), reverse=True)[:65]
    hl   = "\n".join(f"[{a['cat'].upper()}] {a['title']} | {a['source']}" for a in arts)
    fin  = get_cache(); fd = fin.get("data",{})
    snap = [f"{i['n']}: {i.get('price','?')} ({i.get('pct',0):+.2f}%)"
            for i in fd.get("indices",[])[:8] if i.get("price")]
    fng  = fd.get("fng",{}).get("current",{})
    p = (f"Master intelligence analyst. All-source global briefing.\n"
         f"LIVE MARKETS: {' | '.join(snap)}\n"
         f"FEAR & GREED: {fng.get('v','?')} — {fng.get('cls','?')}\n\n"
         f"TOP 65 HEADLINES:\n{hl}\n\n"
         f"## 🔴 CRITICAL ALERTS\n## WORLD SITUATION OVERVIEW\n"
         f"## FINANCIAL INTELLIGENCE\n## SECURITY & CONFLICT INTELLIGENCE\n"
         f"## US POLITICAL INTELLIGENCE\n## THE BIG PICTURE\n"
         f"## EMERGING TRENDS (next 90 days)\n## FLASH RISKS\n## STRATEGIC RECOMMENDATIONS")
    return gemini(p, max_tok=4096).get("text","")

def register_ai_routes(app, bcast_fn):

    @app.route("/api/key", methods=["POST"])
    def api_key():
        d = request.get_json() or {}
        if d.get("gemini"):     set_key("gemini", d["gemini"])
        if d.get("perplexity"): set_key("perplexity", d["perplexity"])
        return jsonify({"gemini": bool(get_key("gemini")), "perplexity": bool(get_key("perplexity"))})

    @app.route("/api/ai/article", methods=["POST"])
    def ai_article():
        d = request.get_json(); db = load_db()
        a = db["arts"].get(d.get("id",""))
        if not a: return jsonify({"error":"Not found"}), 404
        if not a.get("full_text"): a["full_text"] = get_full_text(a["id"])
        body = a.get("full_text","") or a.get("summary","")
        p = (f"Senior intelligence analyst.\nTitle: {a['title']}\n"
             f"Source: {a['source']} | {a['cat']} | {a.get('pub','')}\n"
             f"{body[:2500]}\n\n"
             f"## EXECUTIVE SUMMARY\n## KEY FACTS\n## IMPLICATIONS\n"
             f"## KEY ACTORS\n## RISK ASSESSMENT (LOW/MEDIUM/HIGH/CRITICAL)\n## WHAT TO WATCH")
        res = gemini(p, key=d.get("key", get_key("gemini")))
        if "text" in res:
            a["gemini"] = res["text"]; db["arts"][a["id"]] = a; save_db(db)
        return jsonify(res)

    @app.route("/api/ai/article-perplexity", methods=["POST"])
    def ai_article_ppx():
        d = request.get_json(); db = load_db()
        a = db["arts"].get(d.get("id",""))
        if not a: return jsonify({"error":"Not found"}), 404
        p = (f'Search for the very latest on this story: "{a["title"]}"\n'
             f"Source: {a['source']} | Date: {a.get('pub','')}\n\n"
             f"Find: 1) Latest updates 2) Background context 3) Key players "
             f"4) Related events 5) Expert analysis 6) What to watch next\n"
             f"Cite all sources.")
        return jsonify(perplexity(p, key=d.get("key", get_key("perplexity"))))

    @app.route("/api/ai/financial", methods=["POST"])
    def ai_financial():
        d = request.get_json()
        fin = get_cache(); fd = fin.get("data",{})
        idx  = [f"{i['n']}: {i.get('price','?')} ({i.get('pct',0):+.2f}%)"
                for i in fd.get("indices",[])[:10] if i.get("price")]
        cmd  = [f"{i['n']}: {i.get('price','?')} ({i.get('pct',0):+.2f}%)"
                for i in fd.get("commodities",[])[:8] if i.get("price")]
        fng  = fd.get("fng",{}).get("current",{})
        ylds = fd.get("yields",{})
        db   = load_db()
        fa   = sorted([a for a in db["arts"].values() if a["cat"]=="finance"],
                      key=lambda x: x.get("pub",""), reverse=True)[:35]
        hl   = "\n".join(f"• {a['title']} [{a['source']}]" for a in fa)
        p = (f"Chief market strategist.\n\nINDICES:\n" + "\n".join(idx) +
             f"\nCOMMODITIES:\n" + "\n".join(cmd) +
             f"\nFear & Greed: {fng.get('v','?')} — {fng.get('cls','?')}"
             f"\nUS Yields: {', '.join(f'{k}: {v.get(chr(114)+chr(97)+chr(116)+chr(101))}%' for k,v in ylds.items())}"
             f"\n\nFINANCIAL NEWS:\n{hl}\n\n"
             f"## MARKET OVERVIEW\n## US EQUITIES\n## GLOBAL MARKETS\n"
             f"## COMMODITIES\n## CRYPTO\n## FOREX\n## MONETARY POLICY\n"
             f"## TOP 5 RISKS\n## 30-DAY OUTLOOK (Bull/Base/Bear %)\n## VERDICT")
        return jsonify(gemini(p, key=d.get("key", get_key("gemini")), max_tok=4096))

    @app.route("/api/ai/conflict", methods=["POST"])
    def ai_conflict():
        d = request.get_json(); cid = d.get("cid","")
        det = conf_detail(cid)
        if not det: return jsonify({"error":"Not found"}), 404
        arts = det.get("articles",[]); hl = "\n".join(f"• {a['title']} [{a['src']}]" for a in arts[:25])
        p = (f"Military conflict analyst.\n{det['name']} | {det['region']} | "
             f"{det['status']} | {det['severity']}\n"
             f"Parties: {', '.join(det.get('parties',[]))}\n{det.get('desc','')}\n\n"
             f"INTEL:\n{hl}\n\n"
             f"## SITUATION\n## RECENT DEVELOPMENTS\n## MILITARY BALANCE\n"
             f"## INTERNATIONAL INVOLVEMENT\n## HUMANITARIAN\n"
             f"## ESCALATION RISK\n## TRAJECTORY (30-60 days)\n## FLASHPOINTS\n## VERDICT")
        return jsonify(gemini(p, key=d.get("key", get_key("gemini"))))

    @app.route("/api/ai/conflict-perplexity", methods=["POST"])
    def ai_conflict_ppx():
        d = request.get_json(); cid = d.get("cid","")
        det = conf_detail(cid)
        if not det: return jsonify({"error":"Not found"}), 404
        p = (f"Search latest news on: {det['name']}\n"
             f"Region: {det.get('region','')}\n"
             f"Parties: {', '.join(det.get('parties',[]))}\n\n"
             f"Find: 1) Latest 48-72h update 2) Diplomatic developments "
             f"3) International response 4) Casualties/humanitarian 5) Expert analysis "
             f"6) Upcoming key dates. Cite all sources.")
        return jsonify(perplexity(p, key=d.get("key", get_key("perplexity"))))

    @app.route("/api/ai/master", methods=["POST"])
    def ai_master():
        d = request.get_json()
        if d.get("key"): set_key("gemini", d["key"])
        text = master_brief_text()
        if text:
            bid = briefs_save_new(text, "manual", G_PRO)
            bcast_fn("brief_ready", {"id": bid})
            return jsonify({"text": text, "model": G_PRO, "brief_id": bid})
        return jsonify({"error": "Failed to generate"})

    @app.route("/api/ai/geo", methods=["POST"])
    def ai_geo():
        d = request.get_json()
        db   = load_db()
        arts = sorted([a for a in db["arts"].values() if a["cat"] in ["geopolitics","us_politics"]],
                      key=lambda x: x.get("pub",""), reverse=True)[:55]
        hl   = "\n".join(f"[{a['cat'].upper()}] {a['title']} [{a['source']}]" for a in arts)
        p    = (f"Senior geopolitical analyst.\n\n{hl}\n\n"
                f"## CRITICAL ALERTS\n## ACTIVE CONFLICT STATUS\n"
                f"## US POLITICAL LANDSCAPE\n## GREAT POWER COMPETITION\n"
                f"## DIPLOMATIC DEVELOPMENTS\n## INTELLIGENCE SIGNALS\n"
                f"## 3 STRATEGIC SCENARIOS (next 30 days)")
        return jsonify(gemini(p, key=d.get("key", get_key("gemini"))))

    @app.route("/api/ai/search", methods=["POST"])
    def ai_search():
        d = request.get_json(); q = d.get("q","")
        if not q: return jsonify({"error":"No query"}), 400
        mode = d.get("mode","both")
        p = (f'Intelligence analyst. Research query: "{q}"\n\n'
             f"## OVERVIEW\n## KEY FACTS\n## CURRENT STATUS\n"
             f"## HISTORICAL CONTEXT\n## MULTIPLE PERSPECTIVES\n"
             f"## FINANCIAL IMPLICATIONS\n## POLITICAL/SECURITY IMPLICATIONS\n"
             f"## WHAT TO WATCH")
        if mode == "perplexity": return jsonify({"perplexity": perplexity(p)})
        if mode == "gemini":     return jsonify({"gemini": gemini(p, max_tok=3000)})
        return jsonify(dual_ai(p))

    @app.route("/api/ai/science", methods=["POST"])
    def ai_science_brief():
        d      = request.get_json()
        domain = d.get("domain","")
        arts   = sci_get(domain=domain, pg=1, pp=30)["arts"]
        hl     = "\n".join(f"[{a['domain'].upper()}] {'🌟 ' if a.get('breakthru') else ''}{a['title']} [{a['source']}]" for a in arts)
        p = (f"Science & technology intelligence analyst.\n\n"
             f"LATEST DEVELOPMENTS:\n{hl if hl else 'Articles loading...'}\n\n"
             f"## KEY BREAKTHROUGHS\n## SPACE DEVELOPMENTS\n"
             f"## MEDICAL ADVANCES\n## TECH INNOVATIONS\n"
             f"## INVESTMENT IMPLICATIONS\n## GEOPOLITICAL TECH COMPETITION\n"
             f"## TIMELINE PREDICTIONS")
        return jsonify(dual_ai(p))

    @app.route("/api/ai/stocks", methods=["POST"])
    def ai_stocks():
        d      = request.get_json()
        db     = load_db(); arts = list(db["arts"].values())
        confs,_= conf_all(); fin  = get_cache()
        sci    = sci_get(pg=1, pp=20)["arts"]
        prompt = build_stock_prompt(arts, confs, fin, sci)
        return jsonify(dual_ai(prompt))

    @app.route("/api/ai/nexus", methods=["POST"])
    def ai_nexus():
        db     = load_db(); arts = list(db["arts"].values())
        confs,_= conf_all(); fin  = get_cache()
        nexus  = build_nexus(arts, confs, fin)
        summ   = get_nexus_summary(nexus)
        outcomes = [n["label"] for n in summ["outcomes"]]
        markets  = [f"{n['label']}: {n.get('data',{}).get('direction','?')}" for n in summ["markets"]]
        p = (f"Causal chain analyst and strategic forecaster.\n\n"
             f"ACTIVE CONFLICTS: {', '.join(c['label'] for c in summ['conflicts'][:6])}\n"
             f"MARKET IMPACTS: {', '.join(markets[:8])}\n"
             f"PREDICTED OUTCOMES: {', '.join(outcomes[:6])}\n"
             f"NEXUS SIZE: {summ['node_count']} nodes, {summ['edge_count']} connections\n\n"
             f"## CAUSAL CHAINS\n## HIGHEST RISK INTERCONNECTIONS\n"
             f"## UNEXPECTED CONNECTIONS\n## MARKET DOMINO EFFECTS\n"
             f"## BEST/WORST CASE SCENARIOS\n## EARLY WARNING SIGNALS")
        return jsonify(dual_ai(p))

    @app.route("/api/ai/portfolio-brief", methods=["POST"])
    def ai_pf_brief():
        from intelligence_engine import portfolio_enrich, portfolio_get_news
        d    = request.get_json()
        pf   = portfolio_enrich(get_cache())
        news = portfolio_get_news(list(load_db()["arts"].values()))
        if not pf["holdings"]: return jsonify({"error":"No holdings"})
        hs = "\n".join(f"- {h['symbol']}: {h['qty']}@${h['buy_price']} "
                       f"→ ${h.get('current_price','?')} PnL:{h.get('pnl_pct','?')}%"
                       for h in pf["holdings"])
        ns = "\n".join(f"• [{a.get('matched','?')}] {a['title']}" for a in news[:15])
        p  = (f"Portfolio analyst.\nHOLDINGS:\n{hs}\n"
              f"Total P&L: {pf.get('total_pnl_pct','?')}%\n\nNEWS:\n{ns}\n\n"
              f"## PORTFOLIO HEALTH\n## HOLDINGS ANALYSIS\n## KEY RISKS\n"
              f"## OPPORTUNITIES\n## NEWS IMPACT\n## REBALANCING")
        return jsonify(gemini(p, key=d.get("key", get_key("gemini")), max_tok=2500))

    @app.route("/api/ai/sentiment-brief", methods=["POST"])
    def ai_snt_brief():
        d    = request.get_json()
        arts = list(load_db()["arts"].values())
        snt  = compute_sentiment(arts)
        p    = (f"Sentiment analyst.\nOverall: {snt.get('overall',0)}\n"
                f"Bearish topics: {[t['topic'] for t in snt.get('top_bearish',[])]}\n"
                f"Bullish topics: {[t['topic'] for t in snt.get('top_bullish',[])]}\n\n"
                f"## SENTIMENT OVERVIEW\n## DRIVING NEGATIVITY\n"
                f"## DRIVING POSITIVITY\n## MARKET IMPLICATIONS\n"
                f"## RISK SIGNALS\n## OUTLOOK")
        return jsonify(gemini(p, key=d.get("key", get_key("gemini")), max_tok=2000))

    # ── AI FORECASTS ──────────────────────────────────────────────────────────
    @app.route("/api/ai/forecasts", methods=["POST"])
    def ai_forecasts():
        from prediction_engine import generate_forecasts, build_forecast_prompt
        confs,_ = conf_all()
        arts    = list(load_db()["arts"].values())
        fcs     = generate_forecasts(confs, get_cache(), arts)
        prompt  = build_forecast_prompt(fcs, confs, get_cache())
        return jsonify(dual_ai(prompt))

    # ── AI NARRATIVES ─────────────────────────────────────────────────────────
    @app.route("/api/ai/narratives", methods=["POST"])
    def ai_narratives():
        from narrative_tracker import analyze_narratives, build_narrative_prompt
        arts    = list(load_db()["arts"].values())
        data    = analyze_narratives(arts)
        prompt  = build_narrative_prompt(data.get("topics",[]), arts)
        return jsonify(dual_ai(prompt))

    # ── AI GEO-ECONOMICS ──────────────────────────────────────────────────────
    @app.route("/api/ai/geoeconomics", methods=["POST"])
    def ai_geoeco():
        from geo_economics import analyze_geoeconomics, build_geoeconomics_prompt
        arts    = list(load_db()["arts"].values())
        confs,_ = conf_all()
        data    = analyze_geoeconomics(arts, confs, get_cache())
        prompt  = build_geoeconomics_prompt(data, arts)
        return jsonify(dual_ai(prompt))

    # ── AI REPORT GENERATOR ───────────────────────────────────────────────────
    @app.route("/api/ai/report", methods=["POST"])
    def ai_report():
        from report_generator import build_report_prompt, generate_html_report, save_report
        d           = request.get_json()
        report_type = d.get("type", "daily")
        arts        = list(load_db()["arts"].values())
        confs,_     = conf_all()
        sci         = sci_get(pg=1, pp=20)["arts"]
        from prediction_engine import get_forecasts
        fcs = get_forecasts().get("forecasts", [])
        prompt = build_report_prompt(report_type, arts, confs, get_cache(), sci, fcs)
        # Generate with Gemini
        result = gemini(prompt, max_tok=5000)
        if result.get("text"):
            titles = {"daily":"Daily Intelligence Brief","weekly":"Weekly Intelligence Review",
                      "threat":"Global Threat Assessment","market_intel":"Market Intelligence Report"}
            title   = titles.get(report_type, "Intelligence Report")
            html    = generate_html_report(title, result["text"], report_type)
            rid     = save_report(title, html, report_type)
            bcast_fn("report_ready", {"id": rid, "title": title, "type": report_type})
            return jsonify({"text": result["text"], "report_id": rid, "title": title})
        return jsonify({"error": result.get("error","Failed to generate")})