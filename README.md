# Trend Hunter — Live Scanner (no login)

This is the **original live IntraTradez / Trend Hunter scanner**, not the backtest app. The Google/Supabase membership system, Razorpay checkout, phone-number allowlist, payment pages, and login UI/endpoints have been removed. There is **no user database, login, or payment configuration**.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Enter your `KITE_API_KEY` and **current** `KITE_ACCESS_TOKEN` in `.env`. The app loads `.env` automatically. Then run:

```bash
python3 live_scanner_server.py
```

Open **http://127.0.0.1:8050**. No login required. The scanner works only with a valid Zerodha Kite subscription and an unexpired access token; it may take time to seed candles and connect live ticks.

## Deployment

`render.yaml` has been **removed** from this package as requested. Configure the Render web service manually in its dashboard:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 8 --timeout 120`
- **Environment:** Set `KITE_API_KEY`, `KITE_ACCESS_TOKEN` (and any scanner options you need) in Render's environment settings; never commit `.env` or market-data credentials.
- **Plan:** Select your intended Render plan in Render's dashboard; deleting the local YAML **does not change an already running service's plan or settings**.

`app.py` (Gunicorn) and `main.py` (Uvicorn) are still available. Render does not automatically persist runtime candle-cache files unless a disk is attached.

**Security:** Anyone who can access the server can view market data and invoke the read-only scanner APIs. Do not put it on a public domain unless this is intentional. Kite credentials remain server-side; never put them into the frontend.

## Retained features

- Zerodha Kite WebSocket live ticks and historical seeding
- Momentum/score leaderboards, volume-ratio leaders and % change leaders
- Sector Flow and clickable sector constituents
- TradingView stock links and 5-minute chart navigation
- NIFTY regime and relevant scan APIs
- In-memory/pickle candle caching (not an authentication database)

The login removal does **not** fix slow upstream Kite connections or heavy indicator calculations; it only removes authentication overhead and blocking UI.

## Mobile sector fix

Sector Flow now renders every sector in one non-wrapping horizontal row on phones and tablets. The previous fixed 14-column grid was forcing the 15th sector onto a new line. This is a UI-only CSS change; the live scanner, calculations, click-to-open sector popup, and API endpoints are unchanged.

## Continuation Radar from market open (additive fifth module)

The original **Momentum Radar**, **Sector Flow**, **Volume Radar**, **% Change Radar**, Kite WebSocket scanner, trading links, no-login setup, and original light theme remain in place. Nothing was replaced. Select **Continuation Radar** directly beneath **%Change Radar** in the navigation.

- Collects from **09:15 AM IST** and starts showing **Developing** bullish/bearish candidates after the first candle completes at **09:20**. Refreshes on each new completed 5-minute candle (the selected tab polls every 15 seconds). From **10:00**, when nine full 5-minute candles are available, the original strict qualification filters apply. No future or partial candles are included.
- Shows **Top 5 Bullish Continuation** and **Top 5 Bearish Continuation**, sorted by a separate 0-100 directional quality score.
- Quality score = trend efficiency 25%, candle structure + volume-weighted direction persistence 25%, session VWAP and EMA9/21 alignment 20%, time-matched historical cumulative volume ratio (RVOL) 15%, and relative strength versus NIFTY-50 constituents / sector 15%.
- Before 10:00, the ranks are **provisional**, based on available candles; full-screen thresholds do **not** apply prematurely. The 09:15–09:45 opening range is only established at 09:45, and its breakout can first be detected after 09:45.
- From 10:00, applies minimum liquidity, RVOL, efficiency, opening-range breakout, and reversal filters. **There may be zero qualifying stocks**. No fabricated values are used to fill the Top 5 slots.
- RVOL uses the median cumulative 5-minute-candle volume at the **same completed time** over up to 30 earlier sessions; a minimum five comparable sessions is required.
- If RVOL or benchmark data are not yet sufficient before 10:00, provisional rankings may still appear, with RVOL shown as unavailable and missing benchmark strength treated as neutral for scoring—not as a fabricated reading. The 10:00+ strict screen still requires sufficient data.
- The NIFTY comparison is an **equal-weighted proxy of available NIFTY 50 constituent moves** (not an official NIFTY index candle). It requires at least ten fully observed constituents. Sector comparisons use observed constituent returns.
- Click any stock name to open an NSE TradingView chart in a new browser tab, requesting the 5-minute interval. TradingView itself may show candles later than the scanner snapshot.
- Isolated read-only API: `GET /api/continuation`. The pre-existing `/api/scan` API and all its outputs are unchanged. Continuation history is processed only when its tab is selected (and the server caches it briefly).

> This is an experimental ranking heuristic, **not a guarantee or verified prediction** of the rest of the trading session. Backtest quality thresholds before relying on them.

### Test

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile live_scanner_server.py continuation_radar.py
```

See the test command above for the current unit and regression check results. Existing Kite live-feed runtime and full served-browser workflow could not be end-to-end tested without a valid Kite environment.

## Live-data stability patch (2026-10-26)

The scanner's existing polling previously set `state.liveRows = null` when a market-open `/api/scan` response temporarily contained zero rows or an API request failed after the feed had disconnected. This made all the stock rankings and sector lists disappear and then reappear, even without a browser reload or a Render process restart.

The updated frontend now:

- Keeps the **last valid same-session/same-universe live snapshot** during an interruption of up to **120 seconds**.
- Displays a prominent **DELAYED MARKET DATA — DO NOT TRADE** notice, showing the last tick time; retained data are never labeled live.
- Clears the retained snapshot if the interruption lasts beyond two minutes, or the trading day/universe changes. This prevents indefinite or cross-session stale market signals.
- Prevents overlapping `/api/scan` polls; aborts an unresponsive request after 12 seconds.
- Resumes the normal LIVE indicator automatically once new live data arrive.

This patch is strictly a **data display resilience** fix, not a cure for underlying Kite disconnects, Render process restarts, or API errors. During a disconnected feed, values can be stale and **must not be used to make trade entries**. The Python backend and scoring formulas are unchanged.

Extra frontend resilience test (requires Node.js):

```bash
node tests/test_stable_polling.mjs
```

## Browser tab switching / 5-second polling (2026-10-27)

This version adopts the auto-refresh mechanism observed in the provided reference `outputs (3)(1).zip`:

- The browser fetches `/api/scan` immediately and attempts a new request **every five seconds** whether the Trend Hunter tab is **visible or hidden**; `document.hidden` does not suppress the scanner poll.
- The previous separate `GET /api/health` timer (every 60 seconds when hidden) has been removed. Only the existing main scan polling is used.
- The existing in-flight request guard and 12-second timeout still prevent overlapping or stuck scanner requests. Transient failures retain a recent snapshot clearly marked **DELAYED — DO NOT TRADE**, subject to the original two-minute freshness limit.
- Returning to the Trend Hunter tab triggers an immediate full scan and, when selected, Continuation Radar refresh. Continuation Radar's separate 15-second **visible-tab-only** polling is unchanged to avoid unnecessary heavy calculations in a hidden tab.
- **Important:** Background browser timers are best-effort. Chrome/other browsers can throttle or suspend timers, especially on mobile, battery saver, or sleeping devices. Any incoming requests that actually arrive may reset Render Free's idle countdown, but this **does not guarantee** the service stays awake, nor prevent restarts for other reasons. For continuous unattended market scanning, use an always-on host.
- Removing `render.yaml` only removes the bundled Blueprint configuration. Any existing Render deployment settings must be changed manually in Render's dashboard.

Run the related checks with:

```bash
node tests/test_background_refresh.mjs
node tests/test_stable_polling.mjs
```
