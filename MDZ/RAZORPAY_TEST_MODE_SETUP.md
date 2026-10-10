# Trend Hunter — Google Login + Razorpay ₹4,999 TEST Mode

**Sandbox only:** This build uses `MEMBERSHIP_AUTH_MODE=google_test` and **Razorpay Test API keys**. The ₹4,999 shown on screen is a simulated test order, not a real charge. A successful test payment grants **TEST MEMBER** access to the four radars, charts and related gated APIs. It does not grant a real, production paid lifetime membership.

## 1. Supabase

- Create your Supabase project, enable **Authentication → Providers → Google**, and set up the Google OAuth client with the redirect URL displayed by Supabase (`https://YOUR_PROJECT.supabase.co/auth/v1/callback`). In **Authentication → URL Configuration**, allow your Render site URL and local test URL if needed.
- If you haven't done so, run **`SUPABASE_GOOGLE_ONLY_SETUP.sql`** in **SQL Editor**. This creates the identity/admin-block table.
- Then run **`SUPABASE_RAZORPAY_TEST_SETUP.sql`**. This creates `th_test_memberships` and `th_test_payment_orders`. **Both tables are intentionally separate from live payment records.**
- Keep `SUPABASE_SERVICE_ROLE_KEY` on Render only; it is never sent to the browser. Test members in `th_test_memberships` will **not** become paid members after you switch to live mode.

## 2. Razorpay sandbox

1. Go to <https://dashboard.razorpay.com> and **enable Test Mode**.
2. Under **Account & Settings → API Keys** (exact menu may vary), generate your *Test* Key ID and Test Secret.
3. Your Key ID **must start with `rzp_test_`**. This application refuses other key IDs when `MEMBERSHIP_AUTH_MODE=google_test`.
4. (Optional but useful) Set up a Razorpay **TEST** webhook pointing to `https://YOUR_RENDER_SITE.onrender.com/api/membership/webhook`, with the `payment.captured` event and its own signing secret. Verification from Checkout also works without a webhook.
5. Use Razorpay's documented test payment instruments inside the sandbox checkout. Do **not** enter real financial credentials when testing.

## 3. Render environment configuration

Open your Render service → **Environment** and add/update:

| Key | Value |
|---|---|
| `MEMBERSHIP_AUTH_MODE` | `google_test` |
| `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` |
| `SUPABASE_ANON_KEY` | Your Supabase public / anon JWT key (current backend requires anon-format key) |
| `SUPABASE_SERVICE_ROLE_KEY` | Your Supabase private service-role JWT key |
| `RAZORPAY_KEY_ID` | **`rzp_test_...`** |
| `RAZORPAY_KEY_SECRET` | Razorpay **Test** secret, private |
| `RAZORPAY_WEBHOOK_SECRET` | Test webhook signing secret, optional if verifying from checkout |
| `ALLOW_LIVE_RAZORPAY` | **`false`** (or omit; false by default) |

Save changes and redeploy. Do **not** set `MEMBERSHIP_AUTH_MODE=google` or use `rzp_live_...` for this test.

## 4. Verification checklist

1. Visit `https://YOUR_RENDER_SITE.onrender.com/api/membership/config`. Expect:
   `"mode":"google_test"`, `"test_mode":true`, `"configured":true`, `"price_paise":499900`, `"currency":"INR"`, and a `razorpay_key` beginning with `rzp_test_`.
2. Open Trend Hunter. All protected radars should appear blurred, and the membership card should prominently display **TEST MODE · NO REAL CHARGE** and **₹4,999**.
3. Select **Continue with Google**. The person's name/email are identified by Supabase but they stay locked until test payment succeeds.
4. Select **Try ₹4,999 Test Checkout** and complete a Razorpay Test Mode payment. The server verifies the signature, fetches the simulated *captured* payment from Razorpay and writes to `th_test_payment_orders` and `th_test_memberships`.
5. Once verified, the radars unlock and the Desk View should show the Google name with **TEST MEMBER · DEMO ONLY**.
6. Sign out and sign in again. The test membership should still be active. In Supabase Table Editor inspect the two `th_test_` tables.
7. Run a failed/abandoned test checkout: it must **not** unlock any protected data.
8. Verify that `public.th_memberships` and `public.th_payment_orders` contain **no newly activated production subscriptions** from these tests.

## Payment security and separation

- **Razorpay Checkout events are not sufficient to activate access**. The backend checks order ownership, exact ₹4,999 INR amount, HMAC signature and `captured` state from Razorpay.
- The UI only receives the public test Key ID; service-role and Razorpay secret keys remain server-side.
- The test-mode backend **refuses `rzp_live_` API keys** and production payment processing is disabled in this test-only release regardless of environment variables. Launching real payments requires a separately reviewed build.
- The existing `numbers.txt` phone login cannot bypass the Google test membership gate when the app is configured as `google_test`.
- Test members do not receive real lifetime entitlements. Before launching real payments, separately review pricing, terms, tax invoices, refunds, payment retries and production readiness.
- If test payments are disabled or provider keys are invalid, the application fails closed. It does **not** silently fall back to free Google access.

**Prerequisite:** The Render Kite credentials and market-data backend must be configured independently for live scanner data. Nothing in this change alters market data calculations.
