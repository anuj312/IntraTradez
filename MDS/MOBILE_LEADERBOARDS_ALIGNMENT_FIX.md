# Mobile Volume Ratio and % Change alignment fix

- Fixes an inherited desktop/mobile CSS specificity conflict that caused gainers and losers to display simultaneously in the same mobile grid cell.
- Displays one selected leaderboard at a time with working gainers/losers tabs for **both** Volume Ratio and % Change.
- Assigns dedicated three-column and four-column mobile layouts; truncates long stock names within their own cells instead of painting across adjacent metrics.
- Provides short mobile labels for `% Change` metrics while retaining the original semantic table headings.
- Fits the four mobile navigation tabs alongside the brand icon on compact screens, and scrolls the active tab into view on other mobile widths.
- Preserves existing ten-stock lists, scroll behavior, member login, Black Label styles, daily data processing and gap-recovery fix.
