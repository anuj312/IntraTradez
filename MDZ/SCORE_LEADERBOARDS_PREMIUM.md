# Aurora Board — Gainers / Losers Premium CSS

This version restyles the **Top Gainers by Score** and **Top Losers by Score** dashboards only.

- Two premium, independent leaderboard surfaces with emerald and rose accents
- Distinctive arrow medallions in the panel headers
- Refined heading typography and average-volume indicator pills
- Ranked stock avatars (01–10) using CSS counters, preserving original data templates
- Subtle first-place highlight, stock-row surfaces, and interactive hover/focus styling
- Cleaner score emphasis and subtle score underlines
- Light and dark palettes; compact phone rendering preserved

**Preserved:** The existing score calculation, sorting, login, data feeds, main-page no-scroll layout, mobile Gainers/Losers toggle, and 6-visible / 10-total internal scroll are not changed.

The stylesheet is embedded in `intraday-momentum-scanner.html` via `scripts/sync_premium_css.py`, and the authored source lives at the end of `premium-terminal.css` as well as `score-leaderboard-premium.css`.
