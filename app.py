"""
app.py  –  SIGNAL v7 — Global Intelligence Platform
Entry point. All routes split across routes_ai.py + routes_data.py
Run: python app.py  →  http://localhost:8080
"""
from flask import Flask, Response, stream_with_context
import threading, time, json, queue, os
from datetime import datetime, timezone

from financial_data  import start_updater as fin_start, fetch_all as fin_fetch
from conflict_engine import start_scanner, run_scan
from science_monitor import start_monitor as sci_start, run_scrape as sci_scrape
from scraper_engine  import run_scrape, _ago
from intelligence_engine import (
    watchlist_scan_articles, alerts_check, briefs_get, briefs_save_new,
)
from routes_ai   import register_ai_routes, master_brief_text
from routes_data import register_data_routes

app = Flask(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────
scrape_st  = {"running": False, "last_new": 0, "last_run": ""}
_sse_queues: list[queue.Queue] = []

def bcast(typ, data={}):
    dead = []
    for q in _sse_queues:
        try:    q.put_nowait({"t": typ, "d": data})
        except: dead.append(q)
    for q in dead:
        try: _sse_queues.remove(q)
        except: pass

# ── SSE endpoint ──────────────────────────────────────────────────────────────
@app.route("/api/stream")
def sse():
    q = queue.Queue(maxsize=100)
    _sse_queues.append(q)
    def gen():
        yield 'data: {"t":"ok"}\n\n'
        while True:
            try:
                m = q.get(timeout=28)
                yield f"data: {json.dumps(m)}\n\n"
            except queue.Empty:
                yield ": hb\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── Background workers (all auto — no manual refresh needed) ─────────────────
def _bg_news(interval=90):
    """Auto-scrape news every 90s."""
    time.sleep(6)
    while True:
        scrape_st["running"] = True
        bcast("scrape_start")
        try:
            ni, _ = run_scrape()
            scrape_st.update({"last_new": len(ni), "last_run": datetime.now(timezone.utc).isoformat()})
            if ni:
                for a in ni: a["ago"] = _ago(a.get("pub",""))
                hits = watchlist_scan_articles(ni)
                alts = alerts_check(ni)
                if hits: bcast("watchlist_hits", {"hits": hits[:10]})
                if alts: bcast("alert_triggers", {"alerts": alts[:10]})
                bcast("new_arts", {"count": len(ni), "arts": ni[:5]})
            bcast("scrape_done", {"count": len(ni)})
        except Exception as e:
            bcast("err", {"e": str(e)})
        finally:
            scrape_st["running"] = False
        time.sleep(interval)

def _bg_fin_tick(interval=60):
    """Broadcast financial updates every 60s."""
    time.sleep(20)
    while True:
        try:
            from financial_data import get_cache
            bcast("fin_tick", {"ts": get_cache().get("ts","")})
        except: pass
        time.sleep(interval)

def _bg_conf(interval=480):
    """Auto-scan conflict feeds every 8 min."""
    time.sleep(35)
    while True:
        try:
            run_scan(); bcast("conf_updated")
        except Exception as e:
            print(f"[BG Conflict] {e}")
        time.sleep(interval)

def _bg_science(interval=300):
    """Auto-scrape science feeds every 5 min."""
    time.sleep(25)
    while True:
        try:
            ni, _ = sci_scrape()
            bcast("sci_updated", {"count": len(ni)})
        except Exception as e:
            print(f"[BG Science] {e}")
        time.sleep(interval)

def _bg_autobrief(interval=1800):
    """Auto-generate Gemini master brief on schedule."""
    time.sleep(130)
    while True:
        try:
            from routes_ai import get_key
            if get_key("gemini"):
                db_b = briefs_get(); b = db_b.get("briefs",[])
                ih   = db_b.get("schedule_hours", 6)
                run  = True
                if b:
                    try:
                        dt  = datetime.fromisoformat(b[0].get("ts",""))
                        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
                        run = (datetime.now(timezone.utc)-dt).total_seconds()/3600 >= ih
                    except: pass
                if run:
                    text = master_brief_text()
                    if text:
                        briefs_save_new(text, "auto", "gemini-2.5-pro")
                        bcast("auto_brief")
        except Exception as e:
            print(f"[AutoBrief] {e}")
        time.sleep(interval)

# ── Start everything ──────────────────────────────────────────────────────────
print("[SIGNAL v7] Starting subsystems…")
fin_start(90)         # Financial data refresh every 90s
start_scanner(480)    # Conflict feed scan every 8 min
sci_start(300)        # Science/Tech/Space feed every 5 min

for fn, args in [
    (_bg_news,     (90,)),
    (_bg_fin_tick, (60,)),
    (_bg_conf,     (480,)),
    (_bg_science,  (300,)),
    (_bg_autobrief,(1800,)),
]:
    threading.Thread(target=fn, args=args, daemon=True).start()

# ── Register all routes ───────────────────────────────────────────────────────
register_data_routes(app, bcast, scrape_st)
register_ai_routes(app, bcast)

@app.route("/")
def index():
    p = os.path.join(os.path.dirname(__file__), "dashboard.html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else "<h1>dashboard.html missing</h1>"

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  SIGNAL v7  —  Global Intelligence Platform")
    print("  ✦ Zero manual refresh — everything auto-updates")
    print("  ✦ Gemini 2.5 Pro + Perplexity Sonar Pro (Dual AI)")
    print("  ✦ Nexus Link Tree (news→conflict→market→outcome)")
    print("  ✦ AI Stock Advisor (geo + financial + tech signals)")
    print("  ✦ Space · Medical · Tech breakthrough monitor")
    print("  ✦ Live alerts · Watchlist · Portfolio tracker")
    print("="*60)
    print("  🌐  http://localhost:8080")
    print()
    print("  Optional env vars:")
    print("  export GEMINI_API_KEY=AIza...")
    print("  export PERPLEXITY_API_KEY=pplx-...")
    print()
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)