# Trend Hunter — upgraded scanner

**Dashboard note (2026-10-08):** The Live Signal Intelligence strip and its Replay 5m / Futures OI controls have been removed from the dashboard. The underlying analytics and optional backend endpoints remain available, but are no longer displayed as a card. Top Gainers/Losers, Volume Ratio, and % Change remain 7-row scrollable leaderboards (up to 15 each).

## What changed

- **Market candles:** KiteTicker cumulative-volume ticks are converted into 5-minute OHLCV buckets. Only completed candles are saved to indicator history. A current, incomplete candle is used in live indicator calculations but is not persisted as a finished candle.
- **One seed + incremental recovery:** First startup downloads 45 calendar days of 5m bars and 120 days of daily bars. A complete snapshot is saved to `SCANNER_DATA_DIR/history-cache.pkl` after seeding, refreshed every five minutes and when sessions roll. Later startup and market-day reconnects fetch *missing* bars rather than reloading all the same old history. The restored original Render setup has no mounted disk; use SCANNER_DATA_DIR and mount storage separately if you want persistence across restarts.
- **Time-matched volume:** Prior-session 5m cumulative volume, with a 30-trading-session median and a minimum of five sessions, determines `timeVolumeRatio`. Without sufficient baseline, the internal neutral fallback is 1; consider this an unavailable/low-confidence baseline, not strong evidence of normal activity.
- **Sectors:** NIFTY 50 is an index membership list, not a primary industry sector. A stock may belong to multiple filters. Sector Pulse calculates independent up/down participation, mean % change, mean volume ratio, signed score, leaders, and supports clicking for all group members.
- **Sector constituents:** Click any sector bar to see stock names, volume ratios and momentum scores. The intrusive stock-name hover candlestick chart and diagnostic text have been removed. Clicking a stock row still opens TradingView.
- **Intelligence:** 5-, 15-, and 30-minute momentum; score acceleration over elapsed 5/15/30min snapshots; one-way consistency/pullbacks; ORB 15m and previous-day range crossings requiring relative volume confirmation; and explanations of weighted score components. Indicators are estimates; they are not trading recommendations.
- **Depth vs execution:** `depthImbalance` is the resting top-five bid/ask quantity imbalance. It is **not** true aggressor-side executed volume. Deprecated `buySellDelta` is null.
- **Live integrity:** UI stays blank/offline until authenticated real data arrives. Show last tick time and separate live/previous-session/seeding statuses. No fabricated live feed.
- **Backtesting:** `/api/replay` uses already-seeded historical 5m candles to replay a historical day, with simplified score and forward 5/15/30m percentage returns **as evaluation labels only**. This is not a historical reconstruction of the live tick score or order flow; it does not calculate fills, transaction costs, slippage, or out-of-sample statistical significance.
- **Optional near-expiry futures:** `ENABLE_FUTURES_OI=true` fetches FUTSTK instruments (NFO) and subscribes their full quote to monitor price/OI movements. Classification baseline is the **first observed tick of the market session**, not necessarily yesterday's official OI. Do not confuse it with a verified exchange-level institutional net position.
- **Authentication (restored):** `numbers.txt` allowlist only, as in the original project. Users enter their registered phone number; the original per-phone single-active-session ID mechanism is retained. **No OTP, SMS, Twilio or cookie-based authentication.** Phone number knowledge alone is not identity verification.

## Trend Hunter / SPECTRA premium interface

The scanner includes a new premium trading-terminal skin with midnight-blue backgrounds, lavender/cyan details, positive/negative market accents, responsive KPI and leaderboard cards, a polished sector constituent dialog, and a refined phone-number login surface. The light/dark toggle is preserved; it starts in dark mode unless the browser previously selected light. `numbers.txt` remains the only login allowlist.

To customize the design, edit `premium-terminal.css` then run `python scripts/sync_premium_css.py`. The script embeds the CSS in `intraday-momentum-scanner.html`, avoiding any need to change the original Flask routes or Render configuration.

## Leaderboard scrolling

Top Gainers/Losers, Volume Ratio, and % Change show **seven stocks at once** in a fixed-height scrollable table. Scroll inside either column to see positions 8–15, up to **15 qualifying stocks per side**. The column header stays visible while scrolling, and the scroll position is preserved across live refreshes. Columns maintain equal visible height; when one side has fewer results, muted placeholder rows keep alignment (these are not market results). The original phone-number allowlist (`numbers.txt`) remains unchanged.

## Getting started locally

1. `python -m pip install -r requirements.txt`
2. Add Kite credentials to environment: `KITE_API_KEY`, `KITE_ACCESS_TOKEN`.
3. Create `numbers.txt` with approved 10-digit mobile numbers, one per line. Never commit or publicly serve this file.
4. `python live_scanner_server.py` then open `http://localhost:8050`. Enter a number listed in `numbers.txt`. No SMS or OTP is required.

## Render deployment (original configuration restored)

- `render.yaml`, `app.py`, `requirements.txt` and `requirements-live.txt` are restored from your **original ZIP**. The original Render configuration uses `rootDir: outputs` and a Uvicorn command, with no mounted disk and no Twilio variables.
- **Known issue preserved at your request:** the original Uvicorn start command may not work with the exported Flask WSGI application. The original `requirements.txt` also does not include Uvicorn; deployment needs separate verification before use. You may need your previous repository folder layout (`outputs/`) or to adjust the Render root directory.
- The `numbers.txt` login and original one-active-session-per-number behavior require a **single application process**. No change to multi-instance scaling has been made.
- The Kite access token must be refreshed as required by Zerodha. Render filesystem storage remains ephemeral in this original configuration. Keep `.runtime`, `.env`, and `numbers.txt` private.

## API (authenticated)

- `POST /api/access/login` with `{"phone":"<registered_phone>","session_id":"<client_session_id>"}`
- `POST /api/access/logout` with the same phone and session_id fields
- Authenticated requests need `access_phone` and `access_session_id` query parameters, exactly like the original scanner:
  - `GET /api/scan?type=intraday&universe=stocks&sector=ALL&limit=2000&access_phone=...&access_session_id=...`
  - `GET /api/stock/RELIANCE/candles?access_phone=...&access_session_id=...`
  - `GET /api/replay?symbol=RELIANCE&date=2026-10-07&access_phone=...&access_session_id=...`
  - `GET /api/futures?access_phone=...&access_session_id=...` (optional NFO subscription)
- `GET /api/health` (feed and seed status, no access tokens)

## Known limits and precautions

- Test Kite API request quotas, exchange holidays, trading session short days, corporate actions, ticker disconnections and late/out-of-order ticks with a real market feed. Calendar weekdays alone don't identify exchange holidays. Tick-built OHLCV after reconnects may not reflect movements during a missing interval until recovery has completed.
- A baseline with fewer than five previous sessions is treated as neutral. Freshness checks are per-stock; always check `fresh` and `asOf` before acting.
- The original number-only login verifies allowlist membership, **not phone ownership**. It is unsuitable for high-security access without extra identity verification. Session locks live in process memory and reset on restart.
- The historical replay stores only cached history; dates not in the cache return no observations, and forward labels are never used in replay score.
- This software is a research dashboard, not an order-execution or autonomous trading bot.

## Offline validation

`python -m pytest -q tests` runs pure candle/volume/one-way/replay tests. Use `node --check` on extracted inline dashboard JS. Install requirements to run full Flask route integration tests and verify against Zerodha sandbox/live entitlements.

### Paired leaderboard layout
All three leaderboard views display seven rows at a time with an independent vertical scrollbar on each side. Each side contains at most 15 qualifying stocks; ranking and live-data source are unchanged. The fixed 7-row viewport keeps the paired columns aligned; fewer actual stocks appear with noninteractive muted placeholders when needed. On mobile the pair stacks, each retaining its own 7-row scroll viewport.
