# Trend Hunter — Razorpay Standard Web Checkout (₹4,999 TEST Mode)

This build uses the existing **Python Flask** payment implementation inside `member_payments.py` and `live_scanner_server.py`, served on Render via the `main.py` ASGI adapter. It does **not** create a second payment system and does not change stock-scanner calculations or existing Supabase schemas.

## 1. Install and configure local environment

From the `outputs/` directory:

```sh
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` **locally only**. Set `MEMBERSHIP_AUTH_MODE=google_test`, the 3 Supabase variables, `RAZORPAY_KEY_ID=rzp_test_...` and `RAZORPAY_KEY_SECRET=...`. Set `ALLOW_LIVE_RAZORPAY=false`. Use your **own fresh** test credentials. The `.env` file is intentionally excluded from Git and the distributed ZIP. Never commit or share it.

You do **not** need to install the extra Razorpay SDK: this codebase already calls Razorpay's REST API through the `requests` dependency. `python-dotenv` is included for local `.env` loading; Render's environment variables take priority.

## 2. Supabase (already set up in your project)

Enable Google under **Authentication → Providers → Google**. In Supabase SQL Editor, the existing `SUPABASE_GOOGLE_ONLY_SETUP.sql` and `SUPABASE_RAZORPAY_TEST_SETUP.sql` initialize Google identities and sandbox payment tables. **Do not rerun SQL scripts if you have already run them successfully.** Test records remain in `th_test_memberships` / `th_test_payment_orders`; they do not activate live memberships.

## 3. Render environment

In Render → your web service → **Environment**, set:

```env
MEMBERSHIP_AUTH_MODE=google_test
ALLOW_LIVE_RAZORPAY=false
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=YOUR_ANON_JWT
SUPABASE_SERVICE_ROLE_KEY=YOUR_PRIVATE_SERVICE_ROLE_JWT
RAZORPAY_KEY_ID=rzp_test_YOUR_FRESH_TEST_KEY
RAZORPAY_KEY_SECRET=YOUR_PRIVATE_TEST_SECRET
```

Optionally configure `RAZORPAY_WEBHOOK_SECRET` and a Test Mode webhook at `https://YOUR_RENDER_DOMAIN/api/membership/webhook`. The Checkout success path can verify captured payments without a webhook. Supabase service-role and Razorpay secret are backend-only. This test-only release also rejects live charging even if someone mistakenly configures `MEMBERSHIP_AUTH_MODE=google` or supplies `rzp_live_` keys.

## 4. Checkout request/response

The existing **Try ₹4,999 Test Checkout** button uses the Razorpay `https://checkout.razorpay.com/v1/checkout.js` Standard Checkout modal.

**POST `/api/create-order`** (legacy alias: `/api/membership/order`), with a Supabase Google `Authorization: Bearer <access_token>` header. Body may be `{}` or `{"amount":499900,"currency":"INR"}`. The backend validates that `amount` is at least 100 paise and **exactly** 499900 paise for this membership. It **generates its own receipt**. Returns `{ "order_id": "order_...", "amount":499900, "currency":"INR", "key":"rzp_test_...", "name":..., "email":..., "test_mode":true }`. The `key` is a public test key ID; the secret is never returned.

**POST `/api/verify-payment`** (legacy alias: `/api/membership/verify`). Body:

```json
{
  "razorpay_order_id": "order_...",
  "razorpay_payment_id": "pay_...",
  "razorpay_signature": "64_hex_characters"
}
```

The server first validates HMAC-SHA256 of `order_id + "|" + payment_id` using the **private** key secret with `hmac.compare_digest`. It then checks the order belongs to the signed-in Google user, and **fetches the payment from Razorpay to require captured status, INR and the correct ₹4,999 amount**. Only then is the test membership activated in Supabase. Payment failures / modal dismissal do not unlock the scanner.

| Situation | Expected API response |
|---|---|
| Missing/invalid Google session | 401 |
| Amount below 100 paise or not exactly 499900 | 400 |
| Missing Checkout verification fields | 400 |
| HMAC signature mismatch | 400, never activate |
| Razorpay invalid test key/secret | 401 |
| Other Razorpay API error | 500 |
| Uncaptured payment | 409, no activation |

## 5. Test

1. On Render deploy, open `https://YOUR_RENDER_DOMAIN/api/membership/config` and confirm `"mode":"google_test"`, `"test_mode":true`, `"configured":true`, and `"real_payments_enabled":false`. Do **not** paste secret keys into the browser.
2. Open Trend Hunter and use **Continue with Google**. The four protected radars should stay blurred while the membership is pending.
3. Click **Try ₹4,999 Test Checkout**. Confirm Razorpay opens in **Test Mode**, with amount ₹4,999.
4. Use Razorpay's documented test payment methods to simulate payment success. After backend verification, the four radars unlock and Desk View shows the Google name with **TEST MEMBER · DEMO ONLY**.
5. Sign out and sign in again; test membership should persist. Review records in Supabase `th_test_memberships` and `th_test_payment_orders`.
6. Test a failed payment and modal dismissal. Both must **not** activate a membership.
7. Run `python -m pytest -q` from `outputs/` for automated tests.

**Safety:** Razorpay credentials supplied in a chat should be considered exposed. Regenerate the Test Key Secret in Razorpay and update Render/local `.env`. Do not enable production checkout until a separate live-payment review.
