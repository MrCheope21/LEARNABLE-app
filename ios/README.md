# iOS Client

SwiftUI (iOS 17+), `@Observable` view models, Swift Concurrency. See
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) §2 for the layer rules.

## Build status: compiled and tested in CI only

Written without a Mac. **CI compiles it and runs the unit tests** (`.github/workflows/ios.yml`,
macOS runner) on PRs, pushes to `main`, and manual dispatch. A manual dispatch with `e2e: true`
also runs the end-to-end acceptance test on a simulator against a seeded backend (see
`../docs/DEVELOPMENT.md`, "End-to-end acceptance run"). **No human has used the app yet**, so
layout, feel and accessibility beyond what that test touches are unverified.

To run it on a Mac:

1. `brew install xcodegen`, then `xcodegen generate` in this directory. It produces
   `AdaptiveLearning.xcodeproj` and `AdaptiveLearning/App/Info.plist` from `project.yml` (neither
   is committed — edit `project.yml`, not the generated files).
2. Start the backend (`../backend/README.md`), ideally with the demo seed
   (`AI_PROVIDER=mock`, `scripts/seed_demo.py`); the app points at `http://localhost:8000`
   (`Networking/APIConfiguration.swift`).
3. Run on a simulator and sign in as `demo@example.com` / `learnable-demo-2026`.

## Layout

```
AdaptiveLearning/
  App/              @main entry; AppDependencies (composition root: the one place concrete
                    implementations are chosen); ScreenFactory (builds each screen's view model
                    from the repositories) and the navigation route values
  Domain/
    Entities/       Course, CourseDocument, Curriculum (Chapter/Topic/Concept nodes), Learning
                    (LearningItem, memory snapshot, questions), Proposal, Review (sessions,
                    cards, answers, evaluations); ResilientEnum (unknown server values decode
                    to .unknown instead of failing the screen)
    Models/         Progress: review load, curriculum vs memory progress, Home summary
    Protocols/      Repositories: Auth, Course, Concept, Curriculum, Review, Progress, Document,
                    AnswerDraftStore — everything above Data depends only on these
  Data/
    Remote/         One repository per backend area, against docs/API.md
    Local/          UserDefaultsAnswerDraftStore (typed answers survive a crash or failed send)
  Networking/       APIClient (token-aware JSON + multipart), APIError, TokenStore protocol
  Persistence/      KeychainTokenStore (access token lives in the Keychain, never UserDefaults)
  Presentation/     RootView, MainTabView; Home, Courses, Curriculum (dashboard → chapter →
                    topic → concept, proposal review), Study (the session), Review, Source,
                    ProgressDashboard, Settings; Common (Loadable, error alert, labels, rows)
  Resources/        Localizable.xcstrings — English source + Italian
  Speech/           SpeechTranscriptionService abstraction (Phase 14, not wired)
AdaptiveLearningTests/
  APIContractTests  Every model decoded from real captured backend responses (Fixtures.swift)
  *ViewModelTests   View models against fakes (TestDoubles.swift): study loop, drafts,
                    overrides, activation polling, proposal editing, Home, Progress, Source
  APIClientTests    Auth header, query encoding, error envelope, 401 → sign-out, offline
  LocalizationTests Italian is compiled into the app bundle
AdaptiveLearningUITests/
  VerticalSliceAcceptanceTests  The MVP loop end to end (scheme AdaptiveLearningE2E; needs the
                    seeded backend running)
```

## Rules

- **Views hold no business logic** and never touch networking; they bind to a view model.
- **View models depend on Domain protocols only**, injected through `AppDependencies`, so every
  one is unit-testable with a fake.
- **No error is swallowed**: every view model exposes `errorMessage`, shown via `.errorAlert`.
  Cancellation (a view going away) is the only error that's silently ignored.
- **No hard-coded UI text**: literals in `Text`/`Button`/`Label`/... are catalog keys; use
  `Text(verbatim:)` for user content (course titles) and `String(localized:)` in non-view code.
  Add every new key with its Italian translation to `Resources/Localizable.xcstrings`.
- **Session expiry**: any 401 on an authenticated request deletes the token and returns the app to
  sign-in; signing out discards every view model, so no data from one account leaks into the next.

## What's real

Everything the app shows comes from the backend; nothing is faked or computed locally.

- Sign in / register, session persistence and expiry, Italian/English UI.
- Courses, Chapters (create), Topics and Concepts (from applied AI proposals), study material
  per Course or Chapter with "View source".
- "Analyze New Material" → the AI's proposal, editable (rename, delete, reorder, add concepts)
  → accept or reject.
- Concept activation → Learning Item generation followed until ready → "Learn Now".
- Study sessions: LEARN (introduction, then recall), scheduled review, practice on questions
  marked hard. Feedback shows what was right, missing, misconceptions, the reference answer
  with sources and the next review. Failed or impossible evaluations ask for the user's own
  grade; any grade can be disputed ("Disagree with the grade?"). The app never computes a
  memory level or a due date.
- Home (today's reviews, continue learning, weak areas), Review tab, Progress (review load;
  curriculum and memory progress kept separate).

Not built: voice answering, exam mode, offline caching, merging or splitting concepts in the proposal
editor (the API has no such operation).
