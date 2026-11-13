# Marketplace: publishing, access, reviews, updates, paid courses

Code: `backend/app/services/marketplace.py`, `payments.py`, `backend/app/models/marketplace.py`,
`backend/app/api/marketplace.py`, `payments.py`, `web/src/features/marketplace/`.
The endpoints for publishing and access are listed in docs/API.md ("Marketplace").

## 1. Listing

One `MarketplaceListing` per course: the author's sales page (title, subtitle, description,
outcomes, audience, level, category, tags, price) and a **snapshot** of the course's study
content (structure, questions, expected answers, priorities, reference drawings; never the
uploaded documents, the author's answers or progress). `DRAFT` → `PUBLISHED` → `UNPUBLISHED`.
Each publish is a new version; saving the sales page is not. At most 5000 questions.

## 2. Before access

A listing shows only its sales page, sizes (`item_count`, `chapter_count`, chapter titles with
their question counts), the rating and the "What's new" notes. No question, answer or drawing.
Authors appear by display name only.

## 3. Access, not a copy

Acquiring gives access for good (`MarketplaceAcquisition`, one per user and listing) and puts a
managed, read-only course in the user's courses. It follows the author's later versions; the
user's answers, XP and their own priority per question stay theirs. Course material is never
downloadable. Removing the course and adding it back is free, also for a paid one.

## 4. Reviews

Someone who has the course (not its author) can leave 1 to 5 stars and an optional comment: one
review per person and listing, editable and deletable. The author can answer each review once and
edit the answer. The listing keeps `rating_count` and `rating_average`, so browsing sorts by
"best rated" without counting. An administrator can remove a review.

```
GET    /api/v1/marketplace/listings/{listing_id}/reviews   # {count, average, distribution[1..5], mine, can_review, items}
PUT    /api/v1/marketplace/listings/{listing_id}/review    # {rating, comment}
DELETE /api/v1/marketplace/listings/{listing_id}/review
PUT    /api/v1/marketplace/reviews/{review_id}/reply       # {reply}; empty removes it
DELETE /api/v1/admin/reviews/{review_id}
```

## 5. Updates and announcements

- **A new version**: when republishing, the author can write what changed (`update_note`). It is
  shown on the listing as "What's new · Version n" and sent to everyone who has the course.
- **An announcement**: between versions, the author can write to everyone who has the course
  (`POST /api/v1/courses/{course_id}/marketplace/announce {message}` → how many people were told).

Both arrive as a notification (docs/COMMUNITY.md §5) and, when the server can send email and the
person left it on in Settings, as an email in Italian or English.

## 6. Price

`price_cents` (0 = free) and `currency` (EUR) on the listing, set by the author on the sales page.
A price above 0 is accepted only when payments are enabled on the server, the author finished the
payment setup (`users.payout_ready`) and the amount is between `PRICE_MIN_CENTS` and
`PRICE_MAX_CENTS`. Changing the price doesn't touch people who already have the course.

## 7. Sales page for the author

`/marketplace/sales` in the app: the state of the payment setup, then the sales (course, date,
price, the author's share) and totals. `GET /api/v1/marketplace/sales`.

## 8. Payments

LEARNABLE never sees card data and never holds the author's money. `PAYMENTS_PROVIDER`:

- `none` (default): every course is free; a price can't be set; the app says so.
- `stripe`: Stripe Connect (Express accounts) with Stripe Checkout.

```
author → "Set up payments" → POST /payments/payout/onboarding → their own Stripe account,
         completed on Stripe's pages; payout_ready once Stripe says it can take payments
buyer  → "Buy" → POST /marketplace/listings/{id}/checkout → a MarketplaceOrder (PENDING) and a
         Stripe Checkout page; the charge goes to the author's account minus the platform's fee
Stripe → POST /payments/stripe/webhook (signed) → the order becomes PAID → access is given,
         the author gets a "course sold" notification
```

Access is never given from the browser coming back to the site: only the signed webhook counts
(the listing page polls `GET /marketplace/orders/{id}` until it says PAID). A refund made in the
Stripe dashboard arrives as `charge.refunded`: the order becomes REFUNDED and access is taken
back. Events handled: `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.expired`, `checkout.session.async_payment_failed`, `charge.refunded`,
`account.updated`.

### Turning it on (operator)

1. Open a Stripe account for the platform and activate **Connect** (Express accounts).
2. In the server's `.env`:
   ```
   PAYMENTS_PROVIDER=stripe
   STRIPE_SECRET_KEY=sk_live_…          # sk_test_… to try it with test cards first
   STRIPE_WEBHOOK_SECRET=whsec_…
   PLATFORM_FEE_PERCENT=10              # the platform's share of each sale (0-50)
   PRICE_MIN_CENTS=100
   PRICE_MAX_CENTS=50000
   ```
   `PUBLIC_APP_URL` must be the public https address (Stripe sends people back to it).
3. In Stripe → Developers → Webhooks, add the endpoint
   `https://<domain>/api/v1/payments/stripe/webhook` with the six events above, including
   events from connected accounts, and copy its signing secret into `STRIPE_WEBHOOK_SECRET`.
4. Restart the backend. With the keys missing it refuses to start rather than run half-configured.

Stripe's own fees are taken from the platform's share (destination charges), so
`PLATFORM_FEE_PERCENT` has to cover them: on small prices the fixed part of Stripe's fee can be
larger than 10%.

### PayPal

Buyers can pay with PayPal through the same Stripe Checkout page: no code changes, because the
checkout doesn't fix the payment methods. It has to be requested and enabled in the Stripe
dashboard (Settings → Payment methods → PayPal); for marketplaces on Connect, Stripe and PayPal
review the request, which can take weeks, and it is offered to businesses in European countries.
Authors are still paid out by Stripe to their bank account, not to a PayPal balance. A separate
PayPal integration (PayPal Commerce Platform) is not built.

### Before selling for real

Selling courses is a business activity: it needs the legal side in place first (terms of sale and
refund policy, the 14-day withdrawal rule for digital content sold to EU consumers, VAT on
digital services, invoices or receipts, the platform's own tax position). None of this is handled
by the code.

## 9. Free sample, discount codes, refunds

- **Free sample**: the author chooses how many of the first questions (0-5, none by default)
  anyone may read, with their answers, on the sales page (`preview_count`, `preview` in the
  listing's detail).
- **Discount codes**: per course, a percentage off (1-90), optionally with a maximum number of
  uses and an expiry. The buyer types the code before paying; the discounted price is never
  under `PRICE_MIN_CENTS`. A use is counted when the payment is confirmed.
- **Refund**: from "Sales and payments" the author (or an administrator) refunds a sale in
  full: Stripe takes the money back from the author's account and returns the platform's fee,
  the course leaves the buyer's courses and the buyer is told.

```
GET    /api/v1/marketplace/listings/{id}/discount?code=      # {code, percent_off, price_cents}
POST   /api/v1/marketplace/listings/{id}/checkout            # {code?}
GET    /api/v1/courses/{course_id}/marketplace/discounts
POST   /api/v1/courses/{course_id}/marketplace/discounts     # {code, percent_off, max_uses?, days?}
DELETE /api/v1/courses/{course_id}/marketplace/discounts/{discount_id}
POST   /api/v1/marketplace/orders/{order_id}/refund
```

## 10. Not built yet

- Bundles, subscriptions, currencies other than EUR, partial refunds.
