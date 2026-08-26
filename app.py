"""
Momentum First-Leg Breakout Screener -- Streamlit Dashboard.

Run with:  streamlit run app.py

Layout:
  Sidebar   -> Universe + all configurable parameters (spec section 29), data provider selection, SCAN button
  Tab 1     -> Scanner: results table (section 22), click a row for Stock Detail (23) + Chart (24) + WHY (25)
  Tab 2     -> A+ Setups summary (section 33)
  Tab 3     -> Watchlist (READY): results whose Status is READY (approaching Resistance, not broken out
               yet) regardless of grade -- a heads-up before the breakout, separate from the A+/A grade
               list since a pre-breakout stock can't score high enough on breakout_quality to reach A yet
  Tab 4     -> Methodology (section 30) -- the exact formulas/thresholds currently configured

The last scan (from this dashboard's own SCAN button, or from the local scheduled daily_scan.py run)
is cached to disk via scan_cache.py, so reopening the dashboard in a new tab/session shows that last
scan instead of an empty screen -- see main()'s startup block below.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import notify
import scan_cache
from config import ScreenerConfig
from data import universe as universe_mod
from scanner import scan_universe
from trading_calculator_tab import render_trading_calculator

st.set_page_config(page_title="Momentum First-Leg Screener", layout="wide")

STATUS_COLOR = {
    "BREAKOUT": "#16a34a",
    "READY": "#2563eb",
    "WATCH": "#a16207",
    "EXTENDED": "#ea580c",
    "REJECTED": "#6b7280",
}
GRADE_ORDER = {"A+": 0, "A": 1, "B": 2, "C": 3, "REJECT": 4}


# ---------------------------------------------------------------------------
# Sidebar -- configuration (spec section 29: nothing here is hard-coded)
# ---------------------------------------------------------------------------

def build_sidebar_config() -> ScreenerConfig:
    st.sidebar.title("⚙️ Configuration")

    cfg = ScreenerConfig()

    with st.sidebar.expander("Data Provider", expanded=True):
        cfg.data_provider = st.selectbox("Provider", ["yfinance", "eodhd"], index=0,
                                          help="yfinance = free/unofficial, good for prototyping. "
                                               "eodhd = paid, higher reliability, needs an API key.")
        if cfg.data_provider == "eodhd":
            cfg.eodhd_api_key = st.text_input("EODHD API key", type="password")

    with st.sidebar.expander("Universe (section 2)", expanded=True):
        cfg.min_price = st.number_input("MIN_PRICE ($)", value=cfg.min_price, step=1.0)
        cfg.min_market_cap = st.number_input("MIN_MARKET_CAP ($)", value=float(cfg.min_market_cap), step=50_000_000.0, format="%.0f")
        cfg.min_avg_volume = st.number_input("MIN_AVG_VOLUME", value=float(cfg.min_avg_volume), step=50_000.0, format="%.0f")

    with st.sidebar.expander("EMA Structure (section 5)"):
        cfg.ema_fast = st.number_input("EMA_FAST", value=cfg.ema_fast, min_value=2, max_value=50)
        cfg.ema_mid = st.number_input("EMA_MID", value=cfg.ema_mid, min_value=5, max_value=100)
        cfg.ema_slow = st.number_input("EMA_SLOW", value=cfg.ema_slow, min_value=10, max_value=200)
        cfg.weekly_ema_fast = st.number_input("WEEKLY_EMA_FAST", value=cfg.weekly_ema_fast, min_value=2, max_value=30)
        cfg.weekly_ema_slow = st.number_input("WEEKLY_EMA_SLOW", value=cfg.weekly_ema_slow, min_value=2, max_value=30)

    with st.sidebar.expander("Consolidation (sections 7-10)"):
        cfg.min_consolidation_days = st.number_input("MIN_CONSOLIDATION_DAYS", value=cfg.min_consolidation_days, min_value=3, max_value=60)
        cfg.ema_pullback_tolerance_pct = st.slider("EMA pullback tolerance %", 0.0, 5.0, cfg.ema_pullback_tolerance_pct * 100, 0.25) / 100
        cfg.ema20_close_violation_pct = st.slider("EMA20 'meaningful close' tolerance %", 0.0, 5.0, cfg.ema20_close_violation_pct * 100, 0.25) / 100
        cfg.ema20_max_violation_days = st.number_input("Max tolerated EMA20 violations (days)", value=cfg.ema20_max_violation_days, min_value=0, max_value=10)
        cfg.higher_low_min_gap_pct = st.slider("Higher Low min gap %", 0.0, 5.0, cfg.higher_low_min_gap_pct * 100, 0.25) / 100

    with st.sidebar.expander("Breakout (section 14)"):
        cfg.max_breakout_atr = st.slider("MAX_BREAKOUT_ATR", 0.5, 6.0, cfg.max_breakout_atr, 0.1)
        cfg.clv_threshold = st.slider("CLV_THRESHOLD", 0.0, 1.0, cfg.clv_threshold, 0.01)
        cfg.upper_wick_max_pct = st.slider("Max upper wick %", 0.0, 1.0, cfg.upper_wick_max_pct, 0.05)

    with st.sidebar.expander("Entry / Stop (sections 17-19)"):
        cfg.entry_buffer_pct = st.slider("ENTRY_BUFFER %", 0.0, 2.0, cfg.entry_buffer_pct * 100, 0.05) / 100
        cfg.max_extension_atr = st.slider("Max extension (ATR) before EXTENDED", 0.2, 5.0, cfg.max_extension_atr, 0.1)
        cfg.atr_stop_multiplier = st.slider("ATR_STOP_MULTIPLIER", 0.0, 2.0, cfg.atr_stop_multiplier, 0.1)
        cfg.max_stop_percent = st.slider("MAX_STOP_PERCENT", 1.0, 25.0, cfg.max_stop_percent, 0.5)

    with st.sidebar.expander("Setup Score weights (section 20)"):
        st.caption("Must relatively sum to 100 -- normalized automatically if they don't.")
        for key in list(cfg.setup_score_weights.keys()):
            cfg.setup_score_weights[key] = st.number_input(
                key, value=cfg.setup_score_weights[key], min_value=0, max_value=100, key=f"ssw_{key}")

    with st.sidebar.expander("Data history"):
        cfg.daily_history_years = st.number_input("Daily history (years)", value=cfg.daily_history_years, min_value=1, max_value=10)

    with st.sidebar.expander("Email alerts"):
        cfg.enable_email_alerts = st.checkbox("Email me after SCAN if a matching grade is found",
                                               value=cfg.enable_email_alerts)
        cfg.email_alert_grades = st.multiselect("Alert on grades", ["A+", "A", "B", "C"],
                                                 default=cfg.email_alert_grades)
        if cfg.enable_email_alerts:
            try:
                _recipient = st.secrets["email"]["recipient_address"]
                _has_secrets = bool(st.secrets["email"]["sender_address"]) and \
                    bool(st.secrets["email"]["app_password"]) and bool(_recipient)
            except Exception:
                _has_secrets = False
                _recipient = None
            if _has_secrets:
                st.caption(f"✓ Email secrets configured -- alerts go to {_recipient}.")
            else:
                st.caption("⚠ No [email] secrets set yet -- see README 'Email alerts' section. "
                           "Alerts will silently no-op until configured.")

    return cfg


def build_ticker_universe() -> list[str]:
    st.sidebar.divider()
    st.sidebar.subheader("Universe source")
    source = st.sidebar.radio("Tickers to scan", ["Default seed list", "Paste tickers", "Upload CSV"], index=0)

    if source == "Default seed list":
        tickers = universe_mod.load_default_universe()
        st.sidebar.caption(f"{len(tickers)} seed tickers loaded (not the full US market -- see Methodology tab).")
    elif source == "Paste tickers":
        text = st.sidebar.text_area("Tickers (comma or newline separated)", "AAPL, NVDA, MSFT")
        tickers = sorted(set(t.strip().upper() for t in text.replace("\n", ",").split(",") if t.strip()))
    else:
        file = st.sidebar.file_uploader("CSV with a 'ticker' column", type=["csv"])
        if file is not None:
            df = pd.read_csv(file)
            col = "ticker" if "ticker" in df.columns else df.columns[0]
            tickers = sorted(set(df[col].astype(str).str.strip().str.upper()))
        else:
            tickers = []

    return tickers


# ---------------------------------------------------------------------------
# Chart (section 24)
# ---------------------------------------------------------------------------

def render_chart(result: dict):
    df = result["daily_df"].tail(180)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)

    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                  name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA_fast"], line=dict(width=1, color="#2563eb"), name="EMA8"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA_mid"], line=dict(width=1, color="#f59e0b"), name="EMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA_slow"], line=dict(width=1, color="#dc2626"), name="EMA50"), row=1, col=1)

    # Resistance and Ideal Entry are often only a fraction of a percent apart (Ideal Entry =
    # Resistance + small buffer), so their default right-edge labels land on top of each other and
    # become unreadable. Each line gets the price value in its label plus a distinct vertical pixel
    # offset (yshift) so the three labels always stack instead of overlapping, regardless of how
    # close the underlying prices are.
    if result.get("resistance"):
        fig.add_hline(y=result["resistance"], line=dict(color="#7c3aed", dash="dash"), row=1, col=1,
                       annotation_text=f"RESISTANCE ${result['resistance']:.2f}",
                       annotation_position="top right",
                       annotation_font_size=11, annotation_font_color="#7c3aed",
                       annotation_yshift=22)
    if result.get("ideal_entry"):
        fig.add_hline(y=result["ideal_entry"], line=dict(color="#16a34a", dash="dot"), row=1, col=1,
                       annotation_text=f"IDEAL ENTRY ${result['ideal_entry']:.2f}",
                       annotation_position="top right",
                       annotation_font_size=11, annotation_font_color="#16a34a",
                       annotation_yshift=4)
    if result.get("stop"):
        fig.add_hline(y=result["stop"], line=dict(color="#dc2626", dash="dot"), row=1, col=1,
                       annotation_text=f"STOP ${result['stop']:.2f}",
                       annotation_position="bottom right",
                       annotation_font_size=11, annotation_font_color="#dc2626",
                       annotation_yshift=-4)

    fl = result.get("first_leg", {})
    if fl.get("date") is not None and fl["date"] in df.index:
        fig.add_vline(x=fl["date"], line=dict(color="#2563eb", dash="dash"), row=1, col=1,
                       annotation_text="FIRST LEG")

    cons = result.get("consolidation", {})
    if cons.get("start_date") is not None and cons.get("end_date") is not None:
        fig.add_vrect(x0=cons["start_date"], x1=cons["end_date"], fillcolor="#fde68a", opacity=0.25,
                       line_width=0, row=1, col=1, annotation_text="CONSOLIDATION")
    if cons.get("higher_low_price") and cons.get("higher_low_date") in df.index:
        fig.add_trace(go.Scatter(x=[cons["higher_low_date"]], y=[cons["higher_low_price"]],
                                  mode="markers+text", marker=dict(color="#16a34a", size=10, symbol="triangle-up"),
                                  text=["Higher Low"], textposition="bottom center", name="Higher Low"), row=1, col=1)

    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color="#94a3b8"), row=2, col=1)

    fig.update_layout(height=650, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10),
                       legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Stock detail (section 23) + WHY (section 25) + DO NOT CHASE (26)
# ---------------------------------------------------------------------------

def render_stock_detail(result: dict):
    st.subheader(f"{result['ticker']} -- {result['status']}  |  Setup Score {result['setup_score']} ({result['grade']})")

    if result["status"] == "EXTENDED":
        st.warning(f"**EXTENDED — DO NOT CHASE**  \nIdeal Entry: ${result['ideal_entry']:.2f}  |  "
                    f"Current Price: ${result['price']:.2f}  |  Distance: {result['distance_to_entry_pct']*100:+.2f}%")
    if result.get("stop_too_wide"):
        st.error(f"**DO NOT TRADE — STOP TOO WIDE**  \nStructural stop implies {result['stop_pct']:.1f}% risk, "
                  f"above MAX_STOP_PERCENT.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("**Setup**")
        st.write(f"Setup Score: {result['setup_score']} ({result['grade']})")
        st.write(f"Status: {result['status']}")
        st.write(f"First Leg Date: {result['first_leg']['date']}")
        st.write(f"Consolidation Start: {result['consolidation']['start_date']}")
        st.write(f"Consolidation Days: {result['consolidation']['days']}")
    with col2:
        st.markdown("**Technical**")
        st.write(f"EMA8: {result['ema8']:.2f}")
        st.write(f"EMA20: {result['ema20']:.2f}")
        st.write(f"EMA50: {result['ema50']:.2f}")
        st.write(f"Weekly EMA8: {result['weekly_ema8']:.2f}" if result['weekly_ema8'] else "Weekly EMA8: n/a")
        st.write(f"Weekly EMA10: {result['weekly_ema10']:.2f}" if result['weekly_ema10'] else "Weekly EMA10: n/a")
        st.write(f"ATR20: {result['atr']:.2f}" if result['atr'] else "ATR20: n/a")
        st.write(f"ADR20: {result['adr']:.2f}%" if result['adr'] else "ADR20: n/a")
        st.write(f"Relative Volume: {result['volume']['RelativeVolume']:.2f}x")
    with col3:
        st.markdown("**Pattern**")
        st.write(f"First Leg Score: {result['first_leg']['score']:.0f}")
        st.write(f"EMA Expansion Score: {result['ema_expansion_score']:.0f}")
        st.write(f"CML Score: {result['cml_score']:.0f} ({'GREEN' if result['cml_green'] else 'NOT GREEN'})")
        st.write(f"VCP Score: {result['vcp']['VCPScore']:.0f}")
        st.write(f"Higher Low: {'YES' if result['consolidation']['higher_low'] else 'NO'}")
        st.write(f"Resistance: ${result['resistance']:.2f}" if result['resistance'] else "Resistance: n/a")
        st.write(f"Resistance Strength: {result['resistance_strength']}")
    with col4:
        st.markdown("**Trade Levels**")
        st.write(f"Ideal Entry: ${result['ideal_entry']:.2f}" if result['ideal_entry'] else "Ideal Entry: n/a")
        st.write(f"Recommended Stop: ${result['stop']:.2f}" if result['stop'] else "Stop: n/a")
        st.write(f"Stop %: {result['stop_pct']:.2f}%" if result['stop_pct'] else "Stop %: n/a")
        st.write(f"Risk/Share: ${result['risk_per_share']:.2f}" if result['risk_per_share'] else "Risk/Share: n/a")
        st.write(f"Stop Method: {result['stop_method']}")
        st.write(f"Entry Quality: {result['components']['entry_quality']:.0f}")

    render_chart(result)

    st.markdown("#### WHY " + ("THIS STOCK PASSED" if result["explanation"]["passed"] else "REJECTED"))
    for line in result["explanation"]["reasons"]:
        st.write(line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def results_to_table(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r.get("ok"):
            rows.append({"Ticker": r["ticker"], "Score": None, "Grade": None, "Status": "ERROR",
                         "Price": None, "Resistance": None, "Ideal Entry": None, "Stop": None,
                         "Risk %": None, "Cons. Days": None, "_error": r.get("error")})
            continue
        rows.append({
            "Ticker": r["ticker"], "Score": r["setup_score"], "Grade": r["grade"], "Status": r["status"],
            "Price": round(r["price"], 2), "Resistance": round(r["resistance"], 2) if r["resistance"] else None,
            "Ideal Entry": round(r["ideal_entry"], 2) if r["ideal_entry"] else None,
            "Stop": round(r["stop"], 2) if r["stop"] else None,
            "Risk %": round(r["stop_pct"], 2) if r["stop_pct"] else None,
            "Cons. Days": r["consolidation"]["days"],
        })
    df = pd.DataFrame(rows)
    if not df.empty and "Grade" in df.columns:
        df["_grade_order"] = df["Grade"].map(GRADE_ORDER).fillna(9)
        df = df.sort_values(["_grade_order", "Score"], ascending=[True, False]).drop(columns="_grade_order")
    return df


def main():
    st.title("📈 Momentum First-Leg Breakout Screener")
    st.caption("Fresh New Trend → First Leg → EMA Expansion → First Valid Consolidation → Breakout. "
               "Screener only -- no backtesting, no automated trading.")

    # Floating "Scan" quick-action button, pinned to the top-right corner of the viewport so it's
    # always one click away without scrolling back up to the sidebar. Pure CSS + a normal st.button
    # -- no extra dependency. The trick: the invisible anchor div below sits in its own element
    # container; ":has()" finds that container, and "+" selects the very next element container
    # (the actual button's wrapper) to pin -- so only THIS button is repositioned, nothing else on
    # the page. Both "stElementContainer" (current Streamlit) and "element-container" (older
    # Streamlit) test-ids are targeted since this attribute name has changed between versions --
    # Streamlit Cloud is on "stElementContainer" as of 2026-08, verified live in the browser after
    # the first version (targeting only "element-container") silently failed to match and the
    # button rendered inline instead of floating. Needs a modern Chromium-based browser for :has()
    # (true for Streamlit Cloud's viewers in practice); on an older browser the button still works,
    # it just renders inline instead of floating.
    st.markdown("""
        <style>
        div[data-testid="stElementContainer"]:has(#floating-scan-anchor)
            + div[data-testid="stElementContainer"],
        div[data-testid="element-container"]:has(#floating-scan-anchor)
            + div[data-testid="element-container"] {
            position: fixed;
            top: 4.2rem;
            right: 2rem;
            z-index: 9999;
            width: auto;
        }
        div[data-testid="stElementContainer"]:has(#floating-scan-anchor)
            + div[data-testid="stElementContainer"] button,
        div[data-testid="element-container"]:has(#floating-scan-anchor)
            + div[data-testid="element-container"] button {
            border-radius: 999px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
        }
        </style>
        <div id="floating-scan-anchor"></div>
    """, unsafe_allow_html=True)
    floating_scan_clicked = st.button("🔍 Scan", key="floating_scan_button", type="primary")

    # Restore the last scan from disk on a brand-new session (new tab, page refresh, or the app
    # waking back up) -- without this, st.session_state starts empty every time and the dashboard
    # shows an empty "click SCAN" screen even though a scan was already run recently (here, or by
    # the scheduled daily_scan.py run). Runs once per session: a scan_clicked run below always
    # overwrites "results" with a fresh one anyway, and later reruns of this same session already
    # have "results" set, so this never clobbers a live in-session scan.
    if "results" not in st.session_state:
        cached = scan_cache.load_last_scan()
        if cached:
            st.session_state["results"] = cached["results"]
            st.session_state["scan_time"] = cached["scan_time"]
            st.session_state["results_source"] = cached.get("source", "unknown")
            st.session_state["results_is_cached"] = True

    cfg = build_sidebar_config()
    tickers = build_ticker_universe()

    scan_clicked = st.sidebar.button("🔍 SCAN", type="primary", use_container_width=True)
    scan_clicked = scan_clicked or floating_scan_clicked

    if scan_clicked:
        if not tickers:
            st.sidebar.error("No tickers to scan -- pick a universe source first.")
        else:
            progress = st.progress(0.0, text="Filtering universe...")

            def _progress(i, total, ticker):
                progress.progress(min(1.0, (i + 1) / total), text=f"Scanning {ticker} ({i+1}/{total})")

            results = scan_universe(tickers, cfg, progress_callback=_progress)
            progress.empty()
            scan_time = dt.datetime.now()
            st.session_state["results"] = results
            st.session_state["scan_time"] = scan_time
            st.session_state["results_source"] = "manual"
            st.session_state["results_is_cached"] = False
            scan_cache.save_last_scan(results, scan_time, source="manual")

            if cfg.enable_email_alerts:
                qualifying = [r for r in results if r.get("ok") and r.get("grade") in cfg.email_alert_grades]
                ready_watchlist = [r for r in results if r.get("ok") and r.get("status") == "READY"]
                ready_watchlist.sort(key=lambda r: r.get("distance_to_entry_pct") if r.get("distance_to_entry_pct") is not None else -1,
                                      reverse=True)
                # A READY hit is, on its own, also worth emailing about -- not just A+/A grades --
                # since the point is to get a heads-up before the breakout happens, not just after.
                if qualifying or ready_watchlist:
                    try:
                        _sender = st.secrets["email"]["sender_address"]
                        _password = st.secrets["email"]["app_password"]
                        _recipient = st.secrets["email"]["recipient_address"]
                    except Exception:
                        _sender = _password = _recipient = None
                    if _sender and _password and _recipient:
                        sent, msg = notify.send_grade_alert_email(_sender, _password, _recipient, qualifying,
                                                                    watchlist_results=ready_watchlist)
                        if sent:
                            st.sidebar.success(f"📧 {msg}")
                        else:
                            st.sidebar.warning(f"📧 {msg}")
                    else:
                        st.sidebar.warning("📧 Email alerts are on but [email] secrets aren't configured -- "
                                            "see README 'Email alerts' section.")

    tab_scan, tab_top, tab_watchlist, tab_calculator, tab_methodology = st.tabs(
        ["Scanner", "A+ Setups (SCAN output)", "Watchlist (READY)", "מחשבון מסחר", "Methodology"])

    results = st.session_state.get("results")

    with tab_scan:
        if results is None:
            st.info("Configure your universe and parameters in the sidebar, then click **SCAN**.")
        else:
            ok_results = [r for r in results if r.get("ok")]
            errored = [r for r in results if not r.get("ok")]
            source = st.session_state.get("results_source")
            source_label = {"manual": "manual SCAN", "daily": "automated daily scan"}.get(source, source or "")
            cached_note = ""
            if st.session_state.get("results_is_cached"):
                cached_note = f" -- 📦 showing the last saved scan ({source_label}). Click **SCAN** for a fresh one."
            st.caption(f"Scanned {len(results)} tickers -- {len(ok_results)} scored, {len(errored)} skipped "
                       f"(insufficient data / provider error). Last scan: {st.session_state.get('scan_time')}"
                       f"{cached_note}")

            table = results_to_table(results)

            error_rows = [r for r in results if not r.get("ok")]
            if error_rows:
                with st.expander(f"🔧 Debug: {len(error_rows)} ticker(s) failed -- click to see why", expanded=False):
                    for r in error_rows[:15]:
                        st.code(f"{r['ticker']}: {r.get('error')}", language=None)
                    if len(error_rows) > 15:
                        st.caption(f"... and {len(error_rows) - 15} more")

            statuses = sorted(table["Status"].dropna().unique().tolist())
            grades = sorted(table["Grade"].dropna().unique().tolist(), key=lambda g: GRADE_ORDER.get(g, 9))

            colf1, colf2 = st.columns(2)
            default_statuses = [s for s in statuses if s not in ("REJECTED", "ERROR")] or statuses
            status_filter = colf1.multiselect("Filter by Status", statuses, default=default_statuses)
            grade_filter = colf2.multiselect("Filter by Grade", grades, default=grades)

            filtered = table[table["Status"].isin(status_filter) & (table["Grade"].isin(grade_filter) | table["Grade"].isna())]

            event = st.dataframe(
                filtered.drop(columns=[c for c in filtered.columns if c.startswith("_")], errors="ignore"),
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row", key="results_table",
            )

            selected_ticker = None
            if event and event.selection and event.selection.get("rows"):
                sel_idx = event.selection["rows"][0]
                selected_ticker = filtered.iloc[sel_idx]["Ticker"]

            if selected_ticker:
                match = next((r for r in ok_results if r["ticker"] == selected_ticker), None)
                if match:
                    st.divider()
                    render_stock_detail(match)

    with tab_top:
        if results is None:
            st.info("Run a SCAN to see the A+/A setup summary.")
        else:
            top = [r for r in results if r.get("ok") and r["grade"] in ("A+", "A")]
            top.sort(key=lambda r: r["setup_score"], reverse=True)
            if not top:
                st.write("No A+/A setups in the current scan.")
            for i, r in enumerate(top, start=1):
                st.markdown(f"**{i}. {r['ticker']}**  \n"
                            f"Score: {r['setup_score']} ({r['grade']}) | Status: {r['status']}  \n"
                            f"Ideal Entry: ${r['ideal_entry']:.2f} | Stop: ${r['stop']:.2f} | "
                            f"Risk: {r['stop_pct']:.2f}%" if r['stop_pct'] else "")
                st.divider()

    with tab_watchlist:
        if results is None:
            st.info("Run a SCAN to see the Watchlist.")
        else:
            watch = [r for r in results if r.get("ok") and r["status"] == "READY"]
            watch.sort(key=lambda r: r.get("distance_to_entry_pct") if r.get("distance_to_entry_pct") is not None else -1,
                       reverse=True)
            st.caption("Stocks in a valid, quality consolidation that are approaching Resistance but haven't "
                       "broken out yet -- a heads-up before the breakout, not itself an A+/A grade "
                       "(see Methodology tab for why Setup Score needs an actual breakout to cross 80).")
            if not watch:
                st.write("No READY setups in the current scan.")
            for i, r in enumerate(watch, start=1):
                dist_pct = r.get("distance_to_entry_pct")
                dist_str = f"{dist_pct * 100:+.2f}%" if dist_pct is not None else "n/a"
                resistance_str = f"${r['resistance']:.2f}" if r.get("resistance") else "n/a"
                ideal_entry_str = f"${r['ideal_entry']:.2f}" if r.get("ideal_entry") else "n/a"
                tv_url = f"https://www.tradingview.com/chart/?symbol={r['ticker']}&interval=D"
                st.markdown(f"**{i}.** <a href=\"{tv_url}\" target=\"_blank\" rel=\"noopener\" "
                            f"style=\"font-weight:700;font-size:1.05em;text-decoration:none;\">{r['ticker']}</a>  \n"
                            f"Score: {r['setup_score']} ({r['grade']}) | Price: ${r['price']:.2f}  \n"
                            f"Resistance: {resistance_str} | Ideal Entry: {ideal_entry_str} | "
                            f"Distance to Entry: {dist_str}", unsafe_allow_html=True)
                st.divider()

    with tab_calculator:
        render_trading_calculator(results)

    with tab_methodology:
        render_methodology(cfg)


def render_methodology(cfg: ScreenerConfig):
    st.header("Methodology")
    st.warning("First Leg, First Valid Consolidation, VCP, CML, Higher Low and Resistance are **not** "
               "unambiguous concepts. Every score below is a transparent, configurable approximation -- "
               "not a claim of 100% precision (spec section 30).")

    st.markdown(f"""
**First Leg Score** = weighted blend of Price-vs-EMA50, EMA50 slope, Higher-High/Higher-Low structure,
Momentum, and Weekly Alignment. Current weights: `{cfg.first_leg_weights}`. Confirmed when score >=
`{cfg.first_leg_score_threshold}`.

**First Valid Consolidation** = the first window after the First Leg (>= `{cfg.min_consolidation_days}`
trading days) that touches EMA{cfg.ema_fast}/EMA{cfg.ema_mid} (tolerance `{cfg.ema_pullback_tolerance_pct:.2%}`)
without a "meaningful" close below EMA{cfg.ema_mid} (tolerance `{cfg.ema20_close_violation_pct:.2%}`,
max `{cfg.ema20_max_violation_days}` violation days tolerated). Once found, later consolidations for the
same leg are not searched; if it breaks the pre-leg low, it's invalidated instead of replaced.

**VCP Score** = weighted blend of ATR/Range/Swing contraction, tightening (std-dev), and volume
contraction within the consolidation window. Weights: `{cfg.vcp_weights}`.

**Resistance** = the pivot-high cluster (tolerance `{cfg.resistance_cluster_tolerance_pct:.2%}`) with the
most touches inside the consolidation window -- not an old, irrelevant high.

**Breakout** requires, on the same day (no look-ahead): Close > Resistance, candle body larger than the
prior day's, breakout range <= `{cfg.max_breakout_atr}` x ATR20, CLV >= `{cfg.clv_threshold}`, and upper
wick <= `{cfg.upper_wick_max_pct:.0%}` of the day's range.

**Ideal Entry** = Resistance x (1 + `{cfg.entry_buffer_pct:.2%}`). Beyond `{cfg.max_extension_atr}` x ATR20
past that level, status becomes EXTENDED — DO NOT CHASE.

**Recommended Stop** = Higher Low (preferred) -> Consolidation Low -> Resistance-based fallback, minus an
ATR buffer (`{cfg.atr_stop_multiplier}` x ATR20). Never moved closer to price to "fit" a trade. If the
resulting risk exceeds `{cfg.max_stop_percent}`%, the setup is flagged DO NOT TRADE — STOP TOO WIDE rather
than the stop being tightened artificially.

**Setup Score** = weighted blend of every component above. Weights: `{cfg.setup_score_weights}`.
Grades: A+ >= {cfg.grade_bands['A+']}, A >= {cfg.grade_bands['A']}, B >= {cfg.grade_bands['B']},
C >= {cfg.grade_bands['C']}, else REJECT.
""")

    with st.expander("Data source & universe notes"):
        st.write(
            "Default provider is yfinance (free, unofficial) for prototyping; EODHD is recommended for "
            "regular use (paid, higher reliability, 100k calls/day). The bundled ticker list is a seed of "
            "liquid, well-known US names -- not a claim of full market coverage. Swap in your own list "
            "(paste or CSV) or a full listings pull from your data provider for complete coverage."
        )


if __name__ == "__main__":
    main()
