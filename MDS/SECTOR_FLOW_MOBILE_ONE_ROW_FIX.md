# Sector Flow — all sector bars on one mobile row

- Fixed the prior hardcoded 14-column grid when 15 sectors were rendered, causing the last `DUR` bar to wrap to a second row.
- Sector Flow sets the CSS variable `--th-sector-count` from the actual number of rendered sectors, keeping all bars and labels in the same row.
- At phone widths, the chart is one unscrollable row; no horizontal or vertical chart scrolling.
- The editable `mobile-premium.css` is consistent with the served embedded `premium-terminal.css`.
- Desktop styling, chart calculations, sorting and sector click-to-open behavior remain unchanged.
- All project Markdown files are consolidated in the `MDS` directory.
