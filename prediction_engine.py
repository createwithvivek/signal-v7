"""
prediction_engine.py  —  AI Forecasting & Prediction Tracker
Generates 7/30/90-day forecasts, tracks accuracy over time, confidence scoring
"""
import json, os, hashlib, time
from datetime import datetime, timezone, timedelta

PRED_F = "predictions.json"

FORECAST_TEMPLATES = {
    "conflict_escalation": {
        "title":   "Conflict Escalation Risk",
        "factors": ["severity","trend","article_count","parties"],
        "horizons":[7, 30, 90],
    },
    "market_move": {
        "title":   "Market Direction Forecast",
        "factors": ["fng","yields","vix","momentum"],
        "horizons":[7, 30],
    },
    "geopolitical_shock": {
        "title":   "Geopolitical Shock Probability",
        "factors": ["conflict_count","escalation_count","nuclear_signals","election_cycle"],
        "horizons":[30, 90],
    },
    "recession_risk": {
        "title":   "Recession Risk Indicator",
        "factors": ["yields_inverted","fng","credit_spreads","employment"],
        "horizons":[90, 180],
    },
}

SCENARIO_COLORS = {
    "Bull":     "#4cc870",
    "Bear":     "#f26c5c",
    "Neutral":  "#8a9bb0",
    "Critical": "#ff6b35",
    "Watch":    "#ffd060",
}

def _now():  return datetime.now(timezone.utc)
def _iso():  return _now().isoformat()
def _h(s):   return hashlib.md5(s.encode()).hexdigest()[:10]

def _load():
    if os.path.exists(PRED_F):
        try:
            with open(PRED_F) as f: return json.load(f)
        except: pass
    return {"forecasts": [], "accuracy_log": [], "last_run": ""}

def _save(db):
    with open(PRED_F, "w") as f: json.dump(db, f, indent=2, ensure_ascii=False)

def score_conflict_risk(conflicts):
    """Score overall conflict escalation risk 0-100."""
    if not conflicts: return 20, "Low"
    esc   = sum(1 for c in conflicts if c.get("trend") == "escalating")
    crit  = sum(1 for c in conflicts if c.get("severity") == "critical")
    high  = sum(1 for c in conflicts if c.get("severity") == "high")
    total = len(conflicts)
    score = min(100, (crit * 25) + (high * 12) + (esc * 8) + min(total * 2, 20))
    level = "Critical" if score > 75 else "High" if score > 55 else "Elevated" if score > 35 else "Low"
    return score, level

def score_market_risk(fin_data):
    """Score market risk 0-100."""
    fd  = fin_data.get("data", {})
    fng = fd.get("fng", {}).get("current", {})
    v   = fng.get("v", 50)
    # Fear = high risk (bear market), Greed = moderate risk (correction risk)
    if v < 20:   score = 80  # Extreme Fear — possible capitulation
    elif v < 35: score = 60  # Fear — negative
    elif v < 55: score = 40  # Neutral
    elif v < 75: score = 50  # Greed — correction risk
    else:        score = 70  # Extreme Greed — bubble risk
    level = "High" if score > 65 else "Elevated" if score > 45 else "Low"
    return score, level, v

def generate_forecasts(conflicts, fin_data, articles):
    """Generate a full set of forecasts from current data."""
    db   = _load()
    conf_score, conf_level = score_conflict_risk(conflicts)
    mkt_score, mkt_level, fng_val = score_market_risk(fin_data)

    # Count violence/nuclear signals in last 24h
    cutoff = _now() - timedelta(hours=24)
    nuke_kw = ["nuclear","nuke","missile","icbm","warhead","chemical weapon","biological"]
    econ_kw = ["recession","crash","default","crisis","collapse","bankruptcy"]
    nuke_ct = 0; econ_ct = 0
    for a in articles:
        text = (a.get("title","") + " " + a.get("summary","")).lower()
        try:
            dt = datetime.fromisoformat(a.get("pub",""))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff: continue
        except: continue
        if any(k in text for k in nuke_kw): nuke_ct += 1
        if any(k in text for k in econ_kw): econ_ct += 1

    # Yield curve inversion check
    fd     = fin_data.get("data", {})
    yields = fd.get("yields", {})
    y2     = float(yields.get("2Y", {}).get("rate", 0) or 0)
    y10    = float(yields.get("10Y", {}).get("rate", 0) or 0)
    inverted = y2 > y10

    now_str = _iso()
    forecasts = []

    # ── Forecast 1: Conflict Escalation ────────────────────────────────────
    esc_count = sum(1 for c in conflicts if c.get("trend") == "escalating")
    crit_count = sum(1 for c in conflicts if c.get("severity") == "critical")
    f1_7  = min(95, conf_score + (nuke_ct * 5))
    f1_30 = min(95, conf_score + (esc_count * 3) + (crit_count * 5))
    f1_90 = min(90, f1_30 - 5 + (10 if esc_count > 3 else -5))
    forecasts.append({
        "id":       "conf_esc",
        "category": "Conflict",
        "title":    "Global Conflict Escalation Risk",
        "icon":     "⚔",
        "score":    conf_score,
        "level":    conf_level,
        "color":    SCENARIO_COLORS.get(conf_level, "#8a9bb0"),
        "signals":  f"{esc_count} escalating, {crit_count} critical, {nuke_ct} nuclear signals (24h)",
        "horizons": [
            {"days":7,  "prob":f1_7,  "direction":"Up" if f1_7>conf_score else "Down", "label":"7-day"},
            {"days":30, "prob":f1_30, "direction":"Up" if f1_30>conf_score else "Down", "label":"30-day"},
            {"days":90, "prob":f1_90, "direction":"Up" if f1_90>conf_score else "Down", "label":"90-day"},
        ],
        "scenarios": [
            {"name":"Escalation", "prob":f1_7,       "desc":f"{esc_count} conflicts continue escalating, regional spillover possible", "color":SCENARIO_COLORS["Bear"]},
            {"name":"Status Quo", "prob":100-f1_7-15,"desc":"Conflicts remain contained, no major new fronts open",                   "color":SCENARIO_COLORS["Neutral"]},
            {"name":"De-escalation","prob":15,        "desc":"Diplomatic progress reduces active conflict count",                       "color":SCENARIO_COLORS["Bull"]},
        ],
        "key_risks": [
            f"Nuclear signals elevated ({nuke_ct} mentions in 24h)" if nuke_ct > 2 else "Nuclear risk low",
            f"{esc_count} conflicts currently escalating — watch for regional spillover",
            f"{crit_count} critical-severity conflicts require close monitoring",
        ],
        "ts": now_str,
    })

    # ── Forecast 2: Market Direction ───────────────────────────────────────
    indices  = fd.get("indices", [])
    sp500    = next((i for i in indices if "S&P" in i.get("n","")), {})
    sp_pct   = sp500.get("pct", 0) or 0
    bull_prob = max(20, min(80, 50 + (fng_val - 50) * 0.4 - (conf_score * 0.15) + (sp_pct * 2)))
    bear_prob = max(15, min(75, 100 - bull_prob - 15))
    neut_prob = max(5, 100 - bull_prob - bear_prob)
    forecasts.append({
        "id":       "mkt_dir",
        "category": "Markets",
        "title":    "Equity Market Direction",
        "icon":     "📈",
        "score":    int(bull_prob),
        "level":    "Bull" if bull_prob > 55 else "Bear" if bear_prob > 45 else "Neutral",
        "color":    SCENARIO_COLORS["Bull"] if bull_prob > 55 else SCENARIO_COLORS["Bear"],
        "signals":  f"F&G={fng_val}, Yield Curve={'INVERTED ⚠' if inverted else 'Normal'}, S&P={sp_pct:+.2f}%",
        "horizons": [
            {"days":7,  "prob":int(bull_prob), "direction":"Up" if bull_prob>50 else "Down", "label":"7-day"},
            {"days":30, "prob":int(bull_prob*0.85+15), "direction":"Up" if bull_prob>50 else "Down", "label":"30-day"},
        ],
        "scenarios": [
            {"name":"Bull Run",    "prob":int(bull_prob), "desc":"Continued upside, earnings strength, soft landing narrative", "color":SCENARIO_COLORS["Bull"]},
            {"name":"Correction",  "prob":int(bear_prob), "desc":"5-15% pullback from geo-risk or rate concerns",               "color":SCENARIO_COLORS["Bear"]},
            {"name":"Sideways",    "prob":int(neut_prob), "desc":"Rangebound action, low conviction either way",                "color":SCENARIO_COLORS["Neutral"]},
        ],
        "key_risks": [
            "Yield curve INVERTED — historical recession signal" if inverted else "Yield curve normal",
            f"Fear & Greed at {fng_val} — {'extreme greed, correction risk' if fng_val>75 else 'extreme fear, potential bottom' if fng_val<25 else 'neutral zone'}",
            f"Geopolitical premium elevated ({conf_score}/100)" if conf_score > 50 else "Geopolitical risk manageable",
        ],
        "ts": now_str,
    })

    # ── Forecast 3: Recession Risk ─────────────────────────────────────────
    rec_score = min(95, (25 if inverted else 0) + (econ_ct * 4) + (20 if fng_val < 30 else 0) + (mkt_score * 0.3))
    forecasts.append({
        "id":       "rec_risk",
        "category": "Economy",
        "title":    "Recession Probability",
        "icon":     "📉",
        "score":    int(rec_score),
        "level":    "High" if rec_score > 60 else "Elevated" if rec_score > 35 else "Low",
        "color":    "#f26c5c" if rec_score > 60 else "#ffd060" if rec_score > 35 else "#4cc870",
        "signals":  f"Yield inversion={'Yes ⚠' if inverted else 'No'}, Crisis signals={econ_ct} (24h), F&G={fng_val}",
        "horizons": [
            {"days":90,  "prob":int(rec_score),      "direction":"Up" if rec_score>50 else "Down", "label":"90-day"},
            {"days":180, "prob":int(rec_score*1.1),  "direction":"Up" if rec_score>50 else "Down", "label":"180-day"},
        ],
        "scenarios": [
            {"name":"Soft Landing", "prob":max(10,100-int(rec_score)-15), "desc":"Fed threads the needle, no recession",       "color":SCENARIO_COLORS["Bull"]},
            {"name":"Mild Recession","prob":int(rec_score*0.6),           "desc":"1-2 quarters negative GDP, moderate pain",   "color":SCENARIO_COLORS["Watch"]},
            {"name":"Hard Landing",  "prob":int(rec_score*0.4),           "desc":"Sharp contraction, unemployment spike",       "color":SCENARIO_COLORS["Bear"]},
        ],
        "key_risks": [
            "Inverted yield curve (2Y > 10Y) — strong historical recession predictor" if inverted else "Yield curve not inverted",
            f"{econ_ct} economic crisis signals in news last 24h",
            f"Credit conditions: {'tightening' if fng_val < 40 else 'loose'}",
        ],
        "ts": now_str,
    })

    # ── Forecast 4: Geopolitical Shock ────────────────────────────────────
    shock_score = min(95, (nuke_ct * 12) + (crit_count * 18) + (esc_count * 8) + 10)
    forecasts.append({
        "id":       "geo_shock",
        "category": "Geopolitics",
        "title":    "Geopolitical Black Swan Risk",
        "icon":     "🌍",
        "score":    int(shock_score),
        "level":    "Critical" if shock_score > 65 else "Elevated" if shock_score > 35 else "Low",
        "color":    "#ff6b35" if shock_score > 65 else "#ffd060" if shock_score > 35 else "#4cc870",
        "signals":  f"Nuclear signals={nuke_ct}, Critical conflicts={crit_count}, Escalating={esc_count}",
        "horizons": [
            {"days":30, "prob":int(shock_score*0.7), "direction":"Up" if shock_score>40 else "Down", "label":"30-day"},
            {"days":90, "prob":int(shock_score*0.85),"direction":"Up" if shock_score>40 else "Down", "label":"90-day"},
        ],
        "scenarios": [
            {"name":"Black Swan",  "prob":int(shock_score*0.4), "desc":"Sudden major escalation: nuclear threat, naval confrontation, capital city strike", "color":SCENARIO_COLORS["Critical"]},
            {"name":"Hot Spot",    "prob":int(shock_score*0.6), "desc":"One conflict rapidly escalates, regional powers drawn in",                          "color":SCENARIO_COLORS["Bear"]},
            {"name":"Containment", "prob":max(10,100-shock_score),"desc":"All conflicts remain contained within current theaters",                           "color":SCENARIO_COLORS["Bull"]},
        ],
        "key_risks": [f"Nuclear rhetoric detected ({nuke_ct} mentions)" if nuke_ct>0 else "No nuclear signals",
                      f"{crit_count} conflicts at critical severity","Great power competition remains elevated"],
        "ts": now_str,
    })

    # Save & log
    db["forecasts"] = forecasts
    db["last_run"]  = now_str
    _save(db)
    return forecasts

def get_forecasts():
    db = _load()
    return {"forecasts": db.get("forecasts",[]), "last_run": db.get("last_run","")}

def build_forecast_prompt(forecasts, conflicts, fin_data):
    """Build prompt for AI-enhanced forecast."""
    esc    = [c["name"] for c in conflicts if c.get("trend")=="escalating"][:5]
    crit   = [c["name"] for c in conflicts if c.get("severity")=="critical"][:5]
    fd     = fin_data.get("data",{})
    fng    = fd.get("fng",{}).get("current",{})
    yields = fd.get("yields",{})
    f_sum  = "\n".join(f"• {f['icon']} {f['title']}: {f['score']}/100 ({f['level']}) — {f['signals']}" for f in forecasts)
    return f"""You are a strategic forecaster combining geopolitical intelligence with quantitative market analysis.

SIGNAL DATA (auto-generated):
{f_sum}

ACTIVE CONFLICTS ESCALATING: {', '.join(esc) if esc else 'None'}
CRITICAL CONFLICTS: {', '.join(crit) if crit else 'None'}
FEAR & GREED: {fng.get('v','?')} — {fng.get('cls','?')}
YIELDS: {', '.join(f"{k}: {v.get('rate')}%" for k,v in yields.items())}

Provide a deep strategic forecast covering:

## 🎯 7-DAY OUTLOOK (highest conviction calls this week)
## 📅 30-DAY SCENARIO ANALYSIS (three scenarios: Bull/Base/Bear with probabilities)
## 🔭 90-DAY STRATEGIC VIEW (macro trends and their implications)
## ⚠️ BLACK SWAN WATCH (low-probability, high-impact events to hedge)
## 💡 POSITIONING RECOMMENDATIONS (how to position given the above — NOT financial advice)
## 🔑 KEY DATES & TRIGGERS TO WATCH (upcoming events that could shift the forecast)

Be specific, data-driven, and reference the current signal data above."""
