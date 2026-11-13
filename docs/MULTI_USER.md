# More than one person: invitations, administration and limits

Written 2026-11-08. LEARNABLE was built for private accounts from the start: every course,
document, answer and XP row belongs to one account and is checked on every request (tested in
`tests/test_ownership.py`). This adds the controls needed to let other people in.

## 1. Who can sign up

`REGISTRATION_OPEN` (server `.env`):

| Value | Meaning |
|---|---|
| `true` (default) | Anyone can create an account (development, CI). |
| `false` | Only with an **invitation** from an administrator. Existing accounts sign in as usual. |

An invitation is a link, `https://learnable.duckdns.org/?invite=CODE`. Opening it shows the
sign-up form with the code filled in. Rules, in `app/services/invitations.py`:

- Single use. Of two simultaneous sign-ups with one code, one fails (an `UPDATE ... WHERE
  used_at IS NULL`).
- Expires (default 7 days, up to 90). Can be tied to one email address. Can be revoked before it
  is used.
- Only a SHA-256 of the code is stored, as for password-reset links. The link is shown once, when
  it is created.
- Every failure (unknown, used, revoked, expired, wrong address) gives the same answer, so a
  stranger learns nothing about which codes exist.

## 2. Administrators and suspended accounts

- `users.is_admin`, set only from the command line, never through the API:
  `python scripts/manage_users.py admin --email me@example.com`.
- `users.is_active`: a suspended account can't sign in and its sessions end at once
  (the token version moves on). Reactivating does not bring old sessions back.
- The admin API (`/api/v1/admin/*`) and page (`/admin`, in the account menu) cover: invitations
  (create, list, revoke), accounts (usage, suspend/reactivate, limits, a temporary password for
  someone who lost theirs, delete) and a summary.
- **An administrator never sees what anyone studies.** The account list has counts and sizes
  only: courses, answers, storage, today's AI use, last activity.
- An administrator can't suspend or delete their own account from the page.
- `scripts/manage_users.py` does the same from the server's command line (`list`, `admin`,
  `suspend`, `delete --email-domain example.com [--yes]`).

Deleting an account removes everything it owns: courses with their uploaded files and drawings,
answers, XP, follows, marketplace pages (rows cascade, files are removed explicitly).

## 3. Limits

The AI provider's free quota is one quota for everybody, and the server's disk is small, so
accounts have daily and storage limits (`app/services/quota.py`). Administrators have none.

| Setting | Default | Counts |
|---|---|---|
| `AI_DAILY_EVALUATIONS` | 100 | answers sent for evaluation, repeats, retries, second opinions |
| `AI_DAILY_GENERATIONS` | 100 | curriculum proposals, learning items, questions, concept activation |
| `STORAGE_LIMIT_MB` | 500 | uploaded material per account (0: unlimited) |
| `AI_SHARED_DAILY_CAP` | 0 (off) | the day's total across all accounts |
| `AI_ADMIN_RESERVE_PERCENT` | 20 | share of the cap kept for administrators |

- Days are UTC days; usage is stored in `ai_usage`, so a restart doesn't reset it.
- A request counts when it starts, even if the AI then fails.
- When `AI_SHARED_DAILY_CAP` is set and the total reaches the cap minus the reserve, everyone but
  administrators is stopped for the day (error `quota_exceeded`, reason `shared_limit`).
- The administrator can give one account its own limits, or send it back to the defaults.
- Errors reach the user as `quota_exceeded` (429) and `storage_quota_exceeded` (413), translated
  in all nine languages.

Google's free Gemini tier allowed roughly 500 requests a day for the Flash-Lite model in
autumn 2026 (third-party sources; check aistudio.google.com/rate-limit). Set
`AI_SHARED_DAILY_CAP` a little under what your key really allows. Groq and Mistral can be added
as automatic fall-backs (docs/FREE_AI_ROUTING.md) to raise it.

## 4a. Testing the invitation journey

`web/e2e/invitation.spec.ts` drives the whole path in a real browser: an administrator creates
an invitation, a stranger without one is refused, the invited person opens the link (code
pre-filled), creates an account and is signed in, the same link fails a second time, the
administrator sees it used, and the newcomer can sign out and back in. It needs a backend with
sign-up closed, so it is skipped unless `INVITE_E2E_URL` is set:

```sh
# backend (own temp database, one administrator inserted by hand)
DATABASE_URL=sqlite:////tmp/inv.db REGISTRATION_OPEN=false PUBLIC_APP_URL=http://localhost:5174 \
  AI_PROVIDER=mock AUTH_SECRET=... uvicorn app.main:app --port 8001
# web
LEARNABLE_API_PROXY_TARGET=http://localhost:8001 npx vite --port 5174
INVITE_E2E_URL=http://localhost:5174 INVITE_E2E_ADMIN_EMAIL=... INVITE_E2E_ADMIN_PASSWORD=... \
  npx playwright test invitation
```

Sign-up is limited to 10 per hour per address; restart the backend between repeated runs.

## 4. Not built yet

- Outgoing email (reset-password links, invitation emails): needs an SMTP provider; until then
  the administrator sends links and sets temporary passwords.
- Letting an account delete itself, and a privacy notice to accept at sign-up (GDPR).
- A per-account AI key.
