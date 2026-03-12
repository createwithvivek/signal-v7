"""routes_data.py – Non-AI data endpoints: news, financial, conflicts, science, nexus, stocks"""
from flask import request, jsonify
import threading, time
from datetime import datetime, timezone

from scraper_engine      import run_scrape, get_full_text, get_stats, load_db, save_db, scrape_url, _ago
from financial_data      import get_cache, fetch_all as fin_fetch
from conflict_engine     import get_all as conf_all, get_detail as conf_detail, run_scan
from intelligence_engine import (
    watchlist_get, watchlist_add, watchlist_remove, watchlist_scan_articles,
    compute_sentiment, get_correlations, compute_threat_board,
    portfolio_get, portfolio_add, portfolio_remove, portfolio_enrich, portfolio_get_news,
    briefs_get, briefs_save_new, briefs_list, compute_trend_analysis,
    compute_risk_scores, alerts_get, alerts_add, alerts_remove, alerts_check,
    find_similar_articles, _jsave, BRIEFS_F,
)
from science_monitor import get_articles as sci_get, get_stats as sci_stats, run_scrape as sci_scrape
from nexus_engine    import build_nexus, get_nexus_summary
from stock_advisor   import get_stock_suggestions

_nexus_cache = {"data": None, "ts": 0}

def register_data_routes(app, bcast_fn, scrape_st):

    # ── NEWS ─────────────────────────────────────────────────────────────────
    @app.route("/api/articles")
    def api_arts():
        db   = load_db(); arts = list(db["arts"].values())
        cat  = request.args.get("cat",""); tag = request.args.get("tag","")
        q    = request.args.get("q","").lower(); srt = request.args.get("srt","newest")
        pg   = int(request.args.get("pg",1)); pp = int(request.args.get("pp",25))
        if cat: arts = [a for a in arts if a["cat"] == cat]
        if tag: arts = [a for a in arts if tag in a.get("tags",[])]
        if q:   arts = [a for a in arts if q in a["title"].lower() or q in a.get("summary","").lower()]
        def sk(a):
            try: return datetime.fromisoformat(a.get("pub","1970-01-01T00:00:00+00:00"))
            except: return datetime.min.replace(tzinfo=timezone.utc)
        arts.sort(key=sk, reverse=(srt=="newest"))
        for a in arts: a["ago"] = _ago(a.get("pub",""))
        tot = len(arts); s = (pg-1)*pp
        return jsonify({"arts": arts[s:s+pp], "total": tot, "pg": pg, "pages": (tot+pp-1)//pp})

    @app.route("/api/article/<aid>")
    def api_art(aid):
        db = load_db(); a = db["arts"].get(aid)
        if not a: return jsonify({"error":"Not found"}), 404
        if not a.get("full_text"): a["full_text"] = get_full_text(aid)
        a["ago"] = _ago(a.get("pub","")); return jsonify(a)

    @app.route("/api/stats")
    def api_stats():
        s = get_stats(); s["scrape"] = scrape_st; return jsonify(s)

    @app.route("/api/scrape", methods=["POST"])
    def api_scrape():
        if scrape_st["running"]: return jsonify({"status":"running"})
        def go():
            scrape_st["running"] = True; bcast_fn("scrape_start")
            try:
                ni,_ = run_scrape()
                scrape_st.update({"last_new":len(ni),"last_run":datetime.now(timezone.utc).isoformat()})
                if ni:
                    for a in ni: a["ago"] = _ago(a.get("pub",""))
                    hits = watchlist_scan_articles(ni); alts = alerts_check(ni)
                    if hits: bcast_fn("watchlist_hits",{"hits":hits})
                    if alts: bcast_fn("alert_triggers",{"alerts":alts})
                    bcast_fn("new_arts",{"count":len(ni),"arts":ni[:5]})
                bcast_fn("scrape_done",{"count":len(ni)})
            finally: scrape_st["running"] = False
        threading.Thread(target=go,daemon=True).start(); return jsonify({"status":"started"})

    @app.route("/api/scrape-url", methods=["POST"])
    def api_scrape_url():
        d = request.get_json(); url = (d or {}).get("url","").strip()
        if not url: return jsonify({"error":"No URL"}), 400
        if not url.startswith("http"): url = "https://"+url
        res = scrape_url(url)
        if "error" not in res:
            db = load_db(); db["arts"][res["id"]] = res
            if res["id"] not in db["hashes"]: db["hashes"].append(res["id"])
            save_db(db); bcast_fn("new_arts",{"count":1,"arts":[res]})
        return jsonify(res)

    @app.route("/api/tags")
    def api_tags():
        from collections import Counter
        db = load_db(); c = Counter()
        for a in db["arts"].values():
            for t in a.get("tags",[]): c[t] += 1
        return jsonify([{"tag":k,"count":v} for k,v in c.most_common(35)])

    # ── FINANCIAL ────────────────────────────────────────────────────────────
    @app.route("/api/financial")
    def api_fin(): return jsonify(get_cache())

    @app.route("/api/financial/refresh", methods=["POST"])
    def api_fin_refresh():
        def go(): c = fin_fetch(); bcast_fn("fin_updated",{"ts":c.get("ts","")})
        threading.Thread(target=go,daemon=True).start(); return jsonify({"status":"refreshing"})

    # ── CONFLICTS ────────────────────────────────────────────────────────────
    @app.route("/api/conflicts")
    def api_conflicts():
        data,ls = conf_all(); return jsonify({"conflicts":data,"last_scan":ls})

    @app.route("/api/conflict/<cid>")
    def api_conflict(cid):
        d = conf_detail(cid)
        if not d: return jsonify({"error":"Not found"}), 404
        return jsonify(d)

    @app.route("/api/conflicts/scan", methods=["POST"])
    def api_conf_scan():
        def go(): run_scan(); bcast_fn("conf_updated")
        threading.Thread(target=go,daemon=True).start(); return jsonify({"status":"scanning"})

    # ── SCIENCE ──────────────────────────────────────────────────────────────
    @app.route("/api/science")
    def api_science():
        return jsonify(sci_get(
            domain=request.args.get("domain",""),
            tag=request.args.get("tag",""),
            breakthru_only=request.args.get("bt","")=="1",
            q=request.args.get("q",""),
            pg=int(request.args.get("pg",1)), pp=25))

    @app.route("/api/science/stats")
    def api_science_stats(): return jsonify(sci_stats())

    @app.route("/api/science/refresh", methods=["POST"])
    def api_science_refresh():
        def go(): ni,_ = sci_scrape(); bcast_fn("sci_updated",{"count":len(ni)})
        threading.Thread(target=go,daemon=True).start(); return jsonify({"status":"refreshing"})

    # ── NEXUS LINK TREE ──────────────────────────────────────────────────────
    @app.route("/api/nexus")
    def api_nexus():
        global _nexus_cache
        if _nexus_cache["data"] and (time.time()-_nexus_cache["ts"]) < 120:
            return jsonify(_nexus_cache["data"])
        db = load_db(); arts = list(db["arts"].values())
        confs,_ = conf_all(); fin = get_cache()
        data = build_nexus(arts, confs, fin)
        _nexus_cache = {"data":data,"ts":time.time()}
        return jsonify(data)

    @app.route("/api/nexus/summary")
    def api_nexus_summary():
        db = load_db(); arts = list(db["arts"].values())
        confs,_ = conf_all(); fin = get_cache()
        return jsonify(get_nexus_summary(build_nexus(arts, confs, fin)))

    # ── STOCK SUGGESTIONS ────────────────────────────────────────────────────
    @app.route("/api/stocks")
    def api_stocks():
        db = load_db(); arts = list(db["arts"].values())
        confs,_ = conf_all(); fin = get_cache()
        return jsonify(get_stock_suggestions(arts, confs, fin))

    # ── INTELLIGENCE ─────────────────────────────────────────────────────────
    @app.route("/api/sentiment")
    def api_sentiment():
        db = load_db(); arts = list(db["arts"].values())
        return jsonify(compute_sentiment(arts))

    @app.route("/api/correlations")
    def api_corr():
        return jsonify(get_correlations(get_cache(), conf_all()[0]))

    @app.route("/api/threat-board")
    def api_threat():
        db = load_db(); arts = list(db["arts"].values()); confs,_ = conf_all()
        return jsonify(compute_threat_board(arts, confs))

    @app.route("/api/risk-scores")
    def api_risk():
        db = load_db(); arts = list(db["arts"].values()); confs,_ = conf_all()
        return jsonify({"scores":compute_risk_scores(confs,arts),"ts":datetime.now(timezone.utc).isoformat()})

    @app.route("/api/trends")
    def api_trends():
        db = load_db(); arts = list(db["arts"].values()); confs,_ = conf_all()
        return jsonify(compute_trend_analysis(arts, confs))

    @app.route("/api/compare/<aid>")
    def api_compare(aid):
        db = load_db(); arts = list(db["arts"].values())
        return jsonify({"target":db["arts"].get(aid,{}),"similar":find_similar_articles(aid,arts)})

    # ── WATCHLIST ────────────────────────────────────────────────────────────
    @app.route("/api/watchlist")
    def api_wl(): return jsonify(watchlist_get())

    @app.route("/api/watchlist", methods=["POST"])
    def api_wl_add():
        d = request.get_json()
        return jsonify({"id":watchlist_add(d.get("keyword",""),d.get("label",""),d.get("category","all"),d.get("notify",True))})

    @app.route("/api/watchlist/<wid>", methods=["DELETE"])
    def api_wl_del(wid): watchlist_remove(wid); return jsonify({"ok":True})

    # ── ALERTS ───────────────────────────────────────────────────────────────
    @app.route("/api/alerts")
    def api_alerts(): return jsonify(alerts_get())

    @app.route("/api/alerts", methods=["POST"])
    def api_alerts_add():
        d = request.get_json()
        return jsonify({"id":alerts_add(d.get("keyword",""),d.get("label",""),d.get("severity","any"),d.get("sound",True))})

    @app.route("/api/alerts/<aid>", methods=["DELETE"])
    def api_alerts_del(aid): alerts_remove(aid); return jsonify({"ok":True})

    @app.route("/api/alerts/history")
    def api_alerts_hist(): return jsonify(alerts_get().get("history",[])[:50])

    # ── PORTFOLIO ────────────────────────────────────────────────────────────
    @app.route("/api/portfolio")
    def api_pf(): return jsonify(portfolio_enrich(get_cache()))

    @app.route("/api/portfolio", methods=["POST"])
    def api_pf_add():
        d = request.get_json()
        return jsonify({"id":portfolio_add(d.get("symbol",""),d.get("name",""),d.get("qty",0),d.get("buy_price",0),d.get("asset_type","stock"))})

    @app.route("/api/portfolio/<symbol>", methods=["DELETE"])
    def api_pf_del(symbol): portfolio_remove(symbol); return jsonify({"ok":True})

    @app.route("/api/portfolio/news")
    def api_pf_news():
        return jsonify(portfolio_get_news(list(load_db()["arts"].values())))

    # ── BRIEFINGS ────────────────────────────────────────────────────────────
    @app.route("/api/briefs")
    def api_briefs(): return jsonify({"briefs":briefs_list()})

    @app.route("/api/briefs/run", methods=["POST"])
    def api_brief_run():
        from routes_ai import master_brief_text
        d = request.get_json()
        def go():
            text = master_brief_text()
            if text: bid = briefs_save_new(text,"manual","gemini-2.5-pro"); bcast_fn("brief_ready",{"id":bid})
        threading.Thread(target=go,daemon=True).start(); return jsonify({"status":"generating"})

    @app.route("/api/briefs/schedule", methods=["POST"])
    def api_brief_sched():
        d = request.get_json(); db = briefs_get()
        db["schedule_hours"] = int(d.get("hours",6))
        _jsave(BRIEFS_F, db); return jsonify({"ok":True,"hours":db["schedule_hours"]})

    # ── PREDICTION ENGINE ─────────────────────────────────────────────────────
    @app.route("/api/forecasts")
    def api_forecasts():
        from prediction_engine import generate_forecasts, get_forecasts
        confs,_ = conf_all()
        arts    = list(load_db()["arts"].values())
        data    = generate_forecasts(confs, get_cache(), arts)
        return jsonify({"forecasts": data, "ts": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})

    # ── NARRATIVE TRACKER ─────────────────────────────────────────────────────
    @app.route("/api/narratives")
    def api_narratives():
        from narrative_tracker import analyze_narratives
        arts = list(load_db()["arts"].values())
        return jsonify(analyze_narratives(arts))

    @app.route("/api/narratives/cached")
    def api_narratives_cached():
        from narrative_tracker import get_narratives
        return jsonify(get_narratives())

    # ── GEO-ECONOMICS ─────────────────────────────────────────────────────────
    @app.route("/api/geoeconomics")
    def api_geoeco():
        from geo_economics import analyze_geoeconomics
        arts    = list(load_db()["arts"].values())
        confs,_ = conf_all()
        return jsonify(analyze_geoeconomics(arts, confs, get_cache()))

    @app.route("/api/geoeconomics/sanctions")
    def api_sanctions():
        from geo_economics import get_sanctions
        return jsonify(get_sanctions())

    @app.route("/api/geoeconomics/chokepoints")
    def api_chokepoints():
        from geo_economics import get_chokepoints
        return jsonify(get_chokepoints())

    @app.route("/api/geoeconomics/supplychain")
    def api_supplychain():
        from geo_economics import get_supply_chain
        return jsonify(get_supply_chain())

    # ── REPORTS ────────────────────────────────────────────────────────────────
    @app.route("/api/reports")
    def api_reports():
        from report_generator import get_reports
        return jsonify(get_reports())

    @app.route("/api/reports/<rid>")
    def api_report_get(rid):
        from report_generator import get_report_html
        html = get_report_html(rid)
        if not html: return jsonify({"error":"Not found"}), 404
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/reports/<rid>/download")
    def api_report_dl(rid):
        from report_generator import get_report_html
        html = get_report_html(rid)
        if not html: return jsonify({"error":"Not found"}), 404
        return html, 200, {"Content-Type":"text/html","Content-Disposition":f"attachment; filename=signal_report_{rid}.html"}