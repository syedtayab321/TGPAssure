# TGPAssure Firebase + Stripe Backend

This backend is required for production Stripe payments. Do not put the Stripe secret key in the desktop application.

## Functions

- `createCheckoutSession`: Desktop calls this URL after Firebase login. It verifies the Firebase ID token, calculates the subscription price server-side, creates a Stripe Checkout subscription session and returns the Checkout URL.
- `stripeWebhook`: Stripe calls this after successful payment. It writes the paid plan, selected modules/submodules, amount, currency, session ID and subscription/customer IDs to Firestore under `tgpassure_users/{uid}`.

## Required environment variables

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `TGPA_CURRENCY=pkr`

After deployment, set `TGPA_STRIPE_CHECKOUT_URL` in the desktop `.env` to the deployed `createCheckoutSession` URL.
