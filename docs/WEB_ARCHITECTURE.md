# Web Architecture

The desktop web client (`/web`). It is a second client of the same FastAPI backend as the iOS
app, not a second product: both share Courses, curriculum, Learning Items, memory states,
scheduling, sources and progress, because all of it lives on the server.

## 1. Shape

```
Browser (React)  ──HTTPS──▶  FastAPI  ──▶  domain services  ──▶  AIProvider  ──▶  runtime AI
iPhone (SwiftUI) ──HTTPS──▶  (same backend, same database, same user accounts)
```

- **No learning logic in React.** The browser never computes an outcome, a memory level, a due
  date, mastery or progress. It shows what the API returns and sends what the user did. The
  study loop mirrors `ios/.../StudySessionViewModel.swift` for the same reason.
- **No AI in the browser.** Every model call is server-side. No runtime AI credential exists in
  the web code, its build configuration or its bundle (§6).

## 2. Stack

React 19 + TypeScript (strict) + Vite, React Router 7, TanStack Query 5, `openapi-fetch`.
Vitest + Testing Library for unit/component tests, Playwright for the browser end-to-end run.
Exact versions are pinned in `web/package.json`, and `package-lock.json` is committed (CI uses
`npm ci`). TypeScript is on 5.9 because `typescript-eslint` and `openapi-typescript` don't
support 6+ yet.

## 3. API contract: generated, not remembered

`web/src/api/schema.d.ts` is generated from the backend's OpenAPI schema:

```bash
cd web
../backend/.venv/bin/python ../backend/scripts/export_openapi.py openapi.json
npm run gen:api
```

Web CI regenerates both files and fails if they differ from what is committed, so a backend
change that alters a contract breaks the web build instead of a user's session. Components never
build URLs: every call goes through `src/api/endpoints.ts`, typed by the generated schema.
`src/api/client.ts` adds the access token, maps the error envelope to `ApiError`, turns a 401
into sign-out, and gives user-safe messages (`userMessage`) instead of raw payloads.

## 4. Structure

```
web/src/
  api/          client (auth, errors), endpoints, generated schema
  auth/         token session, sign-in/register
  app/          routes, query client, app shell (blue top navigation, account menu)
  brand/        identity geometry (strokes, no font), active concept, BrandLogo
  components/   QueryState (loading/error/retry), progress blocks, labels
  features/
    dashboard/  dashboard (next step, course library, widgets), activity page
    home/       Review hub (per-course due reviews, practice)
    courses/    course library page, shared course parts (cover, Learn/Review buttons)
    curriculum/ course workspace (tree), course header, chapter, topic, concept (consolidation
                panel, breadcrumbs), proposal editor
    material/   upload / status / delete of study material (course or chapter)
    study/      the study session workspace, answer drafts
    source/     source passage panel
    progress/   curriculum vs memory progress
  test/         fixtures (real captured API responses), scripted fetch, render helper
web/e2e/        Playwright specs against a live backend
```

Server state is TanStack Query; the only local state is what the user is editing (answer drafts,
the proposal draft). Polling uses `refetchInterval` and stops by itself: documents while
`PROCESSING`, a Concept while its items are `GENERATING`, a proposal while `GENERATING`.

## 5. Desktop-first design

This is not the phone UI stretched out.

- **Navigation:** a full-width blue bar: the LEARNABLE logo (a link to the dashboard: `/`),
  Courses, Review, Progress, the current streak, total XP and the account menu (email, timezone,
  sign out). Inside a Course the whole curriculum tree (chapters → topics → concepts, with
  study-state markers) stays on the left while you work on the right, with breadcrumbs above.
- **Dashboard** (`/`, one `GET /dashboard`): "Your next step" (one recommended action), the
  course library (search, status filter, sorting, "+ New course") as wide horizontal cards
  (cover, title, next concept, "concepts studied" and "learning items introduced" bars, green
  Review with its due count, blue Learn), and a sidebar: Daily streak, Experience, Daily goal
  (semicircle gauge, editable), Time planner (cumulative), Activity (12-week calendar, "See
  more" → `/activity`). Tablet: narrower sidebar; below 900 px the widgets move under the list
  and a compact "today" strip appears at the top; phones get a two-row navigation and stacked
  cards with Review/Learn in a bottom row. No horizontal page scroll at 390-1440 px (checked by
  `e2e/screenshots.spec.ts`).
- **Managing content:** "Manage questions" (in the course tree) lists every question grouped by
  chapter › topic › concept, with search, per-question and per-concept checkboxes, a sticky bulk
  bar (Move to…, Pause, Resume, Delete) and inline editing of wordings, expected answer and key
  points. Every course, chapter, topic and concept title has "Rename". Material can be uploaded
  as a file or pasted as text (sent as a Markdown file, as study material or as questions and
  answers), and originals can be downloaded.
- **Reordering:** chapters (course page), topics (chapter page), concepts (topic page) and
  questions within a concept ("Manage questions") are drag-and-drop lists
  (`components/SortableList.tsx`, @dnd-kit): mouse, touch, or keyboard (focus the ⠿ handle,
  Space, arrows, Space), with screen-reader announcements. The new order shows at once and is
  saved with one `PUT …-order` call; on failure the list returns to the server's order. Dragging
  questions is off while a search hides part of the list, since the server needs every item.
  Checked in a browser by `e2e/curriculum-management.spec.ts`.
- **Collapsing:** every section that holds others collapses on its own, via a chevron
  (`components/Collapsible.tsx`): chapters and topics in the course tree, and chapter, topic and
  concept groups in "Manage questions" (plus Collapse all / Expand all; a collapsed concept shows
  its question count). What's collapsed is remembered per course in this browser (localStorage,
  optional). The tree branch of the page you open always shows, and a search never hides its
  results in a collapsed section. Collapsed content stays mounted, only `hidden`, so an open
  editor keeps its state.
- **Wide curriculum views:** sortable lists for chapters, topics and concepts, a table for progress; material management
  inline on the chapter page; the proposal editor shows every topic at once with reorder, move
  between topics, merge, delete and add.
- **Study workspace:** the question and your answer in the centre. The source passage opens in
  a side panel next to the feedback instead of replacing it. The header shows the breadcrumb,
  the mode, "Round n of 3" in consolidation and the session's XP; the card shows the XP a
  correct answer would earn, "Show hint" (the halving is stated before anything is revealed),
  and after grading "Correct · +15 XP · Hint used". A consolidation batch is resumed by URL
  (`/study/:courseId?session=…`) and "Leave (resume later)" keeps it open.
- **Keyboard:** Ctrl/⌘+Enter submits an answer; Enter continues (or starts recall from a LEARN
  introduction); 1–4 give Again/Hard/Good/Easy when a grade is needed or when disputing one.
  All controls are real buttons, links and labelled fields.

## 6. Secrets: nothing server-side reaches the browser

Anything in the bundle is public. So:

- Vite's client-exposed prefix is changed from `VITE_` to `LEARNABLE_PUBLIC_`
  (`vite.config.ts`), so a habitual `VITE_…_KEY` is never compiled in. The only client variable
  is `LEARNABLE_PUBLIC_API_BASE_URL`.
- `npm run check:secrets` (in CI, after the production build) fails if `src/`, `index.html` or
  `dist/` mention a server credential name (`AI_API_KEY`, `DEEPSEEK_API_KEY`,
  `DASHSCOPE_API_KEY`, `MOONSHOT_API_KEY`, `ZHIPU_API_KEY`, `AUTH_SECRET`, …), a public variable
  that looks secret, or a key-shaped string. It prints file and rule only.
- The browser holds only the user's own backend access token (localStorage, so a reload keeps
  you signed in). It grants access to that user's study data, never to an AI provider. Signing
  out or a 401 clears it along with the whole query cache and every saved answer draft; signing
  in clears the cache again, so nothing from one account is shown to the next.

## 7. Running locally against the backend

```bash
# backend (another terminal), with the deterministic mock AI and demo data
cd backend && AI_PROVIDER=mock .venv/bin/python -m alembic upgrade head
AI_PROVIDER=mock .venv/bin/python scripts/seed_demo.py
AI_PROVIDER=mock .venv/bin/uvicorn app.main:app --port 8000

cd web && npm ci && npm run dev    # http://localhost:5173, /api proxied to :8000
```

`LEARNABLE_API_PROXY_TARGET` changes the proxied backend. In production, serve `web/dist` from
the same origin as the API (a reverse proxy routing `/api` to FastAPI). The backend has no CORS
configuration on purpose, so a different origin would need it added explicitly.

## 8. CI (`.github/workflows/web.yml`)

Runs on PRs and pushes to `main` touching `web/`, the backend app, or the export/seed scripts,
and on manual dispatch. No job needs paid AI.

- **check:** `npm ci`, the API-types drift check (§3), `tsc`, ESLint, Vitest, production build,
  and the secrets check (§6).
- **e2e:** migrates a fresh SQLite database, seeds the demo account with `AI_PROVIDER=mock`,
  starts uvicorn, then Playwright (`web/e2e/vertical-slice.spec.ts`) drives Chromium:
  - **consolidation loop:** dashboard → course → chapter → topic → concept, activate, "I have
    studied this concept", round 1 with a confirmed hint (kept across a reload, +5 XP), rounds 2
    and 3 (+20, +30), dispute the last grade (schedule replayed, XP unchanged), finish the batch,
    logo → dashboard with the new XP, streak and goal; Progress; the stored history.
  - **two accounts:** register a second account in the browser; it sees none of the demo
    material, its direct API requests for the demo course, summary, outline and file answer 404,
    and switching accounts in the same tab shows no cached data.
  - **curriculum loop:** new course, chapter, upload, AI proposal, edit, accept.
- `e2e/screenshots.spec.ts` (only with `CAPTURE_SCREENSHOTS=1`) writes `docs/screenshots/`.

The e2e run needs a freshly seeded database: once the demo concept is consolidated, "I have
studied this concept" is (correctly) no longer offered.

## 9. Identity

See docs/BRAND.md. `src/brand/active.ts` picks the active concept; `BrandLogo` draws it inline.
