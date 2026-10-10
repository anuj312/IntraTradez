# Sector Stocks — premium momentum status badges

The Sector Pulse constituent dialog now displays compact premium status chips alongside each stock name. The status changes **presentation only**: momentum score, snapshots, classifications, login, live updates, and TradingView row navigation remain unchanged.

| Status | Design | Meaning |
|---|---|---|
| Accelerating | Emerald green / upward arrow | 5-minute momentum score delta >= +4 |
| Steady | Violet / dot | Score change within +/- 4 points, or an insufficient 5-minute history |
| Fading | Amber / downward arrow | 5-minute momentum score delta <= -4 |
| Stale | Rose / clock | An observed quote is older than the backend's configured tick freshness threshold (overrides score status only in the popup) |
| Waiting | Neutral slate | No live quote and no momentum state yet |

The labels use pill-shaped gradients and subtle elevations in both light and dark themes. On screens narrower than 600px the badge stacks underneath the name. Hovering provides a short status explanation. Reduced-motion preference disables badge motion.

Edit `premium-terminal.css` and run `python scripts/sync_premium_css.py` to sync the embedded stylesheet in `intraday-momentum-scanner.html`.
