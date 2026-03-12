"""
geo_economics.py  —  Geo-Economics Intelligence Engine
Sanctions tracker, trade flow disruptions, currency war signals, supply chain risks
"""
import json, os
from datetime import datetime, timezone, timedelta

GEO_F = "geo_economics.json"

SANCTIONS_DB = [
    {"target":"Russia","issuer":"US/EU/UK","sector":"Finance","type":"SWIFT ban","date":"2022-02","impact":"High","status":"Active","assets_frozen":"$350B"},
    {"target":"Russia","issuer":"US/EU","sector":"Energy","type":"Oil price cap ($60/bbl)","date":"2022-12","impact":"High","status":"Active","assets_frozen":"—"},
    {"target":"Russia","issuer":"US","sector":"Technology","type":"Chip/tech export ban","date":"2022-03","impact":"High","status":"Active","assets_frozen":"—"},
    {"target":"Iran","issuer":"US","sector":"Oil/Finance","type":"Comprehensive sanctions","date":"2018-05","impact":"Critical","status":"Active","assets_frozen":"$100B+"},
    {"target":"North Korea","issuer":"UN/US","sector":"All sectors","type":"Comprehensive sanctions","date":"2006","impact":"Critical","status":"Active","assets_frozen":"—"},
    {"target":"Venezuela","issuer":"US","sector":"Oil/Finance","type":"Sectoral sanctions","date":"2019-01","impact":"High","status":"Active","assets_frozen":"~$7B"},
    {"target":"Myanmar","issuer":"US/EU","sector":"Military/Finance","type":"Targeted sanctions","date":"2021-02","impact":"Medium","status":"Active","assets_frozen":"—"},
    {"target":"Belarus","issuer":"US/EU","sector":"Finance/Aviation","type":"Sectoral sanctions","date":"2021-05","impact":"Medium","status":"Active","assets_frozen":"—"},
    {"target":"China (chips)","issuer":"US","sector":"Semiconductors","type":"Export controls (CHIPS Act)","date":"2022-10","impact":"High","status":"Active","assets_frozen":"—"},
    {"target":"Huawei","issuer":"US","sector":"Technology","type":"Entity list/export ban","date":"2019-05","impact":"High","status":"Active","assets_frozen":"—"},
    {"target":"Cuba","issuer":"US","sector":"All sectors","type":"Embargo","date":"1962","impact":"High","status":"Active","assets_frozen":"—"},
    {"target":"Sudan","issuer":"US","sector":"Finance/Military","type":"Targeted sanctions","date":"2023","impact":"Medium","status":"Active","assets_frozen":"—"},
]

TRADE_CHOKEPOINTS = [
    {"name":"Strait of Hormuz","throughput":"21M bbl/day oil (21% global)","risk_level":"Critical","active_threat":"Houthi/Iran activity","coords":[26.5,56.3],"impact_sectors":["Oil","LNG","Asia imports"]},
    {"name":"Suez Canal","throughput":"12% global trade","risk_level":"High","active_threat":"Houthi Red Sea attacks","coords":[30.7,32.3],"impact_sectors":["Shipping","Consumer goods","Oil"]},
    {"name":"Taiwan Strait","throughput":"50% global container ships","risk_level":"Elevated","active_threat":"PLA military exercises","coords":[24.0,119.5],"impact_sectors":["Semiconductors","Electronics","Global trade"]},
    {"name":"South China Sea","throughput":"$3.4T annual trade","risk_level":"Elevated","active_threat":"Territorial disputes","coords":[13.0,113.5],"impact_sectors":["Semiconductors","Electronics","LNG"]},
    {"name":"Panama Canal","throughput":"5% global trade","risk_level":"Medium","active_threat":"Drought-reduced capacity","coords":[9.0,-79.5],"impact_sectors":["LNG","Coal","Container ships"]},
    {"name":"Bosphorus Strait","throughput":"Ukrainian grain corridor","risk_level":"Medium","active_threat":"Black Sea tensions","coords":[41.1,29.1],"impact_sectors":["Wheat","Corn","Fertilizers"]},
    {"name":"TSMC Taiwan","throughput":"90% advanced chips (<5nm)","risk_level":"Critical","active_threat":"Cross-strait tension","coords":[24.8,121.0],"impact_sectors":["AI chips","Smartphones","Autos","Defense"]},
    {"name":"DRC Cobalt Mines","throughput":"70% global cobalt","risk_level":"High","active_threat":"M23 conflict","coords":[-5.5,26.5],"impact_sectors":["EV batteries","Electronics","Defense"]},
]

CURRENCY_SIGNALS = [
    {"pair":"USD/CNY","signal":"De-dollarization","detail":"China increasing bilateral trade in yuan, PBOC gold buying at record pace","risk":"Gradual USD reserve erosion","severity":"Medium"},
    {"pair":"USD/RUB","signal":"Sanctions bypass","detail":"Russia-China trade in RMB+Rubles, BRICS payment system in development","risk":"Reduced USD effectiveness","severity":"Medium"},
    {"pair":"USD/SAR","signal":"Petrodollar stress","detail":"Saudi Arabia considering non-USD oil sales to China, BRICS membership","risk":"Petrodollar system erosion","severity":"Elevated"},
    {"pair":"EUR/GBP","signal":"Post-Brexit divergence","detail":"UK-EU trade friction continues, BoE vs ECB rate divergence","risk":"GBP sustained weakness","severity":"Low"},
    {"pair":"JPY","signal":"BoJ yield cap exit","detail":"Bank of Japan slowly exiting ultra-loose policy, yen carry trade at risk","risk":"Global carry trade unwind","severity":"High"},
    {"pair":"EM currencies","signal":"Fed rate pressure","detail":"High US rates strengthen dollar, pressuring EM currencies and debt","risk":"EM debt crisis","severity":"Medium"},
]

SUPPLY_CHAIN_RISKS = [
    {"sector":"Semiconductors","risk":"Critical","bottleneck":"TSMC Taiwan (90% advanced chips)","alt_capacity":"Intel/Samsung (3-5yr to scale)","geopolitical_trigger":"Taiwan Strait conflict"},
    {"sector":"Rare Earth Metals","risk":"High","bottleneck":"China controls 60% production, 85% refining","alt_capacity":"Australia, USA (years away)","geopolitical_trigger":"US-China trade war escalation"},
    {"sector":"Cobalt (EV Batteries)","risk":"High","bottleneck":"DRC 70% production","alt_capacity":"Australia, Philippines","geopolitical_trigger":"DRC conflict escalation"},
    {"sector":"Wheat/Grain","risk":"Elevated","bottleneck":"Ukraine/Russia = 30% global exports","alt_capacity":"USA, Canada, Australia","geopolitical_trigger":"Ukraine war escalation/blockade"},
    {"sector":"Natural Gas (EU)","risk":"Elevated","bottleneck":"Russia pipeline dependency","alt_capacity":"LNG from US/Qatar","geopolitical_trigger":"Full Russia gas cutoff"},
    {"sector":"Lithium","risk":"Medium","bottleneck":"Australia/Chile mines, China refining","alt_capacity":"Direct lithium extraction (5yr)","geopolitical_trigger":"Chile nationalization or China ban"},
    {"sector":"Oil","risk":"Elevated","bottleneck":"Middle East/Russia = 40% global","alt_capacity":"US shale (months)","geopolitical_trigger":"Iran/Saudi conflict, Hormuz closure"},
    {"sector":"Palladium","risk":"High","bottleneck":"Russia = 40% global supply","alt_capacity":"South Africa","geopolitical_trigger":"Russia sanctions expansion"},
]

def _now(): return datetime.now(timezone.utc)

def get_sanctions():
    return SANCTIONS_DB

def get_chokepoints():
    return TRADE_CHOKEPOINTS

def get_currency_signals():
    return CURRENCY_SIGNALS

def get_supply_chain():
    return SUPPLY_CHAIN_RISKS

def analyze_geoeconomics(articles, conflicts, fin_data):
    """Cross-reference live data with geo-economic intelligence."""
    fd     = fin_data.get("data", {})
    forex  = {i["s"]: i for i in fd.get("forex", [])}
    commod = {i["s"]: i for i in fd.get("commodities", [])}

    # Live chokepoint status from recent articles
    choke_alerts = []
    for cp in TRADE_CHOKEPOINTS:
        kws = cp["name"].lower().split() + [w.lower() for s in cp["impact_sectors"] for w in s.split()]
        hits = sum(1 for a in articles[:100] if any(kw in (a.get("title","")+" "+a.get("summary","")).lower() for kw in kws))
        if hits >= 2:
            choke_alerts.append({**cp, "article_hits": hits, "alert": True})

    # Sanctions news pulse
    sanction_news = []
    for a in articles[:150]:
        text = (a.get("title","")+" "+a.get("summary","")).lower()
        if any(kw in text for kw in ["sanctions","sanctioned","export ban","embargo","asset freeze","entity list"]):
            sanction_news.append({"title": a.get("title",""), "source": a.get("source",""), "ago": a.get("ago",""), "id": a.get("id","")})

    # Currency war signals
    curr_live = []
    for cs in CURRENCY_SIGNALS:
        pair = cs["pair"]
        fx   = forex.get(pair.replace("/","")+"=X") or forex.get(pair[:3]+pair[-3:]+"=X")
        curr_live.append({**cs, "live_pct": fx.get("pct",0) if fx else None})

    # Supply chain stress from commodity prices
    sc_live = []
    SECTOR_COMMODITY = {"Wheat/Grain":"ZW=F","Oil":"CL=F","Natural Gas (EU)":"NG=F","Cobalt (EV Batteries)":"HG=F"}
    for sc in SUPPLY_CHAIN_RISKS:
        cm_sym = SECTOR_COMMODITY.get(sc["sector"])
        cm_live = commod.get(cm_sym)
        sc_live.append({**sc, "live_pct": cm_live.get("pct",0) if cm_live else None, "live_price": cm_live.get("price") if cm_live else None})

    return {
        "sanctions":       SANCTIONS_DB,
        "chokepoints":     TRADE_CHOKEPOINTS,
        "choke_alerts":    choke_alerts,
        "sanction_news":   sanction_news[:8],
        "currency_signals":curr_live,
        "supply_chain":    sc_live,
        "ts":              _now().isoformat(),
    }

def build_geoeconomics_prompt(data, articles):
    """Build AI prompt for geo-economics analysis."""
    alerts = data.get("choke_alerts",[])
    sanc_n = data.get("sanction_news",[])
    sc     = data.get("supply_chain",[])
    high_sc = [s for s in sc if s["risk"] in ("Critical","High")]
    return f"""You are a geo-economics intelligence analyst specializing in sanctions, trade flows, and economic warfare.

LIVE CHOKEPOINT ALERTS ({len(alerts)} active):
{chr(10).join(f"⚠ {a['name']}: {a['risk_level']} risk, {a['article_hits']} recent articles, threat={a['active_threat']}" for a in alerts) if alerts else "No active chokepoint alerts"}

CRITICAL SUPPLY CHAIN RISKS:
{chr(10).join(f"• {s['sector']}: {s['risk']} risk — {s['bottleneck']} (trigger: {s['geopolitical_trigger']})" for s in high_sc)}

RECENT SANCTIONS NEWS:
{chr(10).join(f"• {s['title']} [{s['source']}]" for s in sanc_n[:6]) if sanc_n else "No major sanctions news"}

CURRENCY WAR SIGNALS: De-dollarization, JPY carry trade risk, EM pressure

Provide a geo-economics intelligence briefing:

## 💰 ECONOMIC WARFARE UPDATE (sanctions effectiveness, new measures, workarounds)
## 🚢 TRADE FLOW DISRUPTIONS (chokepoint status, shipping cost impact, rerouting)
## 💱 CURRENCY WAR SIGNALS (de-dollarization progress, carry trade risks, EM vulnerability)
## ⛓️ SUPPLY CHAIN STRESS POINTS (current bottlenecks, stockpile levels, substitution options)
## 🔮 ECONOMIC WEAPON SCENARIOS (what economic levers could be pulled and their effects)
## 📊 WINNERS & LOSERS (which countries/sectors benefit from current disruptions)
## 🎯 6-MONTH GEO-ECONOMICS OUTLOOK"""
