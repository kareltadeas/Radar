import json
import os
import time
from datetime import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from google import genai

from config import (
    CORE_RULES,
    SATELLITE_RULES,
    ALPHA_RULES,
    PORTFOLIO_RULES,
    GEMINI_API_KEY,
    DATA_DIR,
    CACHE_DIR,
    PORTFOLIO_FILE,
    FUNDAMENTALS_CACHE_FILE,
    FUNDAMENTALS_CACHE_TTL
)

DEFAULT_UNIVERSE = [
    "MSFT", "AAPL", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "JNJ", "V", "PG",
    "UNH", "HD", "MA", "ABBV", "KO", "PEP", "COST", "MRK", "AVGO", "LLY",
    "PLTR", "CRWD", "PANW", "ANET", "DECK", "AXON", "URI", "GWW", "CAT", "DE"
]


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


# --- PERZISTENCE PORTFOLIA ---

def load_portfolio() -> pd.DataFrame:
    """Načte uložené portfolio z lokálního JSON souboru."""
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data:
                return pd.DataFrame(data)
        except Exception:
            pass
    return pd.DataFrame([
        {"ticker": "MSFT", "shares": 5.0, "buy_price": 380.0, "type": "CORE"},
        {"ticker": "NVDA", "shares": 10.0, "buy_price": 110.0, "type": "SATELLITE"},
        {"ticker": "JNJ", "shares": 8.0, "buy_price": 155.0, "type": "CORE"},
    ])


def save_portfolio(df: pd.DataFrame) -> None:
    """Uloží upravené portfolio na disk."""
    records = df.dropna(subset=["ticker"]).to_dict(orient="records")
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# --- TECHNICKÉ INDIKÁTORY ---

def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """
    Spočítá Wilderovo RSI (standardní exponenciální vyhlazování používané na burze).
    Eliminuje odchylky a falešné signály z prostého klouzavého průměru.
    """
    clean_series = series.dropna()
    if len(clean_series) < period + 1:
        return 50.0

    delta = clean_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing: alpha = 1 / period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0


# --- MEZIPAMĚŤ FUNDAMENTŮ ---

def _load_fundamentals_cache() -> dict:
    if os.path.exists(FUNDAMENTALS_CACHE_FILE):
        try:
            with open(FUNDAMENTALS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_fundamentals_cache(cache: dict) -> None:
    _ensure_dir(FUNDAMENTALS_CACHE_FILE)
    try:
        with open(FUNDAMENTALS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Nelze uložit mezipaměť fundamentů: {e}")


def get_stock_fundamentals(ticker: str, cache: dict | None = None, force_refresh: bool = False) -> dict:
    """
    Získá fundamentální data akcie s využitím lokální mezipaměti (TTL 24h).
    Chrání před Yahoo Finance rate-limitem (HTTP 429).
    """
    now = time.time()
    if cache is not None and not force_refresh:
        entry = cache.get(ticker)
        if entry and (now - entry.get("cached_at", 0)) < FUNDAMENTALS_CACHE_TTL:
            return entry["data"]

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        raw_news = stock.news[:5] if hasattr(stock, "news") and stock.news else []
        clean_news = []
        for n in raw_news:
            title = n.get("content", {}).get("title") or n.get("title") or ""
            if title:
                clean_news.append(title)

        data = {
            "name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector") or "Unknown",
            "industry": info.get("industry") or "Unknown",
            "pe": info.get("trailingPE") or info.get("forwardPE"),
            "forward_pe": info.get("forwardPE"),
            "debt_to_equity": info.get("debtToEquity"),
            "fcf": info.get("freeCashflow"),
            "rev_growth": info.get("revenueGrowth") or 0.0,
            "profit_margin": (info.get("profitMargins") or 0.0) * 100,
            "roe": (info.get("returnOnEquity") or 0.0) * 100,
            "target_price": info.get("targetMeanPrice"),
            "analyst_consensus": (info.get("recommendationKey") or "none").upper(),
            "news": clean_news
        }

        if cache is not None:
            cache[ticker] = {"cached_at": now, "data": data}
        return data
    except Exception as e:
        return {
            "name": ticker,
            "sector": "Unknown",
            "industry": "Unknown",
            "pe": None,
            "forward_pe": None,
            "debt_to_equity": None,
            "fcf": None,
            "rev_growth": 0.0,
            "profit_margin": 0.0,
            "roe": 0.0,
            "target_price": None,
            "analyst_consensus": "NONE",
            "news": []
        }


# --- DVOYSTUPŇOVÝ FUNNEL: HROMADNÝ SBĚR TECHNICKÝCH DAT ---

def batch_download_technicals(tickers: list[str], chunk_size: int = 150) -> dict[str, dict]:
    """
    Hromadně stáhne cenovou historii pro stovky tickerů najednou v dávkách přes yf.download.
    Zabere ~15-25 sekund pro celé universum (900+ tickerů) namísto 20 minut sekvenčně.
    """
    results = {}
    total = len(tickers)

    for i in range(0, total, chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            df = yf.download(
                tickers=chunk,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False
            )
            if df.empty:
                continue

            for t in chunk:
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        if t in df.columns.levels[0]:
                            sub = df[t]
                        elif t in df.columns:
                            sub = df[t]
                        else:
                            continue
                    else:
                        sub = df

                    sub_clean = sub.dropna(subset=["Close"])
                    if len(sub_clean) < 180:  # Alespoň ~180 obchodních dní pro SMA 200
                        continue

                    close = sub_clean["Close"]
                    high = sub_clean["High"]
                    low = sub_clean["Low"]

                    current_price = float(close.iloc[-1])
                    sma_50 = float(close.rolling(50).mean().iloc[-1])
                    sma_200 = float(close.rolling(200).mean().iloc[-1])
                    high_52w = float(high.max())
                    low_52w = float(low.min())
                    pct_from_high = ((current_price - high_52w) / high_52w) * 100
                    rsi = calculate_rsi(close)

                    # Vyhodnocení kandidatury pro trychtýř (pre-screening)
                    is_sat_candidate = (
                        current_price > sma_50
                        and current_price > sma_200
                        and (SATELLITE_RULES["rsi_min"] <= rsi <= SATELLITE_RULES["rsi_max"] + 5.0)
                    )
                    # Core kandidát: rozumná sleva od maxima bez totálního krachu
                    is_core_candidate = (
                        pct_from_high <= CORE_RULES["dip_min_pct"]
                        and pct_from_high >= (CORE_RULES["dip_max_pct"] - 10.0)
                    )

                    results[t] = {
                        "price": round(current_price, 2),
                        "sma_50": round(sma_50, 2),
                        "sma_200": round(sma_200, 2),
                        "high_52w": round(high_52w, 2),
                        "low_52w": round(low_52w, 2),
                        "pct_from_high": round(pct_from_high, 1),
                        "rsi": round(rsi, 1),
                        "is_sat_candidate": is_sat_candidate,
                        "is_core_candidate": is_core_candidate
                    }
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Chyba při batch downloadu pro dávku {i}-{i+chunk_size}: {e}")

    return results


# --- VYHODNOCENÍ JEDNOTLIVÉ AKCIE ---

def evaluate_stock_combined(
    ticker: str,
    tech: dict,
    fund: dict,
    meta: dict | None = None
) -> dict:
    """
    Zkombinuje technická a fundamentální data a aplikuje investiční pravidla
    s ochranou proti padajícímu noži a sektorovou neutralitou pro banky.
    """
    company_name = (meta and meta.get("name")) or fund.get("name") or ticker
    sector = (meta and meta.get("sector")) or fund.get("sector") or "Unknown"

    current_price = tech["price"]
    sma_50 = tech["sma_50"]
    sma_200 = tech["sma_200"]
    pct_from_high = tech["pct_from_high"]
    rsi = tech["rsi"]

    pe_ratio = fund.get("pe")
    forward_pe = fund.get("forward_pe")
    debt_to_equity = fund.get("debt_to_equity")
    fcf = fund.get("fcf")
    rev_growth = fund.get("rev_growth") or 0.0
    profit_margin = fund.get("profit_margin") or 0.0
    roe = fund.get("roe") or 0.0
    target_price = fund.get("target_price")
    recommendation = fund.get("analyst_consensus") or "NONE"
    news = fund.get("news") or []

    reasons = []
    bucket = "NEUTRAL"
    status = "NEUTRAL"
    score = 0

    # Výpočet upside potenciálu podle analytiků Wall Street
    upside_pct = 0.0
    if target_price and current_price and target_price > current_price:
        upside_pct = round(((target_price - current_price) / current_price) * 100, 1)

    # 1. TEST PRO KOŠ 1: CORE (Stabilita v rozumné slevě)
    is_exempt_debt = any(exempt_sec.lower() in sector.lower() for exempt_sec in CORE_RULES.get("exempt_sectors_debt", []))
    debt_ok = is_exempt_debt or (debt_to_equity is not None and debt_to_equity <= CORE_RULES["max_debt_to_equity"])
    fcf_ok = fcf is not None and fcf > CORE_RULES["min_free_cash_flow"]
    pe_ok = pe_ratio is not None and pe_ratio <= CORE_RULES["max_pe_ratio"]

    if debt_ok and fcf_ok and pe_ok:
        bucket = "CORE"
        score = 50
        debt_label = f"D/E: {debt_to_equity:.1f}%" if not is_exempt_debt else f"D/E vyjmuto ({sector})"
        reasons.append(f"Zdravý fundament (P/E: {pe_ratio:.1f}, {debt_label}, kladné FCF)")

        dip_min = CORE_RULES["dip_min_pct"]
        dip_max = CORE_RULES["dip_max_pct"]

        # Sleva v ideálním pásmu 5 % až 20 %
        if dip_max <= pct_from_high <= dip_min:
            score += 15
            reasons.append(f"Zdravá sleva {pct_from_high:.1f}% od maxima (pásmo {dip_min}% až {dip_max}%)")
        elif pct_from_high < dip_max:
            # Propad hlubší než 20 % -> podezření na Value Trap / padající nůž
            reasons.append(f"⚠️ Hluboký propad ({pct_from_high:.1f}% z max). Pozor na padající nůž.")
        else:
            reasons.append(f"Kvalitní firma čekající na slevu alespoň {abs(dip_min):.0f}% (nyní {pct_from_high:.1f}%)")

        # Dlouhodobý trend: cena drží nad SMA 200
        if current_price > sma_200:
            score += 10
            reasons.append(f"Cena (${current_price}) drží nad SMA 200 (${sma_200}) – dlouhodobý trend neporušen")

        # PŘÍSNÉ ALPHA KATALYZÁTORY PRO EXKLUZIVNÍ NÁKUP:
        # A) Atraktivní valuace pod 24
        if pe_ratio <= ALPHA_RULES["core_max_pe"]:
            score += 5
            reasons.append(f"Atraktivní valuace P/E {pe_ratio:.1f} <= {ALPHA_RULES['core_max_pe']}")

        # B) Mimořádná rentabilita (ROE >= 15 % A marže >= 12 %)
        if roe >= ALPHA_RULES["core_min_roe"] and profit_margin >= ALPHA_RULES["core_min_margin"]:
            score += 10
            reasons.append(f"Vysoká rentabilita (ROE: {roe:.1f}%, čistá marže: {profit_margin:.1f}%)")

        # C) Skutečná sleva (sweet spot -7 % až -18 %)
        if -18.0 <= pct_from_high <= ALPHA_RULES["core_dip_sweet_spot_min"]:
            score += 5
            reasons.append(f"Výrazná sleva v optimální zóně {pct_from_high:.1f}%")

        # D) Silný konsenzus Wall Street (upside >= 15 %)
        if upside_pct >= ALPHA_RULES["core_min_upside"]:
            score += 10
            reasons.append(f"Konsenzus Wall Street indikuje silný růstový potenciál +{upside_pct}%")

        # E) Stabilní byznys: tržby nesmí klesat
        if rev_growth < 0:
            score -= 20
            reasons.append(f"⚠️ Klesající tržby ({rev_growth*100:.1f}% YoY) – narušený růstový profil")
        else:
            score += 5
            reasons.append(f"Stabilní/rostoucí tržby (+{rev_growth*100:.1f}% YoY)")

        status = "ALPHA_ALERT" if score >= ALPHA_RULES["min_score"] else "WATCHLIST"

    # 2. TEST PRO KOŠ 2: SATELLITE (Růst & Momentum)
    is_sat_growth = rev_growth >= SATELLITE_RULES["min_revenue_growth"]
    is_sat_trend = current_price > sma_50 and current_price > sma_200

    if is_sat_growth and is_sat_trend:
        bucket = "SATELLITE"
        score = 50
        reasons = [
            f"Růst tržeb {rev_growth*100:.1f}% YoY",
            f"Cena (${current_price}) v uptrendu nad SMA 50 (${sma_50}) i SMA 200 (${sma_200})"
        ]

        # Momentum filtr pro Watchlist
        if SATELLITE_RULES["rsi_min"] <= rsi <= SATELLITE_RULES["rsi_max"]:
            score += 15
            reasons.append(f"Zdravé momentum (Wilder's RSI: {rsi:.1f})")
        else:
            reasons.append(f"RSI mimo okno 45–70 ({rsi:.1f})")

        # PŘÍSNÉ ALPHA KATALYZÁTORY PRO EXKLUZIVNÍ NÁKUP:
        # A) Hyper-růst tržeb (>= 25 % YoY)
        if rev_growth >= ALPHA_RULES["sat_min_growth"]:
            score += 10
            reasons.append(f"Hyper-růst tržeb (+{rev_growth*100:.1f}% YoY)")

        # B) Golden stack (SMA 50 je nad SMA 200)
        if sma_50 > sma_200:
            score += 10
            reasons.append(f"Institucionální Golden Stack (SMA 50 ${sma_50} > SMA 200 ${sma_200})")

        # C) Startovní RSI okno (50 až 65)
        if ALPHA_RULES["sat_rsi_min"] <= rsi <= ALPHA_RULES["sat_rsi_max"]:
            score += 5
            reasons.append(f"Ideální startovní momentum bez přehřátí (RSI {rsi:.1f})")

        # D) Wall Street upside (>= 20 %)
        if upside_pct >= ALPHA_RULES["sat_min_upside"]:
            score += 10
            reasons.append(f"Konsenzus Wall Street indikuje růstový potenciál +{upside_pct}%")

        status = "ALPHA_ALERT" if score >= ALPHA_RULES["min_score"] else "WATCHLIST"

    return {
        "ticker": ticker,
        "name": company_name,
        "sector": sector,
        "price": current_price,
        "pe": round(pe_ratio, 2) if pe_ratio is not None else None,
        "forward_pe": round(forward_pe, 2) if forward_pe is not None else None,
        "debt_to_equity": round(debt_to_equity, 1) if debt_to_equity is not None else None,
        "rev_growth_pct": round(rev_growth * 100, 1),
        "profit_margin_pct": round(profit_margin, 1),
        "roe_pct": round(roe, 1),
        "target_price": round(target_price, 2) if target_price else None,
        "upside_pct": upside_pct,
        "analyst_consensus": recommendation,
        "fcf": fcf,
        "rsi": rsi,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "pct_from_high": pct_from_high,
        "bucket": bucket,
        "status": status,
        "score": score,
        "reasons": reasons,
        "news": news
    }


def evaluate_stock(ticker: str) -> dict | None:
    """Zpětně kompatibilní funkce pro evaluaci jednoho tickeru (např. ruční dotaz z UI)."""
    techs = batch_download_technicals([ticker])
    if ticker not in techs:
        return None
    cache = _load_fundamentals_cache()
    fund = get_stock_fundamentals(ticker, cache=cache)
    _save_fundamentals_cache(cache)
    return evaluate_stock_combined(ticker, techs[ticker], fund)


# --- AUDIT DRŽENÉHO PORTFOLIA ---

def audit_portfolio_position(row: dict, precomputed_stock: dict | None = None) -> dict:
    """Zkontroluje drženou pozici a vystaví varovné vlajky."""
    ticker = str(row["ticker"]).strip().upper()
    data = precomputed_stock or evaluate_stock(ticker)

    if not data:
        return {
            "ticker": ticker,
            "flag_level": "NEZNÁMÉ",
            "audit_messages": ["Nepodařilo se načíst data z trhu."],
            "shares": row.get("shares", 0),
            "buy_price": row.get("buy_price", 0),
            "pos_type": row.get("type", "CORE"),
            "pnl_pct": 0.0
        }

    pnl_pct = 0.0
    if float(row["buy_price"]) > 0:
        pnl_pct = ((data["price"] - float(row["buy_price"])) / float(row["buy_price"])) * 100

    flags = []
    flag_level = "OK"

    # Pravidlo pro Core: záporné FCF narušuje tezi
    if row["type"] == "CORE" and data["fcf"] is not None and data["fcf"] < 0:
        flag_level = "RED"
        flags.append("🔴 ČERVENÁ VLAJKA: Záporné Free Cash Flow – narušení fundamentální teze stabilního přístavu.")

    # Pravidlo pro Satellite: stop-loss pod SMA 200
    if row["type"] == "SATELLITE" and data["price"] < data["sma_200"]:
        flag_level = "RED"
        flags.append(f"🔴 ČERVENÁ VLAJKA: Cena (${data['price']}) klesla pod 200denní průměr (${data['sma_200']}). Zvaž technický stop-loss.")

    # Žlutá vlajka: extrémní valuace
    if data["pe"] and data["pe"] > PORTFOLIO_RULES["extreme_pe_warning"]:
        if flag_level != "RED":
            flag_level = "YELLOW"
        flags.append(f"🟡 ŽLUTÁ VLAJKA: Extrémní valuace (P/E {data['pe']:.1f}). Zvaž vybrání části zisku do jádra.")

    # Žlutá vlajka: strmý propad od maxima
    if data["pct_from_high"] <= PORTFOLIO_RULES["falling_knife_drop_pct"]:
        if flag_level != "RED":
            flag_level = "YELLOW"
        flags.append(f"🟡 ŽLUTÁ VLAJKA: Pozice propadla o {data['pct_from_high']:.1f}% od 52týdenního maxima.")

    if not flags:
        flags.append("🟢 Pozice je v pořádku, fundament i technika se drží v mantinelech.")

    return {
        **data,
        "shares": row["shares"],
        "buy_price": row["buy_price"],
        "pos_type": row["type"],
        "pnl_pct": round(pnl_pct, 2),
        "flag_level": flag_level,
        "audit_messages": flags
    }


# --- AI ANALÝZA & KVANTITATIVNÍ FALLBACK ---

def _build_quant_fallback(stock_data: dict, note: str = "") -> str:
    """Datově podložená kvantitativní analýza pro případ nedostupnosti AI klíče."""
    upside = "Není k dispozici"
    if stock_data.get("target_price") and stock_data.get("price"):
        diff = ((stock_data["target_price"] - stock_data["price"]) / stock_data["price"]) * 100
        upside = f"{diff:+.1f}% (cílová cena Wall Street: ${stock_data['target_price']})"

    news_bullets = "\n".join([f"  - *{t}*" for t in stock_data.get("news", [])[:3]]) or "  - *Žádné čerstvé zprávy.*"
    fcf_str = f"{stock_data['fcf']:,} USD" if stock_data.get("fcf") is not None else "N/A"

    return f"""{note}
**1. Býčí teze (Tvrdá data a katalyzátory):**
* **Růst a rentabilita:** Meziroční růst tržeb dosahuje **{stock_data.get('rev_growth_pct', 0)}%**, čistá zisková marže **{stock_data.get('profit_margin_pct', 0)}%** a ROE **{stock_data.get('roe_pct', 0)}%**.
* **Konsenzus Wall Street:** Doporučení je **{stock_data.get('analyst_consensus', 'N/A')}** s očekávaným zhodnocením **{upside}**.
* **Technická kondice:** Cena (${stock_data.get('price')}) vůči SMA 50 (${stock_data.get('sma_50')}) a SMA 200 (${stock_data.get('sma_200')}). Wilderovo RSI činí **{stock_data.get('rsi')}**.

**2. Medvědí teze (Rizika z rozvahy a ocenění):**
* **Ocenění (Valuace):** Trailing P/E je **{stock_data.get('pe') or 'N/A'}** (Forward P/E: **{stock_data.get('forward_pe') or 'N/A'}**).
* **Zadlužení a FCF:** Poměr Debt/Equity činí **{stock_data.get('debt_to_equity') or 'N/A'}%**, volné cash flow: **{fcf_str}**.
* **Odchylka od maxima:** Akcie je **{stock_data.get('pct_from_high', 0)}%** od svého 52týdenního maxima.

**3. Aktuální titulky a zprávy:**
{news_bullets}
"""


def generate_ai_analysis(stock_data: dict, custom_api_key: str = "") -> str:
    """Vygeneruje strukturovaný analytický rozbor pomocí Gemini API s robustním fallbackem."""
    api_key = (custom_api_key or GEMINI_API_KEY).strip()
    news_text = "\n".join([f"- {t}" for t in stock_data.get("news", [])]) or "Žádné čerstvé titulky."
    fcf_str = f"{stock_data.get('fcf', 0):,} USD" if stock_data.get("fcf") is not None else "N/A"

    prompt = f"""Jsi nekompromisní seniorní akciový analytik. Zhodnoť akcii {stock_data.get('name', '')} ({stock_data.get('ticker')}) výhradně na základě těchto ověřených dat:
- Sektor: {stock_data.get('sector', 'N/A')}
- Cena: {stock_data.get('price')} USD ({stock_data.get('pct_from_high')}% od 52týdenního maxima)
- Trailing P/E: {stock_data.get('pe')} | Forward P/E: {stock_data.get('forward_pe')}
- Růst tržeb YoY: {stock_data.get('rev_growth_pct')}% | Čistá marže: {stock_data.get('profit_margin_pct')}% | ROE: {stock_data.get('roe_pct')}%
- Zadlužení (D/E): {stock_data.get('debt_to_equity')}% | Free Cash Flow: {fcf_str}
- Konsenzus analytiků: {stock_data.get('analyst_consensus')} (Cílová cena: {stock_data.get('target_price')} USD)
- Technika: Wilder's RSI = {stock_data.get('rsi')}, SMA 50 = {stock_data.get('sma_50')} USD, SMA 200 = {stock_data.get('sma_200')} USD
- Zařazení v radaru: Koš {stock_data.get('bucket')} ({', '.join(stock_data.get('reasons', []))})
- Poslední zprávy:
{news_text}

Napiš stručný, věcný rozbor bez marketingových klišé přesně v této struktuře:
1. **Býčí teze (3 katalyzátory):** Proč má akcie růstový potenciál.
2. **Medvědí teze (3 hlavní rizika):** Co může narušit byznys nebo srazit cenu.
3. **Verdikt a výhled:** Jedna jasná věta, na jaký klíčový ukazatel se zaměřit při nejbližších kvartálních výsledcích."""

    if not api_key:
        return _build_quant_fallback(stock_data, "ℹ️ *AI klíč nezadán – zobrazuji automatickou datovou analýzu:*\n")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response and response.text:
            return response.text
    except Exception as sdk_err:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            pass
        return _build_quant_fallback(
            stock_data,
            f"⚠️ *Poznámka: Gemini API vrátilo chybu ({sdk_err}). Zobrazuji záložní hloubkový datový rozbor:*\n"
        )
