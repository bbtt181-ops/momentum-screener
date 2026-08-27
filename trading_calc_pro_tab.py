"""Embeds the existing "מחשבון סוחר עלPRO" trading journal as a live tab.

This does NOT reimplement the calculator -- it loads the user's own existing tool
(https://bbtt181-ops.github.io/trading-calc-pro-v2/index6.html) inside an iframe, so it is
always exactly the same tool, with every feature (trade diary, 3-entry pyramid, 3-exit
management, ATR(21) stop, cloud sync, Google Sheets export, local-storage journal) working
unchanged. If that page is ever updated on GitHub Pages, this tab reflects the update
automatically -- nothing here needs to be touched again.

Deliberately has zero dependency on the screener's own data (results/config) -- this is a
fully standalone tool, same as visiting the URL directly in a browser tab.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

CALC_PRO_URL = "https://bbtt181-ops.github.io/trading-calc-pro-v2/index6.html"
CALC_PRO_HEIGHT = 1400  # tall enough for the full journal without an inner scrollbar on most screens


def render_trading_calc_pro() -> None:
    st.subheader("מחשבון סוחר עלPRO")
    st.caption(
        "הכלי המלא שלך (יומן מסחר, פירמידת כניסות/יציאות, ATR(21) stop, סנכרון ענן, ייצוא ל-Sheets) "
        "טעון כאן ישירות מהדף המקורי -- זהו בדיוק אותו כלי, לא עותק. "
        f"[פתח בטאב נפרד ↗]({CALC_PRO_URL})"
    )
    components.iframe(src=CALC_PRO_URL, height=CALC_PRO_HEIGHT, scrolling=True)
