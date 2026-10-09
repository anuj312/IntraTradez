# Trend Hunter – Fit-to-screen layout

The outer browser document and `.main` do not scroll vertically. The
workspace uses `100dvh` and flex/grid minmax(0,1fr) sizing. The Gainers/Losers,
Volume Ratio, and % Change pairs have independent scrollable stock tables;
all top 15 stock rows remain available. The number of immediately visible rows
adapts to screen height (it is no longer always seven on a short laptop).
The Sector Flow graphic also fits its view with an internal scrolling area
when necessary. Mobile navigation and filtering are compact to prioritize
stock visibility on smaller screens. CSS is embedded into the single served
HTML via `python scripts/sync_premium_css.py`.

No backend or market-scoring logic has changed. Use the entire `outputs` folder
when updating a deployed copy of the app.
