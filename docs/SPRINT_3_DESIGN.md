# Sprint 3 Design Record

Status: APPROVED FOR IMPLEMENTATION
Branch: `codex/sprint-3`
Date: 2026-10-21

## Decision summary

1. Massive grouped daily REST is the primary Sprint-3 provider adapter.
2. Development baseline is free Stocks Basic; paid Flat Files are optional evolution.
3. Canonical bars are always raw/as-traded (`adjusted=false`).
4. Broad provider raw is preserved; canonical materialization requires explicit identity.
5. No auto-created identities.
6. Parquet is partitioned by session/date, never ticker.
7. SQLite stores partition/revision metadata, not bulk OHLCV rows.
8. DuckDB reads Parquet; Polars performs lazy/batch transforms.
9. Backfill does not rewrite historical `available_at`; replay availability is derived
   under a versioned policy.
10. No distributed infrastructure in Sprint 3.

## External evidence checked

Massive documentation reviewed on 2026-10-21:
- Stocks Daily Market Summary: grouped all-US daily OHLCV in one request, all Stocks plans.
- Stocks Basic: $0/month, 5 API calls/min, 2 years historical, EOD, corporate actions.
- Stocks day flat files: daily all-US equities, one downloadable dataset per day, history
  available from 2003 depending entitlement.
- Aggregates support `adjusted=false` for non-split-adjusted/as-printed data.
- Massive splits/dividends endpoints expose newer historical adjustment metadata.

Alpaca historical bars were reviewed as an alternative. Alpaca supports raw/split/dividend/
spin-off/all adjustment modes and symbol `asof`, but Sprint 3 favors Massive grouped daily
because one request can cover the broad market and better matches the batch/local design.

## Open risks carried forward

- Free Massive history is limited; deeper backtests eventually require paid entitlement or
  another lawful historical source.
- Provider historical corrections are not guaranteed to expose the exact value that was
  visible on every past date. Revision fidelity must be labeled rather than assumed.
- Current canonical identity coverage is narrower than Massive's all-US response; unresolved
  rows remain raw/quarantined until an explicit identity expansion project.
- Corporate-action adjustment engine remains deferred.

These are accepted constraints, not reasons to weaken identity/PIT rules.
