# EUDR Compliance Suite — Deployment Guide

You execute these steps once. Total time ~2 hours (most of it is waiting for
review queues).

## 1. Create Shopify Partner Dashboard app (10 min)

1. Go to https://partners.shopify.com → Apps → Create app → Public app
2. App name: `EUDR Compliance Suite`
3. Copy `client_id` and `client_secret` — you'll need them in step 4

## 2. Set up Neon Postgres database (5 min)

1. https://neon.tech → New project → name it `eudr-prod`
2. Copy the connection string (looks like `postgresql://...`)

## 3. Create Render service (10 min)

1. https://render.com → New → Web Service → connect GitHub repo (push `eudr/`
   to a new repo first: `gh repo create eudr-compliance-suite --public --source eudr/`)
2. Render auto-detects `render.yaml`
3. Set the unset env vars:
   - `SHOPIFY_API_KEY` = client_id from step 1
   - `SHOPIFY_API_SECRET` = client_secret from step 1
   - `SHOPIFY_APP_URL` = your Render URL (e.g. `https://eudr-compliance.onrender.com`)
   - `DATABASE_URL` = Neon connection string from step 2
4. Deploy — should succeed since the code follows the StockPilot template

## 4. Update Shopify app URLs (5 min)

In Partner Dashboard → your app → Configuration:
- **App URL**: `https://eudr-compliance.onrender.com/`
- **Allowed redirection URLs**: `https://eudr-compliance.onrender.com/auth/callback`
- **GDPR webhook URLs**:
  - `customers/data_request` → `https://eudr-compliance.onrender.com/webhooks/customers-data-request`
  - `customers/redact` → `https://eudr-compliance.onrender.com/webhooks/customers-redact`
  - `shop/redact` → `https://eudr-compliance.onrender.com/webhooks/shop-redact`
- **Scopes**: `read_products,write_products,read_locales`

Also update `eudr/shopify.app.toml` with the same values and push.

## 5. Set up GitHub Actions deploy (10 min, optional but recommended)

Same pattern as StockPilot — see `.github/workflows/render-deploy.yml` in the
StockPilot repo. Webhook auto-deploy on Render has been historically flaky;
this is the safer path.

## 6. Test install on dev store (15 min)

1. Partner Dashboard → Stores → create new development store `eudr-dev`
2. Install the app from your app's preview link
3. Walk through: operator settings → sync products → classify one → add plot →
   create DDS → publish widget
4. Verify the widget displays on the product page in the dev store's storefront

## 7. Build theme app extension (separate `shopify` CLI step, 15 min)

The Liquid block lives in `eudr/extensions/eudr-widget/`. Deploy via:

```bash
cd eudr
npm install -g @shopify/cli @shopify/theme
shopify app deploy
```

This bundles the extension and registers it under your app. Merchants will then
see "EUDR Compliance" as an app block in their theme editor under the Product
section.

## 8. Submit for App Store review (10 min)

1. Partner Dashboard → your app → Distribution → Public listing
2. Fill in listing fields using `eudr/APP_LISTING.md` copy
3. Upload screenshots (1600×900, 3-5 required)
4. Upload app icon (1200×1200 PNG, no alpha — Chrome/Shopify both require this)
5. Set pricing — match `EUDR_PLANS` in `settings.py`
6. Submit

Typical review time: 5-10 business days. Re-submissions are usually faster
(see StockPilot post-rejection turnaround).

## 9. After approval — promote in search

Because EUDR Compliance Suite is the first dedicated EUDR app on the Shopify
App Store, you should rank #1 on the search "EUDR" automatically. Boost
visibility by:

1. Asking your first 5-10 installers for a review (legal compliance apps
   convert to reviews at high rates because merchants are relieved).
2. Publishing SEO blog posts on a marketing site (`eudr-suite.app` or similar)
   targeting "EUDR Shopify app", "EU deforestation regulation compliance",
   "due diligence statement Shopify".
3. Submitting to compliance-focused Shopify partner newsletters (e.g. Shopify
   Plus partner directory).

## Cost structure (so you know what hits your wallet)

| Service | Cost |
|---|---|
| Render Starter | $7/mo |
| Neon Postgres (free tier) | $0 (sufficient for first ~100 installs) |
| Domain (optional) | ~$12/yr |
| Shopify Partner take | 0% under $1M annual partner revenue |
| Stripe processing | ~3% of gross |

Net at 100 installs × $30 average = $3,000/mo with ~$100 in costs.

## Reference

- StockPilot lessons applied: `memory/stockpilot-shopify-submitted.md`
- Why "decide don't ask between options": memory file of same name
- Why never lead with horizontal-bundle (avoid Vitals trap): `memory/feedback_real_money_not_scraps.md`
