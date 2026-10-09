# Trend Hunter — Sector Flow + six-row stock windows

## Sector Flow
- Bar plot expands to use the remaining screen height rather than reserving a fixed 130/320px chart area.
- The green and red bar lengths are percentages of the live plot height, preserving the existing common normalization and auto baseline (30%–70%).
- Sector labels appear at the base of the expanded plot; light grid guides aid comparison.
- Sector popup click, momentum badges and %CHG / VolmRatio / Score sorting are unchanged.

## Stock leaderboards
- On standard desktop and laptop screens, show exactly six stock rows below the sticky header, then scroll within the individual stock list. Up to 10 stock rows remain.
- Same change covers Top Gainers and Losers, Volume Ratio, and % Change.
- On ordinary-height phones, six rows fit when physically possible; very short phones show fewer rows rather than cropping content or allowing the outer page to scroll.
- Main page keeps the one-screen non-scrolling layout, and `numbers.txt` authentication is preserved.

## Deployment
- Copy the `outputs/` contents into the existing application and use the existing start command / Render service.
- No new dependencies or authentication changes.
