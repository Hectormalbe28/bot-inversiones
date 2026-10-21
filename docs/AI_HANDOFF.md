# AI HANDOFF — Sprint 3 ready for execution

## Current state

- Spec: 6.4
- Stage: 1 — DATA foundation
- Stage 1 DATA_READY: false
- Sprint 1: CLOSED/PASS
- Sprint 2: CLOSED/PASS
- Sprint 3: IN_PROGRESS
- Branch: `codex/sprint-3`
- S3.1: PASS — CanonicalDailyBar + ReplayAvailabilityPolicy.
- S3.2: PASS — Massive grouped-daily HTTPS raw transport.
- Current task: `S3.3 strict parser + normalization`.

Read before changes:
- `docs/CURRENT_SPRINT.md`
- `docs/SPRINT_3_DESIGN.md`
- `docs/DECISIONS.md`
- `docs/PROJECT_STATE.json`
- `docs/reference/Bot_Inversiones_v6_4.docx`

## Locked Sprint-3 decisions

- Massive grouped daily is primary provider adapter.
- Canonical storage requests `adjusted=false`.
- No ticker/name identity synthesis.
- Raw all-market response preserved before canonical processing.
- Only explicit resolved identities become canonical daily bars.
- Parquet by session/date, not ticker.
- SQLite metadata, DuckDB query, Polars batch/lazy.
- Replay availability is a derived/versioned policy; never falsify actual ingestion timestamps.
- No distributed extras.
- No Sprint 4 work.
- Live trading remains disabled.

## Execution discipline

Implement only S3.3 now. Do not introduce identity materialization, migrations or Parquet persistence until S3.3 is accepted.
Latest verified CI: 436 PASS on Ubuntu and Windows; Ruff/format/HTTP smoke PASS.
