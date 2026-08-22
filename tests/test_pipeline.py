"""
Run with: python -m tests.test_pipeline   (from the project root)

Not a pytest suite by design -- it's a readable smoke test that prints the
full scan result for a synthetic, engineered setup so a human can sanity
check that First Leg / Consolidation / VCP / Resistance / Breakout /
Entry / Stop / Setup Score all fire sensibly end-to-end, without requiring
network access to a real data provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ScreenerConfig
from scanner import scan_ticker_from_df
from tests.synthetic_data import build_synthetic_series


def run():
    cfg = ScreenerConfig()
    df = build_synthetic_series()

    print(f"Synthetic series: {len(df)} bars, {df.index[0].date()} -> {df.index[-1].date()}")

    result = scan_ticker_from_df("SYNTH", df, cfg)

    if not result["ok"]:
        print("SCAN FAILED:", result["error"])
        return False

    print("\n--- SCAN RESULT ---")
    print(f"Ticker:        {result['ticker']}")
    print(f"As of:         {result['as_of']}")
    print(f"Price:         {result['price']:.2f}")
    print(f"Status:        {result['status']}")
    print(f"Setup Score:   {result['setup_score']} ({result['grade']})")
    print(f"First Leg:     confirmed={result['first_leg']['confirmed']} "
          f"date={result['first_leg']['date']} score={result['first_leg']['score']:.1f}")
    print(f"Consolidation: found={result['consolidation']['found']} "
          f"days={result['consolidation']['days']} higher_low={result['consolidation']['higher_low']} "
          f"invalidated={result['consolidation']['invalidated']}")
    print(f"VCP Score:     {result['vcp']['VCPScore']}")
    print(f"Resistance:    {result['resistance']} (strength={result['resistance_strength']}, "
          f"method={result['resistance_method']})")
    print(f"Breakout:      is_breakout={result['breakout']['is_breakout']} "
          f"quality={result['breakout']['quality']}")
    print(f"Ideal Entry:   {result['ideal_entry']}")
    print(f"Distance %:    {result['distance_to_entry_pct']}")
    print(f"Stop:          {result['stop']} ({result['stop_method']}) "
          f"stop%={result['stop_pct']} too_wide={result['stop_too_wide']}")
    print(f"Components:    {result['components']}")

    print("\n--- WHY ---")
    for line in result["explanation"]["reasons"]:
        print(" ", line)

    # sanity assertions -- this synthetic series was built specifically to
    # contain a first leg, a valid consolidation, and a breakout, so the
    # pipeline should find all three.
    assert result["first_leg"]["confirmed"], "expected a confirmed First Leg on the synthetic series"
    assert result["consolidation"]["found"], "expected a valid consolidation on the synthetic series"
    assert result["status"] in ("BREAKOUT", "READY", "EXTENDED"), (
        f"expected an advanced status on the engineered breakout day, got {result['status']}"
    )
    print("\nAll sanity checks passed.")
    return True


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
