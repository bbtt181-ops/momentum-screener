# Momentum First-Leg Breakout Screener

A **stock screener only** (no backtester, no automated trading) that looks for:

```
Fresh New Trend → First Leg → EMA Expansion → First Valid Consolidation → Breakout
```

See `Methodology` tab inside the app (or `methodology.md` if you received it separately) for exactly how
First Leg, First Valid Consolidation, VCP, CML, Resistance, Breakout, Ideal Entry and Recommended Stop are
defined — every threshold is configurable from the sidebar, nothing is hard-coded.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the dashboard

```bash
streamlit run app.py
```

This opens the dashboard in your browser (usually http://localhost:8501). In the sidebar:

1. Pick a **Data Provider** (`yfinance` is free and works out of the box; `eodhd` needs an API key,
   see below).
2. Set your universe filters (price, market cap, avg volume) and any pattern thresholds you want to change.
3. Choose a ticker source: the bundled seed list, a pasted list, or a CSV upload.
4. Click **SCAN** (in the sidebar), or the floating **🔍 Scan** button pinned to the top-right corner of
   the page -- both trigger the exact same scan, so you don't need to scroll back up to the sidebar.
5. Click any row in the results table to open the Stock Detail panel, chart, and WHY explanation.

**The last scan is remembered.** Opening the dashboard in a new tab, refreshing the page, or coming back
after Streamlit Cloud puts the app to sleep no longer shows an empty "click SCAN" screen -- it shows your
last scan instead (marked "📦 showing the last saved scan" until you click SCAN again). This is written to
a local file (`.cache/last_scan.pkl`, git-ignored) after every scan -- from this dashboard's own SCAN
button, and, on a local run, from the scheduled `daily_scan.py` run too, so the dashboard also reflects
last night's automated scan without you having to click SCAN yourself. This is a local file, not a
database: it survives a page refresh or new tab on the same machine, but not a full redeploy (Streamlit
Cloud clears its disk on redeploy) or a fresh clone of the repo.

## Data providers

- **yfinance** (default): free, unofficial (scrapes Yahoo Finance). Good for trying the screener out.
  It can be rate-limited if you scan a very large universe repeatedly in a short time.
- **EODHD**: recommended once you're scanning regularly. Sign up at https://eodhd.com, grab an API key,
  and either paste it into the sidebar or set it as an environment variable:

  ```bash
  export EODHD_API_KEY=your_key_here
  ```

Switching providers is a one-line change in the sidebar (`data_provider`) — no code edits needed.

## Universe

The bundled `data/default_universe.csv` is a **seed list** of ~240 liquid, well-known US tickers across
sectors — it is explicitly *not* a claim of full market coverage (building a true "every US stock over
$300M market cap" universe requires a paid listings feed). Replace it with your own list (paste or CSV)
at any time, or point `data/universe.py` at a full listings pull from your EODHD/other provider once you
have one.

## Email alerts

The app can email you after a SCAN if any result's grade matches ones you pick (default: A+ and A). It
uses Gmail's SMTP with an **App Password** (not your normal Gmail password) -- credentials are read only
from Streamlit secrets, never typed into the app itself, so they're never visible in the UI or committed
to GitHub.

**1. Create a Gmail App Password** (needs 2-Step Verification turned on for your Google account first):
   - Go to https://myaccount.google.com/apppasswords
   - Create a new app password (name it anything, e.g. "momentum-screener")
   - Copy the 16-character password it gives you

**2. Add secrets:**
   - **Local run**: create a file `.streamlit/secrets.toml` in the project folder (this file is already
     git-ignored, so it never gets uploaded to GitHub) with:
     ```toml
     [email]
     sender_address = "youraccount@gmail.com"
     app_password = "xxxx xxxx xxxx xxxx"
     recipient_address = "where-alerts-should-go@example.com"
     ```
   - **Streamlit Community Cloud**: open your deployed app -> Settings -> Secrets, paste the same TOML
     block, and save. The app picks it up automatically, no redeploy needed.

**3. In the sidebar**, open "Email alerts", check "Email me after SCAN if a matching grade is found", and
pick which grades should trigger an email. One email is sent per SCAN (not per ticker), listing every
matching ticker with its grade, score, status, ideal entry and stop.

If secrets aren't configured yet, the sidebar shows a warning instead of failing silently.

**Watchlist (READY) section**: every alert email also includes a separate section for any result whose
**Status** is READY -- approaching Resistance but hasn't broken out yet -- regardless of grade. A stock in
READY status essentially can't have an A+/A grade yet (Setup Score needs the actual breakout candle to
score `breakout_quality`; see the Methodology tab), so without this section you'd only ever hear about a
setup on the day it already broke out. A non-empty Watchlist is, on its own, enough to trigger an email
even if the same SCAN found zero A+/A results. The same READY setups are also listed in full in the
dashboard's **Watchlist (READY)** tab, where each ticker is a clickable link that opens straight into its
daily chart on TradingView (`https://www.tradingview.com/chart/?symbol={TICKER}&interval=D`) in a new tab --
the `/chart/` URL (rather than `/symbols/{TICKER}/`, which lands on a summary/overview page instead of the
actual chart) opens the interactive chart app directly, with the daily interval pre-selected, and TradingView
auto-resolves the plain ticker to its primary exchange without needing an explicit `EXCHANGE:` prefix.

**Reached-entry alert**: within the Watchlist, any READY result whose current price has reached or crossed
above its Ideal Entry level (`distance_to_entry_pct >= 0`) is called out separately, at the top, in its own
highlighted "🔔 reached entry" box -- both in the email (`_reached_entry_block_html` in `notify.py`) and in
the subject line itself (e.g. "🔔 Momentum Screener: 2 READY setup(s) reached entry!"), so it's visible
without opening the email. This is a heads-up that the price level you'd actually want to enter at has been
reached, even on a day the candle doesn't (yet, or ever) qualify as a full A+/A BREAKOUT.

**Header image**: every email includes a real, different photo every time (fetched live from
[Lorem Picsum](https://picsum.photos), free, no API key, backed by Unsplash's library, so it can be any
subject anywhere in the world). The quote itself is shown as plain text right below the image, not drawn
onto it -- an earlier version tried rendering the Hebrew quote directly onto the photo and that turned out
to be a real (and, on one real run, silently failing) point of failure, so it was simplified back to just
a photo. Fetching the photo needs internet access at send time; if that fails for any reason (offline,
blocked, slow, non-200 response) it falls back to a local procedural gradient background instead
(`imagegen.py`'s `_procedural_background()`), so a flaky network only ever makes that one email's image
plainer, never blocks the send. The quote itself is drawn from a broad pool of ~20 short, well-known
empowering quotes spanning different eras, cultures and fields (science, business, civil rights, art,
philosophy, sport, proverbs) -- see `MOTIVATIONAL_QUOTES` in `notify.py`.

## Daily automatic scan (Windows Task Scheduler)

This runs the full scan **once a day at a fixed local time on your own PC** -- no GitHub, no cloud
automation. It uses `daily_scan.py`, a standalone version of the scan that doesn't need Streamlit
running, and emails you (using the same email-alert logic as the dashboard) if any result grades A+ or A
(configurable).

**1. Create your credentials file:**
   - Copy `.env.example` to a new file named `.env` in the project folder (same folder as `daily_scan.py`).
   - Fill in the same three values used for the dashboard's email alerts (see "Email alerts" above for
     how to create a Gmail App Password):
     ```
     GMAIL_SENDER_ADDRESS=youraccount@gmail.com
     GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
     ALERT_RECIPIENT_ADDRESS=where-alerts-should-go@example.com
     ```
   - `.env` is already git-ignored, so it's never uploaded anywhere.

**2. Test it manually first** (from the project folder, with the venv active):
   ```bash
   .venv\Scripts\activate
   python daily_scan.py
   ```
   This scans the full seed universe once and prints progress. Check `daily_scan.log` (created next to the
   script) for a run history. Unlike the dashboard's SCAN button, this always sends one summary email at
   the end of every run -- even when 0 results match your alert grades -- so a "nothing today" email still
   confirms the scan actually ran the full universe. If it also finds any READY (Watchlist) setups, those
   are included in that same email; see "Email alerts" above.

**3. Register the Windows Scheduled Task** so it runs automatically every day at 22:00 (10:00 PM) local
   time -- open **Command Prompt** (not PowerShell) and run, adjusting the paths only if your project
   folder isn't `C:\Users\PC\Desktop\momentum-screener`:
   ```bat
   schtasks /create /tn "MomentumScreenerDailyScan" /tr "\"C:\Users\PC\Desktop\momentum-screener\.venv\Scripts\python.exe\" \"C:\Users\PC\Desktop\momentum-screener\daily_scan.py\"" /sc DAILY /st 22:00
   ```
   If the task already exists (created at an earlier time), just update its run time instead of deleting and
   recreating it:
   ```bat
   schtasks /change /tn "MomentumScreenerDailyScan" /st 22:00
   ```
   Because this uses your PC's **local time and timezone directly**, there's no UTC/DST conversion to get
   wrong -- 22:00 always means 22:00 on your clock, summer or winter.

   **Timing trade-off, by design choice:** US markets close at 16:00 ET, which is ~23:00 Israel time --
   so 22:00 is about an hour *before* the close. The Breakout conditions (Close > Resistance, CLV, candle
   body, etc.) are defined against the day's **final** Close. A scan at 22:00 uses yfinance's most recent
   available candle, which on a day still in progress can still move before the real close -- so a
   BREAKOUT status seen at 22:00 is provisional and could look different (or vanish) if you re-scanned
   after 23:00. This was a deliberate choice (get the day's picture earlier, accept it may not be final)
   rather than an oversight -- see the "תדירות ההרצה" methodology note in the project for the full
   reasoning. If you ever want the fully-final end-of-day picture instead, change `/st 22:00` to
   `/st 23:05` (or later) using the same `schtasks /change` command above.

   Your computer needs to be **on and awake** at 22:00 for the task to run (it won't fire while asleep or
   shut down; Windows will *not* automatically run it late, though you can enable "Run task as soon as
   possible after a scheduled start is missed" in Task Scheduler's task properties if you want a fallback).

**4. Manage the task** any time via the Task Scheduler GUI (search "Task Scheduler" in the Start menu ->
   find "MomentumScreenerDailyScan" in the Task Scheduler Library), or from Command Prompt:
   ```bat
   schtasks /run /tn "MomentumScreenerDailyScan"      REM run it right now, to test
   schtasks /query /tn "MomentumScreenerDailyScan"    REM check its status/last run result
   schtasks /delete /tn "MomentumScreenerDailyScan"   REM remove it entirely
   ```

## Watchdog alert (optional but recommended)

The daily scan already emails a summary every run, even a "0 setups today" one -- but that only works if
the scan actually *runs*. If the PC is off/asleep at the scheduled time, the Scheduled Task gets disabled or
deleted, or the script crashes before it reaches the email step, there is otherwise **no signal anywhere**
that anything went wrong -- silence just looks identical to "nothing to report."

`watchdog.py` closes that gap: it's a second, much smaller Scheduled Task that runs ~20-25 minutes after the
main scan's start time and checks `daily_scan.log` for today's date. If there's no "Daily scan starting"
line at all, or a scan started but never reached a successful "Email sent:" line, it sends its own short
plain-text alert email (e.g. "⚠️ הסריקה האוטומטית לא רצה הלילה"). If the main scan ran and emailed
successfully, the watchdog exits quietly -- no double email. It's deliberately simple (plain `smtplib`, no
HTML, no header image, no external fetch) and independent of `notify.py`/`imagegen.py`, since a
failure-detector that shares moving parts with what it's supposed to catch failures in isn't a reliable
failure-detector.

**Register it** (uses the same `.env` credentials as the main scan -- no separate setup needed) -- either
run `setup_watchdog_task.bat` once, or from Command Prompt:
```bat
schtasks /create /tn "MomentumScreenerWatchdog" /tr "\"C:\Users\PC\Desktop\momentum-screener\.venv\Scripts\python.exe\" \"C:\Users\PC\Desktop\momentum-screener\watchdog.py\"" /sc DAILY /st 22:25
```
22:25 assumes the main scan is at 22:00 (a full ~280-ticker scan has historically taken 12-17 minutes, so 25
minutes is a comfortable buffer). **If you ever change the main scan's time, update this one to match** (main
time + ~25 minutes):
```bat
schtasks /change /tn "MomentumScreenerWatchdog" /st HH:MM
```
Test it manually any time with `python watchdog.py` (from the activated venv) -- it logs its own checks to
`watchdog.log` next to `daily_scan.log`.

## Report to Adam

If you run the "Adam" supervisor system (adam-brain.gs, discord-agent-gas, etc.), `daily_scan.py` can log
each run to your shared **"ADAM Performance Log"** Google Sheet after it finishes -- so Adam has visibility
into whether the scanner ran today and whether the alert email was sent, using the same
`date, run_type, agent, ...` row format your other agents already write. The scan itself keeps running
locally on this PC exactly as set up above -- this only reports the result, it doesn't move execution to
the cloud.

This needs a one-time Google Cloud service-account setup, since a local Python script can't use your normal
Google login to write to a Sheet:

**1. Create a service account and key:**
   - Go to https://console.cloud.google.com/ and create a project (or pick an existing one).
   - Enable the **Google Sheets API** for that project (APIs & Services -> Enable APIs -> search "Google
     Sheets API" -> Enable).
   - Go to IAM & Admin -> Service Accounts -> Create Service Account (any name, e.g.
     "momentum-screener-adam-logger"). No roles needed at the project level.
   - Open the new service account -> Keys -> Add Key -> Create new key -> JSON. This downloads a `.json`
     file -- **treat it like a password**, it grants write access to whatever you share with it.

**2. Install the key and share the sheet:**
   - Rename the downloaded file to `adam-service-account.json` and place it in the project folder (already
     git-ignored, so it never gets committed).
   - Open the JSON file and copy the `client_email` value (looks like
     `something@your-project.iam.gserviceaccount.com`).
   - Open the "ADAM Performance Log" sheet in your browser -> Share -> paste that email address -> give it
     **Editor** access.

**3. That's it** -- the next `python daily_scan.py` run (manual or scheduled) will append one row automatically.
If the JSON file isn't there yet, this step quietly no-ops (logged in `daily_scan.log` as "Adam log
skipped/failed"), it never blocks the actual scan or your alert email.

## Live IBD50 ticker list

`daily_scan.py` also adds every ticker currently in the **"ibd50"** tab (column A) of your "סוחר עלPRO"
Google Sheet to the seed universe before each scan -- pulled fresh at scan time, not a one-time paste. Since
that tab updates about once a week, this means each day's scan automatically picks up whatever the sheet
currently has, with no manual re-copying.

This reuses the **same service account** from "Report to Adam" above -- if you've already done that setup,
there's only one more step:

- Open the "סוחר עלPRO" sheet -> Share -> paste the same service account email (from the JSON file's
  `client_email`) -> **Viewer** access is enough (read-only).

If the service account isn't set up yet, or isn't shared on this sheet, or the "ibd50" tab isn't found, the
scan just falls back to the seed list alone (logged in `daily_scan.log`, never blocks the scan).

## Running the smoke test (no network required)

```bash
python -m tests.test_pipeline
```

This runs the full pipeline (indicators → First Leg → Consolidation → VCP → Resistance → Breakout →
Entry/Stop → Setup Score) against a synthetic, engineered OHLCV series that deliberately contains a First
Leg, a valid consolidation with a Higher Low, and a breakout day — useful for confirming the code still
works after you tune a threshold, without needing live data access.

## Project layout

```
config.py            Every configurable parameter (dataclass) -- nothing hard-coded elsewhere
data/                 Providers (yfinance, EODHD), SQLite cache, universe filtering
indicators/core.py    EMA, ATR, ADR, linreg slope/R2, CLV, candle overlap, directional efficiency, etc.
patterns/             First Leg, EMA Expansion, CML proxy, Consolidation/Higher Low, VCP, Resistance, Breakout, Volume
scoring/               Ideal Entry, Recommended Stop, Status, Setup Score/Entry Quality, WHY explanations
scanner.py            Orchestrates the full per-ticker pipeline + universe scan
app.py                Streamlit dashboard
tests/                 Synthetic-data smoke test (no network needed)
```

## Known limitations (see spec section 30)

First Leg, First Valid Consolidation, VCP, CML, Higher Low, and "relevant" Resistance are not
unambiguous concepts. Every score here is a transparent, configurable approximation — read the
Methodology tab before trusting the output, and treat A+/A grades as a shortlist to review, not a
guarantee.
