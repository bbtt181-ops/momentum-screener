"""Risk-first calculator driven only by validated Momentum Screener setups."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR

import pandas as pd
import streamlit as st


def _format_setup(result: dict) -> str:
    return f"{result['ticker']} · {result['status']} · {result['grade']} · score {result['setup_score']:.1f}"


def render_trading_calculator(results: list[dict] | None) -> None:
    st.subheader("מחשבון מסחר — מתוך ה־Screener")
    st.caption("הכניסה, הסטופ ו־ATR20 מגיעים מלוגיקת ה־Momentum Screener. אין כאן סטופ שרירותי.")

    eligible = [
        result for result in (results or [])
        if result.get("ok") and result.get("ideal_entry") and result.get("stop") and result.get("atr")
    ]
    if not eligible:
        st.info("הרץ SCAN כדי לבחור Setup תקין. המחשבון משתמש רק בכניסה ובסטופ שחושבו על ידי ה־Screener.")
        return

    selected_index = st.selectbox(
        "בחר Setup לחישוב",
        range(len(eligible)),
        format_func=lambda index: _format_setup(eligible[index]),
        key="calculator_setup",
    )
    setup = eligible[selected_index]
    entry = Decimal(str(setup["ideal_entry"]))
    stop = Decimal(str(setup["stop"]))
    atr = Decimal(str(setup["atr"]))
    risk_per_share = Decimal(str(setup["risk_per_share"]))
    stop_pct = Decimal(str(setup["stop_pct"]))

    details = st.columns(4)
    details[0].metric("מחיר נוכחי", f"${setup['price']:,.2f}", border=True)
    details[1].metric("כניסה אידאלית", f"${entry:,.2f}", border=True)
    details[2].metric("סטופ מחושב", f"${stop:,.2f}", border=True)
    details[3].metric("ATR20", f"${atr:,.2f}", border=True)
    st.caption(f"שיטת הסטופ: {setup['stop_method']} · מרחק סיכון: ${risk_per_share:,.2f} למניה ({stop_pct:.2f}%).")

    if setup.get("stop_too_wide"):
        st.error(
            f"לא לסחור ב־{setup['ticker']} לפי ההגדרה הנוכחית: הסטופ המבני דורש {stop_pct:.2f}% סיכון, "
            "מעל המגבלה. הסטופ לא מוצמד מלאכותית למחיר."
        )
        return

    with st.form("screener_trade_calculator", border=True):
        equity_col, risk_col = st.columns(2)
        with equity_col:
            account_equity = st.number_input("שווי חשבון ($)", min_value=0.01, value=50_000.0, step=100.0)
        with risk_col:
            risk_percent = st.number_input("סיכון לעסקה (%)", min_value=1.0, max_value=2.5, value=1.5, step=0.25)
        submitted = st.form_submit_button("חשב גודל פוזיציה", type="primary", icon=":material/calculate:")

    if not submitted:
        return

    risk_budget = Decimal(str(account_equity)) * Decimal(str(risk_percent)) / Decimal("100")
    shares = (risk_budget / risk_per_share).to_integral_value(rounding=ROUND_FLOOR)
    actual_risk = shares * risk_per_share
    position_value = shares * entry

    st.badge(f"{setup['ticker']} · Long", icon=":material/trending_up:", color="green")
    metrics = st.columns(4)
    metrics[0].metric("תקציב סיכון", f"${risk_budget:,.2f}", border=True)
    metrics[1].metric("גודל פוזיציה", f"{shares:,.0f} מניות", border=True)
    metrics[2].metric("שווי פוזיציה", f"${position_value:,.2f}", border=True)
    metrics[3].metric("Planned 1R", f"${actual_risk:,.2f}", border=True)

    st.dataframe(
        pd.DataFrame([{
            "סימול": setup["ticker"], "כניסה": float(entry), "סטופ": float(stop),
            "מניות": int(shares), "סיכון למניה": float(risk_per_share), "סיכון בפועל": float(actual_risk),
        }]),
        column_config={
            "כניסה": st.column_config.NumberColumn(format="$%.2f"),
            "סטופ": st.column_config.NumberColumn(format="$%.2f"),
            "סיכון למניה": st.column_config.NumberColumn(format="$%.2f"),
            "סיכון בפועל": st.column_config.NumberColumn(format="$%.2f"),
        },
        hide_index=True,
    )
    st.caption("החישוב אינו שולח פקודה לברוקר. הוא מתרגם את ה־Setup המאושר לגודל פוזיציה לפי הסיכון שהגדרת.")
