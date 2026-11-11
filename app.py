import json
import os
import streamlit as st
import pandas as pd
from config import (
    DEFAULT_CORE_WEIGHT,
    GEMINI_API_KEY,
    RADAR_CACHE_FILE
)
from data_engine import (
    evaluate_stock,
    audit_portfolio_position,
    generate_ai_analysis,
    load_portfolio,
    save_portfolio
)
import scanner

st.set_page_config(page_title="S&P 500 Radar & Portfolio Guard", layout="wide", page_icon="📊")

# Inicializace stavů v session_state
if "ai_cache" not in st.session_state:
    st.session_state["ai_cache"] = {}

def load_radar_cache():
    if os.path.exists(RADAR_CACHE_FILE):
        try:
            with open(RADAR_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

cache_data = load_radar_cache()
if cache_data and "ai_analyses" in cache_data:
    st.session_state["ai_cache"].update(cache_data["ai_analyses"])

# --- BOČNÍ PANEL ---
with st.sidebar:
    st.header("⚙️ Nastavení & Režim skenu")
    core_weight = st.slider("Cílový poměr Jádro (Core) vs. Satelit (%)", 50, 100, DEFAULT_CORE_WEIGHT, 5)
    st.write(f"**Jádro (Stabilita):** {core_weight} % | **Satelit (Růst):** {100 - core_weight} %")
    st.divider()

    scan_mode_choice = st.selectbox(
        "Rozsah skenovaného trhu",
        options=["sp500", "full", "quick"],
        format_func=lambda x: {
            "sp500": "🏛️ S&P 500 (503 velkých firem)",
            "full": "🌐 S&P 500 + MidCap 400 (903 firem)",
            "quick": "⚡ Rychlý vzorek (30 reprezentativních gigantů)"
        }[x]
    )

    api_key_input = st.text_input(
        "🔑 Gemini API Klíč",
        value=GEMINI_API_KEY,
        type="password",
        help="Načítá se automaticky z .env, nebo ho vlož sem pro AI rozbor."
    )
    st.divider()

    run_scan_btn = st.button("🔄 Spustit sken trhu hned", type="primary", use_container_width=True)

    if cache_data:
        st.caption(f"🕒 Poslední ranní sken: **{cache_data.get('timestamp', 'N/A')}**")
        st.caption(f"⏱️ Doba běhu skriptu: {cache_data.get('elapsed_seconds', 0)} s")

# Zpracování manuálního spuštění skenu
if run_scan_btn:
    with st.spinner(f"Spouštím sken trhu v režimu {scan_mode_choice.upper()} přes dvoustupňový trychtýř..."):
        cache_data = scanner.run_scanner(
            mode=scan_mode_choice,
            force_refresh=False,
            generate_ai_for_alpha=bool(api_key_input)
        )
        if cache_data and "ai_analyses" in cache_data:
            st.session_state["ai_cache"].update(cache_data["ai_analyses"])
        st.success("Sken byl úspěšně dokončen a mezipaměť aktualizována!")

# --- HLAVNÍ STRÁNKA ---
st.title("📊 S&P 500 Radar & Portfolio Guard")
st.caption("Disciplinovaný ranní analytický systém: žádné nucené obchody, přísné filtry a ochrana před padajícím nožem.")

# Metriky v záhlaví
if cache_data and "summary" in cache_data:
    s = cache_data["summary"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Analyzováno akcií", f"{s.get('successfully_scanned', 0)} / {s.get('total_universe', 0)}")

    breadth = s.get("stocks_above_sma200_pct", 0)
    breadth_delta = "Býčí trend" if breadth >= 60 else ("Neutrální" if breadth >= 45 else "Medvědí trend")
    m2.metric("Tržní šíře (> SMA 200)", f"{breadth}%", breadth_delta)

    m3.metric("🚨 Alpha Alerty", s.get("alpha_alerts_count", 0))
    m4.metric("🛡️ Core Watchlist", s.get("core_watchlist_count", 0))
    m5.metric("🚀 Satellite Watchlist", s.get("satellite_watchlist_count", 0))
    st.divider()

tab_radar, tab_portfolio = st.tabs(["🎯 Ranní Radar (Nákupní příležitosti)", "🛡️ Hlídač mého portfolia"])

def render_stock_card(item: dict, prefix: str, expanded: bool = False):
    """Vykreslí detailní kartu akcie včetně AI analýzy."""
    score = item.get("score", 0)
    ticker = item["ticker"]
    header = f"{'⭐ ' if prefix=='alpha' else ''}{ticker} – {item.get('name', '')} | Cena: ${item.get('price')} | Skóre: {score}/100"

    with st.expander(header, expanded=expanded):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Cena", f"${item.get('price')}", f"{item.get('pct_from_high')}% od 52w max")
        c2.metric("Trailing / Fwd P/E", f"{item.get('pe') or 'N/A'} / {item.get('forward_pe') or 'N/A'}")
        c3.metric("Růst tržeb YoY", f"{item.get('rev_growth_pct')}%")
        c4.metric("Čistá marže / ROE", f"{item.get('profit_margin_pct')}% / {item.get('roe_pct')}%")
        c5.metric("Wilder's RSI (14)", item.get("rsi"))

        st.markdown("**Splněná kritéria a signály:**")
        for reason in item.get("reasons", []):
            st.markdown(f"- ✅ {reason}")

        cache_key = ticker
        col_btn, _ = st.columns([1, 2])
        if col_btn.button(f"🧠 Zobrazit / Vygenerovat AI analýzu ({ticker})", key=f"btn_{prefix}_{ticker}"):
            with st.spinner(f"Analyzuji data a zprávy pro {ticker}..."):
                st.session_state["ai_cache"][cache_key] = generate_ai_analysis(item, api_key_input)

        if cache_key in st.session_state["ai_cache"]:
            st.info(st.session_state["ai_cache"][cache_key])

# --- ZÁLOŽKA 1: RANNÍ RADAR ---
with tab_radar:
    if not cache_data:
        st.warning("⚠️ Mezipaměť ranního skenu je zatím prázdná. Klikni v levém panelu na **Spustit sken trhu hned**.")
    else:
        alpha_picks = cache_data.get("alpha_alerts", [])
        core_watch = cache_data.get("core_watchlist", [])
        sat_watch = cache_data.get("satellite_watchlist", [])

        if alpha_picks:
            st.error(f"🚨 **ALPHA ALERT: Nalezeno {len(alpha_picks)} titulů s mimořádnou shodou fundamentu, techniky a katalyzátoru!**")
            # Zobrazit prvních 10 nejvýše hodnocených rozbalených
            for pick in alpha_picks[:10]:
                render_stock_card(pick, "alpha", expanded=True)
            if len(alpha_picks) > 10:
                with st.expander(f"➕ Zobrazit dalších {len(alpha_picks)-10} Alpha Alertů"):
                    for pick in alpha_picks[10:]:
                        render_stock_card(pick, "alpha", expanded=False)
        else:
            st.success("💤 **Dnes žádná akcie nesplňuje přísná kritéria pro okamžitý Alpha Alert.** Žádné nucené obchody – držíme disciplínu a čekáme na správný moment.")

        st.divider()
        col_core, col_sat = st.columns(2)

        with col_core:
            st.subheader(f"🛡️ Koš 1: Klidný přístav (Watchlist: {len(core_watch)})")
            st.caption("Stabilní firmy s nízkým dluhem a kladným FCF čekající na zdravou slevu.")
            if not core_watch:
                st.write("*Žádné akcie v této sekci.*")
            for item in core_watch[:25]:
                render_stock_card(item, "core", expanded=False)

        with col_sat:
            st.subheader(f"🚀 Koš 2: Akcelerátor (Watchlist: {len(sat_watch)})")
            st.caption("Růstové tituly v potvrzeném uptrendu nad SMA 50 i SMA 200 se zdravým RSI.")
            if not sat_watch:
                st.write("*Žádné akcie v této sekci.*")
            for item in sat_watch[:25]:
                render_stock_card(item, "sat", expanded=False)

# --- ZÁLOŽKA 2: HLÍDAČ MÉHO PORTFOLIA ---
with tab_portfolio:
    st.subheader("Moje držené pozice (Ukládají se do portfolio.json)")
    st.caption("Uprav počty kusů, nákupní cenu nebo přidej nové akcie. Systém zkontroluje fundament i stop-lossy.")

    portfolio_df = load_portfolio()
    edited_df = st.data_editor(
        portfolio_df,
        num_rows="dynamic",
        column_config={
            "ticker": "Ticker",
            "shares": "Počet kusů",
            "buy_price": "Nákupní cena ($)",
            "type": st.column_config.SelectboxColumn("Koš", options=["CORE", "SATELLITE"], required=True)
        },
        use_container_width=True
    )

    col_save, col_audit = st.columns([1, 2])
    if col_save.button("💾 Uložit změny v portfoliu", use_container_width=True):
        save_portfolio(edited_df)
        st.toast("Portfolio uloženo do portfolio.json!", icon="✅")

    # Pokud máme v cache ranní audit, můžeme ho rovnou zobrazit
    show_audit = col_audit.button("🔍 Zkontrolovat zdraví portfolia", type="primary", use_container_width=True)

    if show_audit or (cache_data and "portfolio_audits" in cache_data):
        save_portfolio(edited_df)
        st.markdown("### Výsledky auditu pozic:")

        # Pokud uživatel kliknul na audit hned po editaci, zvalidujeme živě
        for _, row in edited_df.iterrows():
            if not row.get("ticker"):
                continue
            ticker = str(row["ticker"]).strip().upper()
            with st.spinner(f"Audituji {ticker}..."):
                audit = audit_portfolio_position(row.to_dict())
                flag = audit.get("flag_level", "OK")
                icon = "🟢" if flag == "OK" else ("🟡" if flag == "YELLOW" else "🔴")
                pnl = audit.get("pnl_pct", 0.0)
                pnl_color = "green" if pnl >= 0 else "red"

                with st.expander(
                    f"{icon} **{ticker}** ({audit.get('pos_type', '')}) | Cena: ${audit.get('price', 'N/A')} | Výnos: :{pnl_color}[{pnl:+.1f} %]",
                    expanded=(flag != "OK")
                ):
                    for msg in audit.get("audit_messages", []):
                        st.write(f"- {msg}")
                    st.caption(f"Fundament: P/E: {audit.get('pe') or 'N/A'} | D/E: {audit.get('debt_to_equity') or 'N/A'}% | RSI: {audit.get('rsi')} | SMA 200: ${audit.get('sma_200')}")
