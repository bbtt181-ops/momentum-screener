"""
Central configuration for the Momentum First-Leg Breakout Screener.

Every threshold, weight, and tolerance referenced by the methodology lives
here. Nothing in patterns/, scoring/, or indicators/ should hard-code a
number that a user might reasonably want to tune — it should be read from
a ScreenerConfig instance instead.

The dataclass can be constructed with defaults (matching the approved
methodology) or overridden field-by-field, e.g. from the Streamlit sidebar.
"""

from dataclasses import dataclass, field, asdict


@dataclass
class ScreenerConfig:
    # ------------------------------------------------------------------
    # 2. STOCK UNIVERSE
    # ------------------------------------------------------------------
    min_price: float = 5.0
    min_market_cap: float = 300_000_000
    min_avg_volume: float = 500_000
    avg_volume_window: int = 20

    # ------------------------------------------------------------------
    # 5. EMA STRUCTURE
    # ------------------------------------------------------------------
    ema_fast: int = 8
    ema_mid: int = 20
    ema_slow: int = 50
    weekly_ema_fast: int = 8
    weekly_ema_slow: int = 10

    # ------------------------------------------------------------------
    # 4. FIRST LEG
    # ------------------------------------------------------------------
    first_leg_slope_window: int = 10          # days used for EMA50 slope
    first_leg_momentum_window: int = 20       # ROC window
    first_leg_swing_fractal: int = 3          # bars each side for HH/HL fractal
    first_leg_weekly_tolerance_pct: float = 0.03   # weekly EMA8/10 proximity band
    first_leg_score_threshold: float = 60.0   # score needed to "confirm" a First Leg

    # Component weights for First Leg Score (must sum to 100)
    first_leg_weights: dict = field(default_factory=lambda: {
        "price_vs_ema50": 20,
        "ema50_slope": 25,
        "hh_hl_structure": 20,
        "momentum": 15,
        "weekly_alignment": 20,
    })

    # ------------------------------------------------------------------
    # 5. EMA EXPANSION
    # ------------------------------------------------------------------
    ema_expansion_lookback: int = 10          # days to compare spread growth

    # ------------------------------------------------------------------
    # 6. CML GREEN PROXY
    # ------------------------------------------------------------------
    cml_lookback: int = 20
    cml_green_threshold: float = 60.0

    cml_weights: dict = field(default_factory=lambda: {
        "momentum": 25,
        "linreg_slope": 25,
        "trend_consistency": 20,
        "candle_overlap": 15,
        "directional_efficiency": 15,
    })

    # ------------------------------------------------------------------
    # 7-10. FIRST VALID CONSOLIDATION / PULLBACK / EMA20 RULE / HIGHER LOW
    # ------------------------------------------------------------------
    min_consolidation_days: int = 7
    max_consolidation_search_days: int = 90   # stop looking for a valid window after this many days post First Leg
    ema_pullback_tolerance_pct: float = 0.01  # "Low <= EMA * (1+tol)" tolerance
    ema20_close_violation_pct: float = 0.015  # how far below EMA20 a close can be w/o being "meaningful"
    ema20_max_violation_days: int = 2         # how many such closes are tolerated before invalidating
    consolidation_range_contraction_max: float = 0.85  # consolidation range vs prior leg range must be <= this
    higher_low_min_gap_pct: float = 0.005     # min rise required for a low to count as "higher"

    # ------------------------------------------------------------------
    # 11. VCP
    # ------------------------------------------------------------------
    vcp_weights: dict = field(default_factory=lambda: {
        "atr_contraction": 25,
        "range_contraction": 20,
        "swing_contraction": 20,
        "tightening": 20,
        "volume_contraction": 15,
    })

    # ------------------------------------------------------------------
    # 13. RESISTANCE
    # ------------------------------------------------------------------
    resistance_fractal: int = 2               # bars each side for pivot high
    resistance_cluster_tolerance_pct: float = 0.01

    # ------------------------------------------------------------------
    # 14. BREAKOUT
    # ------------------------------------------------------------------
    atr_window: int = 20
    max_breakout_atr: float = 2.5
    clv_threshold: float = 0.786
    upper_wick_max_pct: float = 0.25          # upper wick / total range must be <= this

    # ------------------------------------------------------------------
    # 15. VOLUME
    # ------------------------------------------------------------------
    volume_avg_window: int = 20

    # ------------------------------------------------------------------
    # 17. IDEAL ENTRY / EXTENDED
    # ------------------------------------------------------------------
    entry_buffer_pct: float = 0.002           # 0.20% above resistance
    max_extension_atr: float = 1.5            # beyond this many ATRs past ideal entry => EXTENDED
    ready_proximity_pct: float = 0.03         # within this % of resistance => READY (else WATCH)

    # ------------------------------------------------------------------
    # 18-19. STOP LOSS
    # ------------------------------------------------------------------
    atr_stop_multiplier: float = 0.5          # ATR buffer subtracted below structural low
    max_stop_percent: float = 8.0             # DO NOT TRADE - STOP TOO WIDE beyond this

    # ------------------------------------------------------------------
    # 20. SETUP SCORE WEIGHTS (must sum to 100)
    # ------------------------------------------------------------------
    setup_score_weights: dict = field(default_factory=lambda: {
        "first_leg": 12,
        "weekly_alignment": 8,
        "ema_structure": 8,
        "ema_expansion": 8,
        "cml": 8,
        "consolidation_quality": 10,
        "vcp": 10,
        "higher_low": 6,
        "resistance_quality": 6,
        "breakout_quality": 10,
        "volume": 6,
        "entry_quality": 5,
        "stop_quality": 3,
    })

    grade_bands: dict = field(default_factory=lambda: {
        "A+": 90,
        "A": 80,
        "B": 70,
        "C": 60,
    })

    # ------------------------------------------------------------------
    # 21. ENTRY QUALITY WEIGHTS (must sum to 100)
    # ------------------------------------------------------------------
    entry_quality_weights: dict = field(default_factory=lambda: {
        "distance_from_resistance": 20,
        "distance_from_ema20": 15,
        "breakout_strength": 25,
        "atr_extension": 20,
        "stop_distance": 10,
        "price_vs_ideal_entry": 10,
    })

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------
    daily_history_years: int = 3
    weekly_history_years: int = 5
    data_provider: str = "yfinance"           # "yfinance" | "eodhd"
    eodhd_api_key: str = ""

    # ------------------------------------------------------------------
    # EMAIL ALERTS -- sends one email per SCAN if any result's grade is
    # in `email_alert_grades`. Sender/recipient/app-password are never
    # entered in the app UI -- they live in Streamlit secrets only (see
    # README "Email alerts" section).
    # ------------------------------------------------------------------
    enable_email_alerts: bool = False
    email_alert_grades: list = field(default_factory=lambda: ["A+", "A"])

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = ScreenerConfig()
