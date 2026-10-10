# Trend Hunter — Fill empty space below sixth stock row

- The six visible rows now divide up the entire available height inside each leaderboard, rather than stopping at an arbitrary 65px cap and leaving blank space at the bottom.
- All six leaderboards (Top Gainers, Top Losers, Volume Ratio rising/falling, % Change rising/falling) retain a maximum of 10 stocks, with stocks 7–10 accessible by scrolling *inside* each table.
- The main page remains fixed to the viewport and never scrolls.
- CSS `container-type: size` and `100cqh` make the row height respond to the actual table viewport, independent of screen resolution. Small mobile viewports retain a readable minimum row height and may show fewer rows at once.
- Sector Flow, scoring, login, Kite connectivity, and all other features are unchanged.
