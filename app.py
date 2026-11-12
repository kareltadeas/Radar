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
if "selected_alpha" not in st.session_state:
    st.session_state["selected_alpha"] = None
if "selected_watch" not in st.session_state:
    st.session_state["selected_watch"] = None

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

    run_scan_btn = st.button("🔄 Spustit nový sken trhu", type="primary", use_container_width=True)

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
        st.rerun()

# --- HLAVNÍ STRÁNKA ---
st.title("📊 S&P 500 Radar & Portfolio Guard")
st.caption("Disciplinovaný ranní analytický systém: žádné nucené obchody, přísné filtry a ochrana před padajícím nožem.")

# Metriky v záhlaví
if cache_data and "summary" in cache_data:
    s = cache_data["summary"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Analyzováno akcií", f"{s.get('successfully_scanned', 0)} / {s.get('total_universe', 0)}")

    breadth = s.get("stocks_above_sma200_pct", 0)
    breadth_delta = "Býčí trh" if breadth >= 60 else ("Neutrální" if breadth >= 45 else "Medvědí trh")
    m2.metric("Tržní šíře (> SMA 200)", f"{breadth}%", breadth_delta)

    m3.metric("🚨 Alpha Alerty (TOP)", s.get("alpha_alerts_count", 0))
    m4.metric("🛡️ Core Watchlist", s.get("core_watchlist_count", 0))
    m5.metric("🚀 Satellite Watchlist", s.get("satellite_watchlist_count", 0))
    st.divider()

tab_radar, tab_portfolio = st.tabs(["🎯 Ranní Radar (Nákupní příležitosti)", "🛡️ Hlídač mého portfolia"])


def add_ticker_to_portfolio(ticker: str, price: float, pos_type: str):
    """Pomocná funkce pro rychlé přidání vybrané akcie do portfolia."""
    df = load_portfolio()
    if ticker in df["ticker"].values:
        st.toast(f"Akcie {ticker} již v portfoliu existuje!", icon="ℹ️")
        return
    new_row = pd.DataFrame([{
        "ticker": ticker,
        "shares": 1.0,
        "buy_price": price,
        "type": pos_type
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_portfolio(df)
    st.toast(f"✅ Akcie {ticker} byla přidána do portfolia!", icon="🎉")


def render_detail_card(item: dict, prefix: str):
    """Zobrazí velkou, přehlednou detailní kartu pro vybranou akcii."""
    ticker = item["ticker"]
    score = item.get("score", 0)
    bucket = item.get("bucket", "CORE")

    st.markdown(f"### ⭐ Detail akcie: **{ticker}** – {item.get('name', '')} ({bucket})")

    # Řádek klíčových metrik
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Aktuální cena", f"${item.get('price')}", f"{item.get('pct_from_high')}% od 52w max")
    c2.metric("P/E (Forward)", f"{item.get('pe') or 'N/A'} ({item.get('forward_pe') or 'N/A'})")
    c3.metric("Wall St Cíl / Upside", f"${item.get('target_price') or 'N/A'}", f"+{item.get('upside_pct', 0)}%")
    c4.metric("Růst tržeb YoY", f"{item.get('rev_growth_pct')}%")
    c5.metric("Rentabilita (ROE / Marže)", f"{item.get('roe_pct')}% / {item.get('profit_margin_pct')}%")

    col_signals, col_actions = st.columns([2, 1])

    with col_signals:
        st.markdown("**🔍 Proč systém akcii vybral (Katalyzátory a signály):**")
        for reason in item.get("reasons", []):
            st.markdown(f"- ✅ {reason}")

    with col_actions:
        st.markdown("**⚡ Rychlé akce:**")
        if st.button(f"➕ Přidat {ticker} do mého portfolia", key=f"btn_add_{prefix}_{ticker}", use_container_width=True):
            add_ticker_to_portfolio(ticker, float(item.get("price", 0)), bucket)

        cache_key = ticker
        has_ai = cache_key in st.session_state["ai_cache"]
        btn_label = f"🔄 Přegenerovat AI rozbor ({ticker})" if has_ai else f"🧠 Vygenerovat AI analýzu ({ticker})"
        if st.button(btn_label, key=f"btn_ai_{prefix}_{ticker}", use_container_width=True):
            with st.spinner(f"Generuji rozbor rizik a katalyzátorů pro {ticker}..."):
                st.session_state["ai_cache"][cache_key] = generate_ai_analysis(item, api_key_input)
                st.rerun()

    # Zobrazení AI rozboru
    cache_key = ticker
    if cache_key in st.session_state["ai_cache"]:
        st.markdown("#### 🧠 Hloubkový rozbor (Býčí / Medvědí teze & Výhled):")
        st.info(st.session_state["ai_cache"][cache_key])


# =========================================================
# ZÁLOŽKA 1: RANNÍ RADAR
# =========================================================
with tab_radar:
    if not cache_data:
        st.warning("⚠️ Mezipaměť ranního skenu je prázdná. V levém panelu klikni na **Spustit nový sken trhu**.")
    else:
        alpha_picks = cache_data.get("alpha_alerts", [])
        core_watch = cache_data.get("core_watchlist", [])
        sat_watch = cache_data.get("satellite_watchlist", [])

        # --- SEKCE 1: ALPHA ALERT BANNER & LEADERBOARD ---
        if alpha_picks:
            st.error(f"🚨 **ALPHA ALERT: Nalezeno {len(alpha_picks)} mimořádných titulů (Přísná TOP selekce trhu)**")
            st.caption("Tyto akcie splňují nejpřísnější kritéria: ziskovost, rozumné ocenění, potvrzený trend a výrazný růstový potenciál Wall Street.")

            # Ovládací prvky pro řazení
            col_sort, col_info = st.columns([2, 3])
            with col_sort:
                sort_alpha_by = st.selectbox(
                    "Seřadit Alpha Alerty podle:",
                    options=["score", "upside", "dip", "pe", "growth"],
                    format_func=lambda x: {
                        "score": "⭐ Nejvyšší skóre (Doporučeno)",
                        "upside": "📈 Největší Wall Street Upside (%)",
                        "dip": "🏷️ Největší sleva od maxima (%)",
                        "pe": "💰 Nejnižší P/E (Nejlevnější)",
                        "growth": "🚀 Nejvyšší růst tržeb YoY (%)"
                    }[x],
                    key="sort_alpha_select"
                )

            # Aplikace řazení
            sorted_alphas = list(alpha_picks)
            if sort_alpha_by == "score":
                sorted_alphas.sort(key=lambda x: (x.get("score", 0), x.get("upside_pct", 0)), reverse=True)
            elif sort_alpha_by == "upside":
                sorted_alphas.sort(key=lambda x: x.get("upside_pct", 0), reverse=True)
            elif sort_alpha_by == "dip":
                sorted_alphas.sort(key=lambda x: abs(x.get("pct_from_high", 0)), reverse=True)
            elif sort_alpha_by == "pe":
                sorted_alphas.sort(key=lambda x: (x.get("pe") if x.get("pe") is not None else 999))
            elif sort_alpha_by == "growth":
                sorted_alphas.sort(key=lambda x: x.get("rev_growth_pct", 0), reverse=True)

            # Kompaktní Leaderboard tabulka
            table_rows = []
            for item in sorted_alphas:
                table_rows.append({
                    "Ticker": item["ticker"],
                    "Firma": item.get("name", item["ticker"]),
                    "Koš": item.get("bucket"),
                    "Cena ($)": f"${item.get('price'):.2f}",
                    "Sleva z max": f"{item.get('pct_from_high'):.1f}%",
                    "P/E": f"{item.get('pe'):.1f}" if item.get('pe') else "N/A",
                    "Růst tržeb": f"{item.get('rev_growth_pct'):.1f}%",
                    "Wall St Upside": f"+{item.get('upside_pct', 0):.1f}%",
                    "Skóre": f"{item.get('score')}/100"
                })
            df_alpha = pd.DataFrame(table_rows)

            st.dataframe(df_alpha, use_container_width=True, hide_index=True)

            # Master-Detail výběr akcie k prokliku
            alpha_tickers = [item["ticker"] for item in sorted_alphas]
            if st.session_state["selected_alpha"] not in alpha_tickers:
                st.session_state["selected_alpha"] = alpha_tickers[0]

            st.markdown("#### 🔍 Klikni pro detailní analytický rozbor akcie:")
            selected_alpha_ticker = st.pills(
                "Vyber titul pro detailní zobrazení:",
                options=alpha_tickers,
                default=st.session_state["selected_alpha"],
                key="pill_alpha_ticker"
            )
            st.session_state["selected_alpha"] = selected_alpha_ticker or alpha_tickers[0]

            # Vykreslení vybrané detailní karty
            chosen_alpha_item = next((it for it in sorted_alphas if it["ticker"] == st.session_state["selected_alpha"]), sorted_alphas[0])
            with st.container(border=True):
                render_detail_card(chosen_alpha_item, prefix="alpha")

        else:
            st.success("💤 **Dnes žádná akcie nesplňuje přísná kritéria pro okamžitý Alpha Alert.** Žádné nucené obchody – držíme disciplínu a čekáme na správný moment.")

        st.divider()

        # --- SEKCE 2: WATCHLISTY (CORE & SATELLITE) ---
        st.subheader("📋 Sledovací seznamy (Watchlist)")
        st.caption("Kvalitní a růstové tituly splňující stabilitu, které čekají na vhodný nákupní impuls či slevu.")

        watch_tab_core, watch_tab_sat = st.tabs([
            f"🛡️ Koš 1: Klidný přístav – Core ({len(core_watch)})",
            f"🚀 Koš 2: Akcelerátor – Satellite ({len(sat_watch)})"
        ])

        with watch_tab_core:
            if not core_watch:
                st.info("Žádné akcie v Core Watchlistu.")
            else:
                # Možnost řazení a vyhledávání
                c_sort, c_search = st.columns([1, 2])
                with c_sort:
                    sort_core = st.selectbox(
                        "Řadit Core podle:",
                        ["Skóre", "Sleva od maxima", "Wall St Upside", "P/E"],
                        key="sort_core_select"
                    )
                with c_search:
                    search_core = st.text_input("Hledat ticker nebo firmu v Core:", "", key="search_core_input")

                sorted_core = list(core_watch)
                if sort_core == "Skóre":
                    sorted_core.sort(key=lambda x: (x.get("score", 0), x.get("upside_pct", 0)), reverse=True)
                elif sort_core == "Sleva od maxima":
                    sorted_core.sort(key=lambda x: abs(x.get("pct_from_high", 0)), reverse=True)
                elif sort_core == "Wall St Upside":
                    sorted_core.sort(key=lambda x: x.get("upside_pct", 0), reverse=True)
                elif sort_core == "P/E":
                    sorted_core.sort(key=lambda x: (x.get("pe") if x.get("pe") is not None else 999))

                if search_core:
                    sorted_core = [x for x in sorted_core if search_core.upper() in x["ticker"].upper() or search_core.lower() in x.get("name", "").lower()]

                core_rows = []
                for x in sorted_core[:30]:
                    core_rows.append({
                        "Ticker": x["ticker"],
                        "Firma": x.get("name", x["ticker"]),
                        "Cena ($)": f"${x.get('price'):.2f}",
                        "Sleva z max": f"{x.get('pct_from_high'):.1f}%",
                        "P/E": f"{x.get('pe'):.1f}" if x.get('pe') else "N/A",
                        "D/E (%)": f"{x.get('debt_to_equity') or 0:.0f}%",
                        "Wall St Upside": f"+{x.get('upside_pct', 0):.1f}%",
                        "Skóre": f"{x.get('score')}/100"
                    })
                st.dataframe(pd.DataFrame(core_rows), use_container_width=True, hide_index=True)

                # Detail proklik pro Core
                core_tickers = [x["ticker"] for x in sorted_core[:30]]
                if core_tickers:
                    sel_core = st.selectbox("Vyber akcii z Core k rozboru:", options=core_tickers, key="sel_core_box")
                    core_item = next((x for x in sorted_core if x["ticker"] == sel_core), sorted_core[0])
                    with st.expander(f"🔍 Detail akcie {sel_core}", expanded=True):
                        render_detail_card(core_item, prefix="core_watch")

        with watch_tab_sat:
            if not sat_watch:
                st.info("Žádné akcie v Satellite Watchlistu.")
            else:
                c_sort_sat, c_search_sat = st.columns([1, 2])
                with c_sort_sat:
                    sort_sat = st.selectbox(
                        "Řadit Satellite podle:",
                        ["Růst tržeb YoY", "Skóre", "Wall St Upside", "RSI"],
                        key="sort_sat_select"
                    )
                with c_search_sat:
                    search_sat = st.text_input("Hledat ticker nebo firmu v Satellite:", "", key="search_sat_input")

                sorted_sat = list(sat_watch)
                if sort_sat == "Růst tržeb YoY":
                    sorted_sat.sort(key=lambda x: x.get("rev_growth_pct", 0), reverse=True)
                elif sort_sat == "Skóre":
                    sorted_sat.sort(key=lambda x: (x.get("score", 0), x.get("upside_pct", 0)), reverse=True)
                elif sort_sat == "Wall St Upside":
                    sorted_sat.sort(key=lambda x: x.get("upside_pct", 0), reverse=True)
                elif sort_sat == "RSI":
                    sorted_sat.sort(key=lambda x: x.get("rsi", 50))

                if search_sat:
                    sorted_sat = [x for x in sorted_sat if search_sat.upper() in x["ticker"].upper() or search_sat.lower() in x.get("name", "").lower()]

                sat_rows = []
                for x in sorted_sat[:30]:
                    sat_rows.append({
                        "Ticker": x["ticker"],
                        "Firma": x.get("name", x["ticker"]),
                        "Cena ($)": f"${x.get('price'):.2f}",
                        "Růst tržeb": f"+{x.get('rev_growth_pct'):.1f}%",
                        "RSI (14)": f"{x.get('rsi'):.1f}",
                        "Wall St Upside": f"+{x.get('upside_pct', 0):.1f}%",
                        "Skóre": f"{x.get('score')}/100"
                    })
                st.dataframe(pd.DataFrame(sat_rows), use_container_width=True, hide_index=True)

                # Detail proklik pro Satellite
                sat_tickers = [x["ticker"] for x in sorted_sat[:30]]
                if sat_tickers:
                    sel_sat = st.selectbox("Vyber akcii ze Satellite k rozboru:", options=sat_tickers, key="sel_sat_box")
                    sat_item = next((x for x in sorted_sat if x["ticker"] == sel_sat), sorted_sat[0])
                    with st.expander(f"🔍 Detail akcie {sel_sat}", expanded=True):
                        render_detail_card(sat_item, prefix="sat_watch")


# =========================================================
# ZÁLOŽKA 2: HLÍDAČ MÉHO PORTFOLIA
# =========================================================
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

    show_audit = col_audit.button("🔍 Zkontrolovat zdraví portfolia", type="primary", use_container_width=True)

    # Zobrazení auditu: buď z ranní cache, nebo čerstvě při kliknutí
    audits_to_show = []
    if show_audit:
        save_portfolio(edited_df)
        with st.spinner("Provádím čerstvý audit pozic..."):
            for _, row in edited_df.iterrows():
                if not row.get("ticker"):
                    continue
                audits_to_show.append(audit_portfolio_position(row.to_dict()))
    elif cache_data and cache_data.get("portfolio_audits"):
        audits_to_show = cache_data["portfolio_audits"]

    if audits_to_show:
        st.markdown("### Výsledky auditu pozic:")
        for audit in audits_to_show:
            ticker = audit.get("ticker", "N/A")
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
