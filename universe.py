import io
import json
import os
import time
import requests
import pandas as pd
from config import DATA_DIR

SP500_FILE = os.path.join(DATA_DIR, "universe_sp500.json")
MIDCAP400_FILE = os.path.join(DATA_DIR, "universe_midcap400.json")
UNIVERSE_TTL = 7 * 86400  # 7 dní (složení indexů se mění pomalu)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Záložní repre-vzorek pro případ kompletního výpadku sítě a prázdné cache
FALLBACK_UNIVERSE = [
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Communication Services", "index": "SP500"},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "index": "SP500"},
    {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Communication Services", "index": "SP500"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financial Services", "index": "SP500"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "index": "SP500"},
    {"ticker": "V", "name": "Visa Inc.", "sector": "Financial Services", "index": "SP500"},
    {"ticker": "PG", "name": "Procter & Gamble", "sector": "Consumer Staples", "index": "SP500"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financial Services", "index": "SP500"},
    {"ticker": "UNH", "name": "UnitedHealth Group", "sector": "Healthcare", "index": "SP500"},
    {"ticker": "HD", "name": "Home Depot", "sector": "Consumer Discretionary", "index": "SP500"},
    {"ticker": "MA", "name": "Mastercard Inc.", "sector": "Financial Services", "index": "SP500"},
    {"ticker": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare", "index": "SP500"},
    {"ticker": "KO", "name": "Coca-Cola Co.", "sector": "Consumer Staples", "index": "SP500"},
    {"ticker": "PEP", "name": "PepsiCo Inc.", "sector": "Consumer Staples", "index": "SP500"},
    {"ticker": "COST", "name": "Costco Wholesale", "sector": "Consumer Staples", "index": "SP500"},
    {"ticker": "MRK", "name": "Merck & Co.", "sector": "Healthcare", "index": "SP500"},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "LLY", "name": "Eli Lilly and Co.", "sector": "Healthcare", "index": "SP500"},
    {"ticker": "PLTR", "name": "Palantir Technologies", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "CRWD", "name": "CrowdStrike Holdings", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "ANET", "name": "Arista Networks", "sector": "Information Technology", "index": "SP500"},
    {"ticker": "DECK", "name": "Deckers Outdoor", "sector": "Consumer Discretionary", "index": "SP500"},
    {"ticker": "AXON", "name": "Axon Enterprise", "sector": "Industrials", "index": "SP500"},
    {"ticker": "URI", "name": "United Rentals", "sector": "Industrials", "index": "SP500"},
    {"ticker": "GWW", "name": "W.W. Grainger", "sector": "Industrials", "index": "SP500"},
    {"ticker": "CAT", "name": "Caterpillar Inc.", "sector": "Industrials", "index": "SP500"}
]


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _load_cached_json(path: str) -> list[dict] | None:
    if os.path.exists(path):
        try:
            mtime = os.path.getmtime(path)
            if (time.time() - mtime) < UNIVERSE_TTL:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None


def fetch_sp500_tickers(force_refresh: bool = False) -> list[dict]:
    """Stáhne a normalizuje seznam tickerů S&P 500 z Wikipedie."""
    if not force_refresh:
        cached = _load_cached_json(SP500_FILE)
        if cached:
            return cached

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        df = pd.read_html(io.StringIO(r.text))[0]

        # Normalizace symbolů pro Yahoo Finance (např. BRK.B -> BRK-B)
        sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        name_col = "Security" if "Security" in df.columns else "Company"
        sec_col = "GICS Sector" if "GICS Sector" in df.columns else "Sector"

        tickers = []
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip().replace(".", "-")
            name = str(row.get(name_col, sym)).strip()
            sector = str(row.get(sec_col, "Unknown")).strip()
            tickers.append({
                "ticker": sym,
                "name": name,
                "sector": sector,
                "index": "SP500"
            })

        _ensure_dir(SP500_FILE)
        with open(SP500_FILE, "w", encoding="utf-8") as f:
            json.dump(tickers, f, indent=2, ensure_ascii=False)
        return tickers
    except Exception as e:
        print(f"⚠️ Varování: Nelze stáhnout S&P 500 z Wikipedie ({e}). Používám záložní data.")
        if os.path.exists(SP500_FILE):
            try:
                with open(SP500_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return [t for t in FALLBACK_UNIVERSE if t.get("index") == "SP500"]


def fetch_midcap400_tickers(force_refresh: bool = False) -> list[dict]:
    """Stáhne a normalizuje seznam tickerů S&P MidCap 400 z Wikipedie."""
    if not force_refresh:
        cached = _load_cached_json(MIDCAP400_FILE)
        if cached:
            return cached

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        df = pd.read_html(io.StringIO(r.text))[0]

        sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        name_col = "Security" if "Security" in df.columns else "Company"
        sec_col = "GICS Sector" if "GICS Sector" in df.columns else "Sector"

        tickers = []
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip().replace(".", "-")
            name = str(row.get(name_col, sym)).strip()
            sector = str(row.get(sec_col, "Unknown")).strip()
            tickers.append({
                "ticker": sym,
                "name": name,
                "sector": sector,
                "index": "MIDCAP400"
            })

        _ensure_dir(MIDCAP400_FILE)
        with open(MIDCAP400_FILE, "w", encoding="utf-8") as f:
            json.dump(tickers, f, indent=2, ensure_ascii=False)
        return tickers
    except Exception as e:
        print(f"⚠️ Varování: Nelze stáhnout S&P MidCap 400 z Wikipedie ({e}).")
        if os.path.exists(MIDCAP400_FILE):
            try:
                with open(MIDCAP400_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []


def get_universe(include_sp500: bool = True, include_midcap: bool = True, force_refresh: bool = False) -> list[dict]:
    """Vrátí kombinovaný investiční vesmír s deduplikovanými tickery."""
    all_tickers = []
    seen = set()

    if include_sp500:
        for t in fetch_sp500_tickers(force_refresh=force_refresh):
            if t["ticker"] not in seen:
                seen.add(t["ticker"])
                all_tickers.append(t)

    if include_midcap:
        for t in fetch_midcap400_tickers(force_refresh=force_refresh):
            if t["ticker"] not in seen:
                seen.add(t["ticker"])
                all_tickers.append(t)

    return all_tickers
