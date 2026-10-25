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

The existing `render.yaml`, `app.py` (Gunicorn) and `main.py` (Uvicorn) entrypoints remain. Set the two Kite environment variables in your host. Render does not automatically persist runtime files unless a disk is attached.

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
