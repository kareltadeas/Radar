import argparse
import json
import os
import sys
import time
from datetime import datetime

from config import (
    DATA_DIR,
    RADAR_CACHE_FILE,
    PORTFOLIO_FILE,
    GEMINI_API_KEY,
    ALPHA_RULES
)
from universe import get_universe
from data_engine import (
    DEFAULT_UNIVERSE,
    batch_download_technicals,
    _load_fundamentals_cache,
    _save_fundamentals_cache,
    get_stock_fundamentals,
    evaluate_stock_combined,
    load_portfolio,
    audit_portfolio_position,
    generate_ai_analysis
)


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def run_scanner(mode: str = "full", force_refresh: bool = False, generate_ai_for_alpha: bool = True) -> dict:
    """
    Hlavní ranní skener trhu využívající dvoustupňový trychtýř.
    """
    start_time = time.time()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n========================================================")
    print(f"🚀 S&P 500 & MIDCAP 400 RADAR: Ranní sken spuštěn ({now_iso})")
    print(f"Režim: {mode.upper()} | Force refresh: {force_refresh}")
    print(f"========================================================\n")

    # 1. Výběr univerza
    if mode == "full":
        universe = get_universe(include_sp500=True, include_midcap=True, force_refresh=force_refresh)
    elif mode == "sp500":
        universe = get_universe(include_sp500=True, include_midcap=False, force_refresh=force_refresh)
    else:
        universe = [{"ticker": t, "name": t, "sector": "Sample", "index": "SAMPLE"} for t in DEFAULT_UNIVERSE]

    universe_map = {item["ticker"]: item for item in universe}
    all_tickers = list(universe_map.keys())

    # Načtení portfolia pro zaručení jejich přítomnosti
    portfolio_df = load_portfolio()
    portfolio_tickers = []
    if not portfolio_df.empty and "ticker" in portfolio_df.columns:
        portfolio_tickers = [str(t).strip().upper() for t in portfolio_df["ticker"].dropna().unique() if t]

    tickers_to_fetch = list(set(all_tickers + portfolio_tickers))
    print(f"📊 1. KROK: Stahuji technická data pro {len(tickers_to_fetch)} akcií...")

    # 2. Hromadný batch download technických dat (rychlý trychtýř)
    techs = batch_download_technicals(tickers_to_fetch, chunk_size=120)
    print(f"✅ Úspěšně získána technická data pro {len(techs)} akcií za {time.time() - start_time:.1f} s.")

    # 3. Tržní šíře (Market Breadth)
    stocks_above_sma200 = sum(1 for t, data in techs.items() if data["price"] > data["sma_200"])
    breadth_pct = (stocks_above_sma200 / len(techs) * 100) if techs else 0.0

    # 4. Pre-screening: Výběr kandidátů na detailní fundamentální šetření
    candidates = set()
    for t, data in techs.items():
        if data.get("is_sat_candidate") or data.get("is_core_candidate"):
            candidates.add(t)

    # Vždy zahrnout portfolio
    for pt in portfolio_tickers:
        if pt in techs:
            candidates.add(pt)

    print(f"🎯 2. KROK: Pre-screening vybral {len(candidates)} kandidátů pro fundamentální analýzu (zbytek odfiltrován).")

    # 5. Načtení fundamentů s mezipamětí (chrání před HTTP 429)
    fund_cache = _load_fundamentals_cache()
    fund_start = time.time()
    fundamentals = {}

    for idx, t in enumerate(candidates, 1):
        fundamentals[t] = get_stock_fundamentals(t, cache=fund_cache, force_refresh=force_refresh)
        if idx % 25 == 0 or idx == len(candidates):
            print(f"   - Fundamenty zpracovány: {idx}/{len(candidates)}")

    _save_fundamentals_cache(fund_cache)
    print(f"✅ Fundamenty zkompletovány za {time.time() - fund_start:.1f} s.")

    # 6. Finální evaluace a kategorizace
    alpha_alerts = []
    core_watchlist = []
    satellite_watchlist = []
    evaluated_all = []

    for t in candidates:
        tech_data = techs.get(t)
        fund_data = fundamentals.get(t)
        if not tech_data or not fund_data:
            continue

        meta = universe_map.get(t)
        item = evaluate_stock_combined(t, tech_data, fund_data, meta=meta)
        evaluated_all.append(item)

        if item["status"] == "ALPHA_ALERT":
            alpha_alerts.append(item)
        elif item["bucket"] == "CORE" and item["status"] == "WATCHLIST":
            core_watchlist.append(item)
        elif item["bucket"] == "SATELLITE" and item["status"] == "WATCHLIST":
            satellite_watchlist.append(item)

    # Řazení podle skóre a Wall Street upside potenciálu
    alpha_alerts.sort(key=lambda x: (x["score"], x.get("upside_pct", 0)), reverse=True)

    # Přísná redukce na exkluzivní TOP N Alpha alertů (ostatní kvalitní akcie jdou do watchlistu k sledování)
    max_alerts = ALPHA_RULES.get("max_daily_alerts", 5)
    if len(alpha_alerts) > max_alerts:
        excess = alpha_alerts[max_alerts:]
        alpha_alerts = alpha_alerts[:max_alerts]
        for exc in excess:
            exc["status"] = "WATCHLIST"
            if exc["bucket"] == "CORE":
                core_watchlist.append(exc)
            elif exc["bucket"] == "SATELLITE":
                satellite_watchlist.append(exc)

    core_watchlist.sort(key=lambda x: (x["score"], x.get("upside_pct", 0), abs(x["pct_from_high"])), reverse=True)
    satellite_watchlist.sort(key=lambda x: (x["score"], x.get("upside_pct", 0), x["rev_growth_pct"]), reverse=True)

    # 7. AI analýza pro Alpha Alerty (pokud je povolená)
    ai_analyses = {}
    if alpha_alerts and generate_ai_for_alpha:
        print(f"\n🧠 3. KROK: Generuji AI analýzu pro {len(alpha_alerts)} ALPHA ALERT titulů...")
        for pick in alpha_alerts:
            t = pick["ticker"]
            print(f"   - Zpracovávám AI rozbor pro {t}...")
            ai_analyses[t] = generate_ai_analysis(pick, custom_api_key=GEMINI_API_KEY)

    # 8. Audit uživatelského portfolia
    portfolio_audits = []
    red_flags_count = 0
    yellow_flags_count = 0

    if not portfolio_df.empty:
        print(f"\n🛡️ 4. KROK: Provádím audit drženého portfolia ({len(portfolio_df)} pozic)...")
        for _, row in portfolio_df.iterrows():
            if not row.get("ticker"):
                continue
            pt = str(row["ticker"]).strip().upper()
            precomputed = next((item for item in evaluated_all if item["ticker"] == pt), None)
            if not precomputed and pt in techs:
                fund_d = fundamentals.get(pt) or get_stock_fundamentals(pt, cache=fund_cache)
                precomputed = evaluate_stock_combined(pt, techs[pt], fund_d, meta=universe_map.get(pt))

            audit_res = audit_portfolio_position(row.to_dict(), precomputed_stock=precomputed)
            if audit_res.get("flag_level") == "RED":
                red_flags_count += 1
            elif audit_res.get("flag_level") == "YELLOW":
                yellow_flags_count += 1
            portfolio_audits.append(audit_res)

    elapsed_total = round(time.time() - start_time, 1)

    # Sestavení finálního cache reportu
    report = {
        "timestamp": now_iso,
        "mode": mode,
        "elapsed_seconds": elapsed_total,
        "summary": {
            "total_universe": len(universe),
            "successfully_scanned": len(techs),
            "screened_candidates": len(candidates),
            "stocks_above_sma200_pct": round(breadth_pct, 1),
            "alpha_alerts_count": len(alpha_alerts),
            "core_watchlist_count": len(core_watchlist),
            "satellite_watchlist_count": len(satellite_watchlist),
            "portfolio_red_flags": red_flags_count,
            "portfolio_yellow_flags": yellow_flags_count
        },
        "alpha_alerts": alpha_alerts,
        "core_watchlist": core_watchlist,
        "satellite_watchlist": satellite_watchlist,
        "ai_analyses": ai_analyses,
        "portfolio_audits": portfolio_audits
    }

    _ensure_dir(RADAR_CACHE_FILE)
    with open(RADAR_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n========================================================")
    print(f"🏁 SKEN DOKONČEN ZA {elapsed_total} sekund")
    print(f"📊 Tržní šíře (akcie nad SMA 200): {breadth_pct:.1f} %")
    print(f"🚨 ALPHA ALERTS: {len(alpha_alerts)} nalezeno")
    print(f"🛡️ Core Watchlist: {len(core_watchlist)} akcií")
    print(f"🚀 Satellite Watchlist: {len(satellite_watchlist)} akcií")
    print(f"🛡️ Portfolio audit: {red_flags_count} červených vlajek, {yellow_flags_count} žlutých")
    print(f"💾 Výsledky uloženy do: {RADAR_CACHE_FILE}")
    print(f"========================================================\n")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S&P 500 & MidCap 400 Morning Radar Scanner")
    parser.add_argument(
        "--mode",
        choices=["full", "sp500", "quick"],
        default="quick",
        help="Režim skenu: 'full' (S&P 500 + MidCap 400), 'sp500' (jen S&P 500), 'quick' (30 ukázkových tickerů)"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Vynutí přestažení fundamentů a seznamu indexů bez ohledu na cache"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Vynechá automatické generování AI analýzy"
    )

    args = parser.parse_args()
    run_scanner(mode=args.mode, force_refresh=args.force_refresh, generate_ai_for_alpha=(not args.no_ai))
