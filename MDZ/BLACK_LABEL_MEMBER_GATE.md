# Black Label — Registered Mobile Number Access Gate

## Display behavior

- The Top Gainers/Top Losers, Volume Ratio, % Change, and Sector Flow views have a premium locked preview before login.
- The preview contains only synthetic shapes. No live row values are embedded in it.
- Each view includes the existing registered-number login and private-group link.
- Valid `numbers.txt` login removes the lock and loads live data.
- Logout, expiration, and failed session verification restore the blur and clear cached stock rows. Late API responses after logout are discarded.
- No changes to Kite scanning calculations, sector scoring, mobile Sector Flow bar count, desktop fixed-height layout, or internal leaderboard scroll limit.

## Backend and important security qualification

- `/api/scan`, stock charts/candles, replay, and futures data continue to require an active server-side `numbers.txt`-validated session, not just a client CSS class.
- This is the existing **phone-number allowlist login** (no SMS/OTP), as requested. An approved phone number by itself does **not** prove the person owns it. Someone who knows an allowed number may be able to log in. For identity verification beyond the allowlist, use an additional proof-of-ownership factor in a separate future change.
- Keep `numbers.txt` and any Kite tokens out of public source repositories and publicly served static directories.
