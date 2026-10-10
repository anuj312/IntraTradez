# Trend Hunter — Kite Historical Gap-Recovery Date Fix

## Issue
After starting the server with a saved historical cache, gap recovery failed for every NSE symbol with `kiteconnect.exceptions.InputException: invalid from date`.

## Root cause
A cached pandas `Timestamp` was passed directly to `kite.historical_data()` as `from_date`. The Kite Python client formats native `datetime.datetime` objects but passes a `pandas.Timestamp` through without formatting, which can include a timezone suffix and fail the historical-data API's expected `YYYY-MM-DD HH:MM:SS` format.

## Fix
- Added `_kite_history_datetime`: normalize pandas and native timestamps to **native** Python `datetime` values in IST, without timezone suffixes.
- Added `_completed_history_cutoff`: clamp last completed 5-minute boundary to NSE market hours, and use the previous weekday close before the first completed candle or on weekends.
- Skip duplicate intraday recovery requests when the cache already includes the last completed candle.
- Converted both 5-minute and daily incremental recovery date arguments.
- Reduce repeated log noise if the provider rejects many calls simultaneously.

## What has NOT changed
- No changes to Kite credentials, Render configuration, scanner algorithm, frontend CSS, registration, `numbers.txt`, login, or stock universes.
- No new dependency is required.

## Validation
`python -m pytest -q` → 65 tests passed, including 5 date-specific regression tests.

## Deploy
1. Back up your existing project and replace its `outputs` files with the files in this ZIP.
2. Rotate the exposed Zerodha access token and set the new value as `KITE_ACCESS_TOKEN` in Render environment settings (or locally).
3. Restart Render and verify the log shows cache loaded and a successful catch-up rather than 198 `invalid from date` errors.
4. The market has already closed at 18:39 IST; live ticks resume on the next trading session. Historical catch-up is separate from live updates.
