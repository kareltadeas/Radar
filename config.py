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

# Koš 1: CORE (Klidný přístav - S&P 500 stabilní giganti)
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

# Koš 2: SATELLITE (Akcelerátor - Růst a Momentum)
SATELLITE_RULES = {
    "min_revenue_growth": 0.15,        # Meziroční růst tržeb alespoň 15 % (YoY)
    "rsi_min": 45.0,                   # Potvrzené vzestupné momentum
    "rsi_max": 70.0,                   # Ochrana před nákupem v překoupené zóně
}

# Pravidla pro audit portfolia
PORTFOLIO_RULES = {
    "extreme_pe_warning": 45.0,        # Žlutá vlajka: Extrémní valuace
    "falling_knife_drop_pct": -25.0,   # Varování: Příliš strmý propad od maxima
}
