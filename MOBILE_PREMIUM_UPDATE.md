# Trend Hunter — Premium Responsive Mobile Release

### Included
- Compact fixed-height phone/tablet navigation and hero header; the document itself does not scroll.
- Phone-friendly direction filter, symbol search, and expandable filters.
- Separate full-height `Gainers` / `Losers` tabs for each of Momentum, Volm Ratio, and % Change; scroll independently through the top 10 without changing the underlying scanner.
- Six visible rows where phone height permits, otherwise retain a comfortable minimum row size with internal scrolling.
- Horizontal swipe of Sector Flow bars; tapping bars still opens sector stock popup.
- Touch-friendly sector stocks modal, premium dark/light support, mobile logout, and safe-area padding.
- Desktop CSS remains unchanged outside the new responsive styles.

### Testing
- 47 regression tests passed.
- JavaScript syntax checked.
- Chromium viewport emulation checked at 375x667, 390x844, 430x932, 768x1024, 820x1180, and 1440x900.
- Verified no outer page scroll / no horizontal overflow, independent list scroll to item #10, Gainers/Losers tabs, filter expansion, sector modal, dark-theme toggle.
- Browser viewport checks are not a substitute for a real-device Safari/Android Chrome test.

### Deployment
- Deploy `outputs/` as you did for the previous ZIP.
- Keep the existing backend `numbers.txt` login, API keys and Render config. Do not expose secrets publicly.
