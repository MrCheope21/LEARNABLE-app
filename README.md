# Adaptive AI Learning Platform

A structured knowledge curriculum combined with an adaptive memory engine, for iPhone. Not a
chatbot, not a flashcard app — a Course → Chapter → Topic → Concept → Learning Item hierarchy
paired with an AI-evaluated, spaced-repetition review engine.

See [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) for the full product specification and
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for current build status and phase plan.

## Status

**The backend learning loop works end to end**: Course → PDF → chunks → AI curriculum (per
Chapter, reviewed by the user) → Concepts → activation → AI-generated Learning Items and
questions → LEARN / review / practice sessions → AI-graded answers → deterministic outcome →
Chessable-style scheduling → history → progress, with Course isolation enforced and tested (417
tests on SQLite and PostgreSQL). No real AI model has been tried yet (everything runs against a
mock; a manual real-provider workflow is ready and waits for a key in GitHub secrets). Two
clients share that backend: the iOS app (every MVP screen, unit-tested in CI; its simulator
acceptance run doesn't pass yet) and a desktop web client (every MVP screen, passing a browser
end-to-end run against the real backend). Verified status:
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md). CI runs on pull requests and pushes to
`main`: [Actions](https://github.com/MrCheope21/LEARNABLE/actions).

## Documentation

- [PROJECT_SPEC.md](docs/PROJECT_SPEC.md) — authoritative product specification
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, service boundaries, isolation rules
- [DATA_MODEL.md](docs/DATA_MODEL.md) — entity reference
- [API.md](docs/API.md) — endpoint reference
- [AI.md](docs/AI.md) — AIProvider contract, structured-output schemas, prompt versioning
- [SCHEDULING.md](docs/SCHEDULING.md) — SchedulingPolicy contract, Chessable-style defaults
- [XP_AND_ACTIVITY.md](docs/XP_AND_ACTIVITY.md) — consolidation rounds, progressive XP, hints,
  streak, daily goal, dashboard
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — what GitHub holds, services and secrets, upload storage,
  accounts and privacy
- [WEB_ARCHITECTURE.md](docs/WEB_ARCHITECTURE.md) — the web client; [BRAND.md](docs/BRAND.md) —
  the identity
- [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — verified phase and acceptance status
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) — decision log, local dev, testing, CI

## Structure

```
ios/       SwiftUI client (Phase 2+)
web/       desktop web client: React + TypeScript + Vite (docs/WEB_ARCHITECTURE.md)
backend/   FastAPI + PostgreSQL backend (Phase 3+)
docs/      Living specification and architecture docs
```

## Important architectural rule

The coding agent used to build this repository (Claude, Kimi, DeepSeek, GLM, or another) is
independent of the runtime AI the finished app calls (Qwen, DeepSeek, Kimi, GLM, a managed
service, or self-hosted). Neither the iOS app nor the backend may hard-code assumptions about
either. See [AI.md](docs/AI.md) §1.
