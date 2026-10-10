# Trend Hunter — Black Label Private Entry + Metal Lifetime Pass

## Member experience (Google authentication first)

1. **Before Google login:** the members-only scanner stays blurred. Visitors see an exclusive Google sign-in panel. The membership offer and price are hidden.
2. **After Supabase Google login:** the app calls its existing `/api/membership/me` server endpoint. Pending members see a metallic debit-card-inspired **Trend Hunter Black Label Lifetime Access** visual, with their Google profile name and the ₹4,999 membership price.
3. **During sandbox testing:** the UI explicitly says **TEST MODE — NO REAL CHARGE**. The test Razorpay Standard Checkout opens using the existing `/api/create-order` and `/api/verify-payment` endpoints. Only verified test membership entitlement unlocks the scanners.
4. **Already active:** the backend-confirmed active membership unlocks all four scanners directly. No repeat checkout screen is presented.
5. **Sign out:** the app closes access and returns to the Google sign-in step.

## Files changed

- `intraday-momentum-scanner.html` — accessible, two-stage member interface and consistent auth-state switching in all four radar gates.
- `membership-elite-card.css` — editable source for Google sign-in and premium metallic member card.
- `premium-terminal.css` — merged presentation layer, synced into standalone HTML.
- `tests/test_staged_luxe_membership.py` — state, styling, and sandbox regression checks.

## Deployment

The existing `google_test` mode and Supabase/Razorpay **test** keys work without any new database tables or backend changes. Set `MEMBERSHIP_AUTH_MODE=google_test`, `ALLOW_LIVE_RAZORPAY=false` and keep your Supabase and `rzp_test_` credentials in Render's secret environment. Deploy the included `outputs/` project normally. No API keys are included in the ZIP.

The metallic design is a **membership pass illustration**, not a stored payment card. Live payments remain disabled. Google OAuth redirects require the correct Google Cloud and Supabase configuration.
