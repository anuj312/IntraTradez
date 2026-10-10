# Trend Hunter — Google Login Only (NO Razorpay)

This ZIP is a complete Trend Hunter build with a separate **Google-only** mode. Users click **Continue with Google**, authenticate via Supabase Auth, and gain access to protected scanner data without any payment. Their Google name and email are saved in Supabase and their name is shown in Desk View. The former lifetime ₹4,999 checkout is **not displayed or enabled in this mode**.

**Important:** In `google_free` mode, **any person with a Google account who signs in may access the scanner**, unless you manually set their `th_memberships.status` to `blocked`. If you want invitation-only access, ask for an allowlist/approval flow before publishing this publicly. The `pending` status here just means a free Google profile, not a payment waiting state.

## 1. Create Supabase project

1. Visit https://supabase.com/dashboard and select **New project**.
2. Name it `trend-hunter` and choose a nearby region (e.g. Mumbai if offered).
3. Wait for provisioning. Copy your project URL (`https://YOUR_PROJECT.supabase.co`).
4. Open **SQL Editor > New query**, paste `SUPABASE_GOOGLE_ONLY_SETUP.sql`, and click **Run**. The table appears as `public.th_memberships`. You do **not** need the payment orders table yet.

## 2. Create Google OAuth app

1. Visit https://console.cloud.google.com/ and create/select a project.
2. Open **Google Auth Platform** > **Branding**. Enter your app name (`Trend Hunter`), support email, audience and contact info. Choose **External** audience if your Google users are outside your Google Workspace organization.
3. In **Audience**, while the app is in Testing, add Google accounts you will use as test users; otherwise Google may block a login. Publish to Production when ready to allow broader logins.
4. Under **Data Access**, confirm the `openid`, `userinfo.email`, and `userinfo.profile` scopes required by Supabase.
5. In **Clients**, create **OAuth client ID** > **Web application**.
6. Under **Authorized JavaScript origins** enter your origin, e.g. `https://YOUR-SERVICE.onrender.com` (no trailing slash/path). For local testing optionally include `http://127.0.0.1:8000`.
7. Under **Authorized redirect URIs**, paste **the Supabase callback URL** copied from Supabase's Google Provider settings, usually `https://YOUR_PROJECT.supabase.co/auth/v1/callback`. **Do not use a Render URL in this Google callback field.**
8. Save the generated Google **Client ID** and **Client Secret**.

## 3. Enable Google in Supabase

1. Supabase > **Authentication > Sign In / Providers > Google**. Turn on Google.
2. Paste the Google OAuth Client ID and Client Secret and save.
3. Supabase > **Authentication > URL Configuration**:
   - **Site URL:** `https://YOUR-SERVICE.onrender.com`
   - **Redirect URLs:** add `https://YOUR-SERVICE.onrender.com/**` (or your exact app URL). Add `http://127.0.0.1:8000/**` only if testing locally.
4. In **Project Settings > API Keys** (or the current project's API Keys area), copy the project URL, legacy **anon/public JWT** key, and legacy **service_role JWT** key used by this direct REST integration. The service-role key must remain PRIVATE.

## 4. Configure Render environment

Deploy this new ZIP's `outputs` files to your Render code repository (the service's root directory must match the project files). In **Render > Web Service > Environment**, add:

| Variable | Value |
|---|---|
| `MEMBERSHIP_AUTH_MODE` | `google_free` |
| `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase public **anon JWT** key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase private **service_role JWT** key (server only) |

**Do NOT set** `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, or `RAZORPAY_WEBHOOK_SECRET` for Google-only mode. Existing Kite API environment variables remain as before. Google OAuth Client Secret is stored **in Supabase**, not in Render. Save and redeploy.

`MEMBERSHIP_AUTH_MODE=phone` (or absent) keeps the original `numbers.txt` system. `google_free` enables free Google login and **disables phone login**, including direct data APIs. `google` is the future PAID mode and must not be used yet.

## 5. Test it

1. Open `https://YOUR-SERVICE.onrender.com/api/membership/config` — it should show `"mode":"google_free"`, `"configured":true`, your Supabase URL and a zero `price_paise`. It should not expose the private key.
2. Visit Trend Hunter logged out: market tables stay locked/blurred and show **Continue with Google** without price or Razorpay.
3. Click **Continue with Google**. Sign in using your Google account (which must be on the Google test-user list while Testing).
4. Google redirects via Supabase back to Trend Hunter. Once login succeeds, the scanners unlock and the Google display name shows in Desk View.
5. Supabase > **Table Editor > th_memberships**: confirm a new row contains the user's name, email and `status=pending` (correct for this free mode).
6. Click **Sign out**, then confirm all scanner API endpoints return 403 without a valid bearer token.
7. Try another browser and return later; Supabase should restore the session while valid.

If `configured:false`, check all three Supabase Render env vars and redeploy. If Google displays `redirect_uri_mismatch`, check the **Supabase auth/v1/callback** URI on Google Cloud and your Render URLs in Supabase's redirect allow-list. If login fails with `google_login_required`, confirm the Google provider is selected and Supabase returns a verified email.

## Security and upgrade notes

- `SUPABASE_SERVICE_ROLE_KEY` and your Google OAuth Client Secret must never be added to HTML, GitHub or screenshots.
- The backend authenticates each request with Supabase, and the `th_memberships` table has RLS enabled and no client write permissions.
- Member profiles persist across Render restarts.
- No Razorpay setup or money collection is used here.
- Later, to introduce ₹4,999 lifetime membership, run the full `SUPABASE_MEMBERSHIP_SETUP.sql`, configure Razorpay test keys and webhook, change `MEMBERSHIP_AUTH_MODE` to `google`, and **test thoroughly first**. Users who signed in during free mode are **not automatically marked as paid**.
