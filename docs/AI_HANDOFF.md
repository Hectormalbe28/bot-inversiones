# AI HANDOFF — Sprint 3 ready for execution

## Current state

- Spec: 6.4
- Stage: 1 — DATA foundation
- Stage 1 DATA_READY: false
- Sprint 1: CLOSED/PASS
- Sprint 2: CLOSED/PASS
- Sprint 3: DESIGN APPROVED / READY_FOR_EXECUTION
- Branch: `codex/sprint-3`
- First task: `S3.1 CanonicalDailyBar + ReplayAvailabilityPolicy contracts and RED tests`

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

Implement only S3.1 first. Run full baseline after the focused tests. Do not introduce
transport, network, migration or Parquet persistence until S3.1 is accepted.
