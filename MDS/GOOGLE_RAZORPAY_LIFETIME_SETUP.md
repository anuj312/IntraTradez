# Trend Hunter — Google sign-in + ₹4,999 lifetime membership

## What changes

- Google verifies the visitor's identity with Supabase Auth.
- A new Google user sees **Lifetime Access ₹4,999** over the blurred scanner.
- The Render backend creates a Razorpay order for exactly **499900 paise** (INR ₹4,999).
- Checkout success is **not** access: the backend verifies Razorpay's signature, fetches the payment from Razorpay, checks `captured`, order ID, amount and currency, then saves `active` status and `paid_at` in Supabase.
- A verified member can access Top Gainers/Losers, Volume Ratio, %Change, Sector Flow, charts, replay and futures without paying again.
- Desk View shows the Google profile name (and `LIFETIME PRO MEMBER` on active membership).
- Member data survives Render redeployments/restarts. Legacy `numbers.txt` login remains the **default**; setting `MEMBERSHIP_AUTH_MODE=google` explicitly disables the phone login and phone bypasses.

## Setup (required before processing actual payments)

1. Create a Supabase project and run `SUPABASE_MEMBERSHIP_SETUP.sql` in its SQL Editor.
2. In Supabase **Authentication > Providers > Google**, enable Google and paste Google OAuth Client ID + Secret created in Google Cloud Console. Add the Supabase Auth callback URL shown by Supabase to Google Cloud's authorized redirect URIs (normally `https://YOUR_PROJECT.supabase.co/auth/v1/callback`). In Supabase **Authentication > URL Configuration**, set your Render site's URL and add `https://YOUR_RENDER_SITE.onrender.com/**` to redirect allow-list. Add local URL when testing.
3. Create a Razorpay merchant account, finish activation/KYC for live checkout, and generate **Test Mode** API Key ID and Secret. Later use your live keys for production. Under Razorpay Webhooks, add `https://YOUR_RENDER_SITE.onrender.com/api/membership/webhook`, select **payment.captured**, and set a separate webhook secret.
4. In Render **Environment**, add (keep secrets secret):

   | Variable | Example / requirement |
   |---|---|
   | `MEMBERSHIP_AUTH_MODE` | `google` |
   | `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` |
   | `SUPABASE_ANON_KEY` | Supabase public/publishable/anon key |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase secret service-role key (**server-only**) |
   | `RAZORPAY_KEY_ID` | Razorpay key ID |
   | `RAZORPAY_KEY_SECRET` | Razorpay key secret (**server-only**) |
   | `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook signing secret (**server-only**) |

5. Redeploy Render with **one worker**, test Google login and a Razorpay **Test Mode** payment, then check `public.th_memberships` (`status='active'`, `paid_at` populated) and `public.th_payment_orders`. Verify that logout, new browser sessions, expired credentials and server restart work as expected.
6. Switch to live Razorpay keys ONLY when tests pass; configure a live webhook too. Keep separate test vs live records or projects where possible. Discuss your refund policy, taxes/invoicing and lifetime service terms before going live.

## Important safety notes

- `SUPABASE_SERVICE_ROLE_KEY`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` must remain on Render, never in HTML or GitHub.
- A user who merely clicks Google or opens checkout stays locked. Only a verified captured payment or an explicit administrator-set active entitlement unlocks the APIs. Client-side manipulation cannot grant access.
- If webhook processing temporarily fails, member can retry the verify step from checkout or contact support; keep Razorpay and Supabase records for reconciliation.
- Free Supabase/Auth limits are subject to provider terms. Razorpay charges transaction-processing fees; payment processing is not free even though implementing a login button can be free.
- This package is **not live-connected yet**: account IDs/secrets, provider callbacks and live payment test are required.
- Existing user accounts from `numbers.txt` are **not automatically granted paid Google access**. Owner must migrate/approve them separately if desired.
- Never use front-end code to set `status='active'`; entitlement is server-controlled.
