import os
from dotenv import load_dotenv

load_dotenv()

# API Klíč pro Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Výchozí rozdělení portfolia
DEFAULT_CORE_WEIGHT = 85
DEFAULT_SATELLITE_WEIGHT = 15

# Cesty k datům a mezipaměti
DATA_DIR = "data"
CACHE_DIR = "cache"
RADAR_CACHE_FILE = os.path.join(DATA_DIR, "radar_cache.json")
FUNDAMENTALS_CACHE_FILE = os.path.join(CACHE_DIR, "fundamentals_cache.json")
PORTFOLIO_FILE = "portfolio.json"

# Expirace mezipaměti fundamentů v sekundách (24 hodin = 86400 s)
FUNDAMENTALS_CACHE_TTL = 86400

# Koš 1: CORE (Klidný přístav - S&P 500 stabilní giganti pro Watchlist)
CORE_RULES = {
    "max_debt_to_equity": 100.0,       # D/E pod 100 % (1.0) pro bezpečnou rozvahu
    "min_free_cash_flow": 0,           # Kladné volné cash flow
    "max_pe_ratio": 28.0,              # Rozumné ocenění
    "dip_min_pct": -5.0,               # Sleva alespoň 5 % od 52týdenního maxima
    "dip_max_pct": -20.0,              # Ochrana před padajícím nožem (pokles nesmí být hlubší než -20 %)
    "exempt_sectors_debt": [           # Sektory vyjmuté z obecného D/E limitu kvůli specifické rozvaze
        "Financial Services"
    ]
}

# Koš 2: SATELLITE (Akcelerátor - Růst a Momentum pro Watchlist)
SATELLITE_RULES = {
    "min_revenue_growth": 0.15,        # Meziroční růst tržeb alespoň 15 % (YoY)
    "rsi_min": 45.0,                   # Potvrzené vzestupné momentum
    "rsi_max": 70.0,                   # Ochrana před nákupem v překoupené zóně
}

# EXKLUZIVNÍ ALPHA ALERTY (Přísný nákupní filtr - smetánka trhu, cíl 0 až max 5 za den)
ALPHA_RULES = {
    "min_score": 90.0,                 # Minimální skóre pro vstup do Alpha Alertu
    "max_daily_alerts": 5,             # Zastropování TOP N nejkvalitnějších příležitostí dne
    # Core Alpha kritéria (mimořádná ziskovost a podhodnocení)
    "core_max_pe": 24.0,               # Atraktivní valuace pod 24 (ne hraničních 28)
    "core_min_roe": 15.0,              # Vysoká rentabilita vlastního kapitálu
    "core_min_margin": 12.0,           # Čistá marže alespoň 12 %
    "core_min_upside": 15.0,           # Analytický růstový potenciál alespoň +15 %
    "core_dip_sweet_spot_min": -7.0,   # Skutečná sleva (ne jen běžné zakolísání -5 %)
    # Satellite Alpha kritéria (hyper-růst a explozivní momentum)
    "sat_min_growth": 0.25,            # Růst tržeb alespoň +25 % YoY (hyper-growth)
    "sat_min_upside": 20.0,            # Analytický růstový potenciál alespoň +20 %
    "sat_rsi_min": 50.0,               # Vzestupný start momenta
    "sat_rsi_max": 65.0,               # Bezpečný odstup od překoupenosti
}

# Pravidla pro audit portfolia
PORTFOLIO_RULES = {
    "extreme_pe_warning": 45.0,        # Žlutá vlajka: Extrémní valuace
    "falling_knife_drop_pct": -25.0,   # Varování: Příliš strmý propad od maxima
}
