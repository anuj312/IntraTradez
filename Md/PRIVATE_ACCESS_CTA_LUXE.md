# Trend Hunter Black Label — Private Access CTA Luxe

A presentation-only refinement of the "Not yet a member?" area in all four
member-gated views: Momentum Radar, Sector Flow, Volume Radar and % Change.

## Design updates
- Premium violet/navy glass group-access link with mint-violet illuminated edge
- Decorative star icon and elevated external-link arrow
- Refined divider and trust/approved-number note
- Hover, focus-visible, touch-friendly and reduced-motion states
- Compact treatment for mobile and shorter displays

## Security/behavior unchanged
- Approved numbers continue to be loaded from `numbers.txt`.
- Existing login and logout endpoints, form submission logic and protected data remain unchanged.
- Existing private group URL remains unchanged.

`private-access-cta-luxe.css` is an editable source layer. Its CSS is also
embedded at the end of `premium-terminal.css` and synchronized into the single
`intraday-momentum-scanner.html` file used by the application.

To resync after editing `premium-terminal.css`, run
`python scripts/sync_premium_css.py` from the `outputs` directory.
