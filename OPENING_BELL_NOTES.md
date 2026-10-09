# Trend Hunter — 09:15 Live Opening-Bell Upgrade

## What is new

- **Before 09:15 IST:** Render worker starts its Kite session / NSE instrument load / ticker immediately on worker boot, rather than on the first visitor request. Cached historical candles are loaded once when available; otherwise a background history seed begins. The ticker connection is initiated before the slow seed.
- **From the first valid 09:15 tick:** the scan endpoint merges current LTP and % change from the WebSocket directly into the rankings, even when no historical candles exist yet. This does not wait for the first completed 5-minute bar.
- **09:15–09:20:** scores display without a `~` prefix; provisional status is still available in the score hover tooltip. With a historical baseline, the existing composite scoring continues. Without history, a separate quote-only provisional estimate is used; missing RSI, ADX and volume ratios are shown as unavailable, not invented.
- **At 09:20 and subsequent 5-minute boundaries:** the previous 5-minute candle is finalized and exposed separately as `lastCompleted5m` with its actual close, price-change percentage, and price-only momentum strength score. The next candle's *live composite score* remains provisional until its own completion; the two scores are not represented as interchangeable.
- **Live traded volume:** cumulative Kite volume is included in each row. While historical volume ratio is unavailable, leaderboard cells show clearly labeled raw `Vol ...` values rather than a fabricated ratio.
- **3-second frontend polling:** live quote fields are refreshed on the request path, independently of the slower 8-second indicator computation. During market hours scan responses use `Cache-Control: no-store` so unchanged cache ETags cannot hide new prices.
- Historical seeding preserves any already-closed bars captured by WebSocket. Only complete bars are committed; the building candle is separate.
- Authentication: old `numbers.txt` allowlist login and existing endpoints are unchanged. The Kite token is validated once before a seed; expired tokens produce one clear diagnostic instead of hundreds of per-stock history failures.

## Simplified live display (2026-10-09)

- Momentum scores show numeric values without the `~` prefix. This is visual only: provisional computation and API status remain unchanged.
- The live subheading is `Live / N detailed / M watched`, populated from the server's `detail_symbols` and `universe_size` fields. No last-tick time, previous-candle price-strength, or provisional text is printed in the subheading.

## Deployment

Your `render.yaml` keeps `rootDir: outputs` and starts `uvicorn main:app` (workers=1). `main.py` now supplies a proper ASGI wrapper around the existing Flask app. Put the included project files in the existing repository `outputs/` directory and keep existing Render environment variables (`KITE_API_KEY`, `KITE_ACCESS_TOKEN`). The `requirements.txt` now includes `asgiref` and `uvicorn`.

For a stable premarket warmup, your Render service needs to be running before 09:15, and a valid *today's* Kite access token must be available. This release does not generate/renew the Kite access token; change the environment token and restart/redeploy according to your existing credential workflow. Do not place Kite keys or access tokens into code, HTML or `numbers.txt`.

**Caveat:** The source used for this release was your latest stored `Trend_Hunter_Premium_Without_Live_Signal_Panel.zip` (Flask backend). Your separate Render logs referenced a FastAPI-based `main:app`; if the Git repository currently uses different backend files, merge/adapt these changes rather than replacing unrelated code blindly.

## Quick health check

- Before 09:15: `GET /api/health` should show loaded NSE instruments and a connected/connecting ticker if credentials are valid.
- 09:15+: `GET /api/health` should report tick counts increasing; authenticated `/api/scan` should return `quote_first: true`, today's LTP rows and `scoreStatus: provisional` without waiting for a 5-minute close.
- At/after 09:20: after the bar closes, rows contain `lastCompleted5m.end` ending at `09:20` and a separately labeled `priceMomentumScore`. At 09:25, the next 5-minute bar is committed.
- In historical-data failures, price tick rows can still appear. RSI, ADX and volume ratio are withheld until history is available.

## Tests

`python -m pytest -q` (all tests) and JavaScript `node --check` on the extracted inline script. Live Kite authentication and Render deployment cannot be exercised offline.
