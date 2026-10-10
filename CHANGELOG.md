## Google + Razorpay TEST Mode — ₹4,999 simulated membership

- Added opt-in `MEMBERSHIP_AUTH_MODE=google_test` Google login + Razorpay sandbox checkout.
- Only `rzp_test_` keys are accepted; live charging is disabled unless explicitly opted in with separate production credentials and mode.
- Sandbox purchases are verified server-side then saved in isolated `th_test_memberships` and `th_test_payment_orders` tables. They do not create real lifetime memberships.
- Added Black Label `TEST MODE · NO REAL CHARGE` banner and `TEST MEMBER · DEMO ONLY` profile status.
- Preserved the scanner, member access gates, responsive mobile layout and existing `google_free` / phone modes.
- Setup files: `RAZORPAY_TEST_MODE_SETUP.md`, `SUPABASE_RAZORPAY_TEST_SETUP.sql`.

## Trend Hunter — clean live subheading and scores (2026-10-09)
- Removed `~` prefix from provisional scores in all momentum leaderboards while retaining hover context and unchanged calculations.
- Live status now reads `Live / N detailed / M watched` with actual server counts; removed candle timestamp, price strength, provisional text and last-tick timestamp from the live subheading.
- No auth, market feed, candle logic or backend changes.

## Trend Hunter — removed Live Signal Intelligence panel (2026-10-08)
- Removed the entire Live Signal Intelligence panel, leader chips, Replay Date/Symbol fields, Replay 5m button, Futures OI button and results area.
- Deleted panel-only browser event handlers, rendering logic and styling. No hidden placeholders remain; the summary cards move directly beneath the filters.
- Kept all Gainers/Losers, Volume Ratio and % Change leaderboards at 7 visible stocks and 15 scrollable positions, plus green/red LTP % styling.
- Kept the `numbers.txt` login, Sector Pulse, backend market calculations, historical APIs and original Render files unchanged.

## Trend Hunter — seven visible rows / fifteen ranked stocks (2026-10-08)
- Top Gainers/Losers, Volume Ratio, and % Change each now display exactly 7 row slots before scrolling.
- Each column contains a maximum of 15 live-ranked stocks. Gainers/Losers and Volume Ratio previously allowed more than 15.
- Both sides have matched viewport height; independent visible thin scrollbars, sticky headers, and keyboard accessibility.
- Maintains scroll position during live refresh, and green/red LTP % coloring remains intact.
- No login, backend calculation, market feed, or deployment changes.

# Upgrade summary

The upgrade preserves the existing NSE cash scanner and Sector Pulse layout while adding:

1. Completed 5-minute KiteTicker OHLCV candles, per-token volume increments, incremental reconnect/backfill, persistent snapshot save and 30-session time-matched volume ratio caching.
2. Multi-sector stock membership and NIFTY 50 as an index membership group, with correct stock selection and pulse participation.
3. (Later removed from the UI.) Stock-name hover candlestick charts and diagnostic text; the separate backend candle/history features remain available for market analytics.
4. Score acceleration history, one-way direction/pullback detector, prior-high/low and opening 15m breakout labels with volume confirmation.
5. Simplified historical replay API and optional FUTSTK OI classification retained in the backend (their separate UI panel has been removed).
6. Restored original `numbers.txt` allowlist login with registered phone number and a single active session per number; no SMS OTP/Twilio/cookie-based security. Kept the no-fabricated-live-data improvement.
7. Restored the original `render.yaml`, `app.py`, and requirements/deployment settings without the new Gunicorn/disk changes.

**Not production-verified:** Zerodha live ticks, original Render deployment, visual browser layout, exchange holidays, rate quotas, and load capacity. A high-scale multi-instance market-data architecture and a comprehensive fills/slippage-aware backtest are outside the current single-server implementation.

## Requested rollback
Restored your original phone-number-only login and Render setup; new chart, replay and futures endpoints now use the original phone/session query credentials.

## SPECTRA premium visual redesign

- Added a layered midnight-blue/violet professional trading-terminal skin and corresponding light theme without removing the existing theme toggle.
- Restyled navigation, headings, status chips, search/filters, KPI cards, two-sided market tables, Sector Pulse bars and sector stock popup.
- Polished the original phone-number login surfaces; authentication still only uses `numbers.txt` with the original one-active-session behavior.
- Improved keyboard focus rings, reduced-motion support, and mobile spacing. (The replay/futures control panel was later removed.)
- Added `premium-terminal.css` as an editable source file and `scripts/sync_premium_css.py` to embed it into the HTML, which the original backend serves directly.
- No changes to backend trade calculations, Zerodha credentials, Render config, login behavior or endpoints.

## Trend Hunter branding and simplified tables

- Renamed the browser title, brand/monogram, and main dashboard title to **Trend Hunter**.
- Removed the stock-name hover chart popup entirely, including its candle-fetch logic, chart canvas, diagnostic line, and hover/focus handlers. The Sector Pulse constituent modal, momentum score and TradingView row-click remain.
- Removed independent vertical scrolling and fixed heights from Gainers/Losers, Volume Ratio and % Change tables. The ranked lists expand and use natural page scrolling; mobile retains horizontal panning as needed.
- Original `numbers.txt` login, market calculations, and Render configuration remain unchanged.

## Trend Hunter — LTP percentage coloring
- Gainers, Losers, Volume Ratio, and % Change tables now color each LTP/% Change number green when positive and red when negative, with a neutral style for zero/missing values.
- Fixed dark-theme table-cell CSS precedence so the value coloring stays visible in both themes.
- No changes to login, trading calculations, scanner filters, or Render settings.

## Leaderboard equal-height alignment
- Gainers and decliners now finish at the same height in all three paired views (Score, Volume Ratio, % Change).
- The side with fewer actual qualifying stocks displays muted, non-clickable blank rows after a single “No additional gainers/decliners” explanation. Real stocks are never removed or fabricated.
- Row heights and table headers align, panels expand with their content, and the whole page scrolls instead of clipping bottom rows.
- On small screens where the lists stack vertically, extra alignment-only rows are hidden to avoid unnecessary scrolling.
- Preserved green/red percentage-change coloring, `numbers.txt` access, and the original server/Render files.
