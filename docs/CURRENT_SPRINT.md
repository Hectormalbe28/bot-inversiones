# SPRINT 3 — BROAD MARKET EOD / CANONICAL DAILY BARS

## Gate

**DESIGN: APPROVED**
**STATUS: READY_FOR_EXECUTION**
**IMPLEMENTATION: NOT STARTED**

Branch: `codex/sprint-3`
Spec: 6.4
Stage: 1 — DATA foundation
Stage 1 DATA_READY: false

User authorization: continuar después del cierre de Sprint 2.

## Objective

Construir la primera capa reproducible de mercado EOD para investigación local:

```
Massive Daily Market Summary (raw)
        ↓
immutable RawIngestion
        ↓
strict provider parser
        ↓
explicit identity resolution
        ↓
CanonicalDailyBar(raw)
        ↓
quality + quarantine
        ↓
immutable daily Parquet
        ↓
SQLite partition/revision metadata
        ↓
DuckDB / Polars
        ↓
future scanner/features
```

## Selected provider

Primary: Massive Stocks Daily Market Summary.

Baseline transport:
`GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false`

Reasons:
- one request returns broad US daily market;
- available in Stocks Basic/free;
- provider adapter remains replaceable;
- avoids one-call-per-ticker design;
- raw and split-adjusted modes are explicit;
- paid Flat Files can be adopted later without changing domain contracts.

Free-tier constraints are treated as runtime policy, not domain semantics.
Backfill must support bounded rate limiting and resumability.

## Scope

### S3.1 Domain + contracts
- define `CanonicalDailyBar` with stable `instrument_id`;
- define `DailyBarQualityReport`;
- define `ReplayAvailabilityPolicy` + derived replay timestamp;
- define provider-neutral daily-market port;
- acceptance tests before implementation.

### S3.2 Massive raw transport
- HTTPS only;
- explicit API key from environment;
- no secrets in logs/query diagnostics;
- timeout;
- bounded retry/backoff for transient network/429/5xx only;
- `adjusted=false` LOCKED;
- preserve response bytes before parse;
- provider request_id retained when present;
- fixtures for malformed/error/empty responses;
- no provider SDK in domain/application.

### S3.3 Parser + normalization
- strict JSON shape;
- preserve source ticker;
- OHLC consistency;
- nonnegative volume/VWAP/trade_count;
- timestamp validation;
- duplicate source ticker detection;
- no auto identity creation;
- deterministic ordering.

### S3.4 Identity gate
Input: provider rows + explicit PIT alias/version evidence.

Output states:
- ELIGIBLE;
- PENDING_IDENTITY;
- IDENTITY_CONFLICT;
- INVALID_DATA.

Only ELIGIBLE rows become canonical Parquet rows.
All source rows remain recoverable from raw.

### S3.5 Immutable Parquet + metadata
Proposed path:

`data/market/eod/provider=massive/feed=grouped_daily/session_date=YYYY-MM-DD/<revision>.parquet`

Rules:
- no file-per-ticker;
- immutable fragments;
- deterministic schema;
- deterministic row ordering by `instrument_id`;
- hash and row count recorded in SQLite;
- exact replay idempotent;
- divergent replay creates explicit new revision or fails according to revision contract;
- no silent overwrite.

SQLite metadata table is allowed only through a new forward migration.
Accepted prior migrations remain frozen.

### S3.6 DuckDB/Polars read path
- DuckDB view/query over Parquet;
- Polars lazy scan for batch transforms;
- query by session range and instrument set;
- deterministic results;
- no dependency on full dataframe loading when avoidable.

### S3.7 Real-data validation
Controlled Massive request for one or more dates.

PASS may include:
- full/partial canonical materialization for explicitly resolvable identities;
- quarantine for unresolved identities.

FAIL:
- invented identity;
- adjusted price stored as raw;
- overwritten revision;
- missing raw provenance;
- silent drop of malformed/duplicate records.

## CanonicalDailyBar proposed contract

Required:
- `instrument_id: Identifier`
- `symbol: Symbol`
- `session_date: date`
- `event_time: datetime UTC`
- `open/high/low/close`
- `volume`
- `vwap: optional`
- `trade_count: optional`
- `otc: optional`
- inherited provenance timestamps
- `provider`
- `feed`
- `version`
- `adjustment_policy = raw`

No adjusted close is stored in the canonical raw row.

## ReplayAvailabilityPolicy v1

Purpose: historical backfill must not falsify observed ingestion timestamps.

Policy:
- `policy_id = eod-next-calendar-day-ny-v1`
- session D becomes replay-eligible at 00:00 America/New_York on D+1;
- convert to timezone-aware UTC;
- store/derive this as replay metadata, not as fabricated local `received_at` or
  `processed_at`;
- never use for live/shadow;
- use only for EOD/historical reconstruction.

Any future change requires policy version increment.

## Adjustment policy

Canonical:
`raw`

Derived adjustment layers are DEFERRED until explicit corporate-actions ingestion.
Provider split-adjusted data may be used only as a validation comparison, never as the
canonical raw source in Sprint 3.

## Quality policy

FAIL/quarantine:
- malformed JSON/schema;
- missing ticker/date/OHLC;
- NaN/Inf;
- negative prices/volume;
- high < max(open, close, low);
- low > min(open, close, high);
- duplicate ticker with divergent values in same response;
- invalid timestamp.

WARN:
- missing VWAP;
- missing trade_count;
- OTC record if not in target universe;
- source result count differs from parsed count with explainable omissions.

No forward-fill, synthetic zero bars or previous-close carry in canonical storage.

## PIT join rules

- canonical identity uses explicit alias/version evidence;
- no latest/current fallback;
- historical universe and daily bars are joined by `instrument_id`;
- symbol is audit/provider evidence only;
- a bar may exist in raw even when no operational-universe membership exists;
- scanner later must use the historical/operational universe appropriate to its decision cutoff.

## Migration policy

If persistence metadata requires schema:
- create next migration only;
- do not edit 001..005;
- migration must be atomic, checksummed and backward-startup compatible with existing DB;
- clean DB and upgrade-existing DB tests mandatory.

## Performance target

Correctness first.

Initial practical target on local machine:
- process a full grouped daily response without per-ticker network calls;
- one-date pipeline bounded by memory and suitable for a normal developer PC;
- lazy/batch transforms where practical;
- no distributed infrastructure.

No numerical latency target is a release gate yet; record wall time and rows/sec as baseline.

## Non-goals

- scanner/ranking;
- intraday;
- WebSockets;
- broker/paper/live execution;
- AI/LLM;
- automatic instrument creation;
- corporate-action adjustment engine;
- Redis/Ray/MLflow;
- Kafka/RabbitMQ/Celery/Airflow/Spark/Kubernetes;
- Postgres/TimescaleDB;
- complex scheduler;
- Stage 2.

## Acceptance tests

At minimum:

1. raw grouped response is persisted before canonical parse result is committed;
2. adjusted=true source is rejected for canonical Sprint-3 persistence;
3. clean raw row normalizes deterministically;
4. OHLC invalid row quarantines/fails;
5. duplicate identical row handling is deterministic;
6. divergent duplicate ticker cannot silently win;
7. explicit known alias maps to expected instrument_id;
8. unknown alias does not create identity;
9. ticker reuse resolves using effective interval;
10. late-known alias remains invisible before its available_at;
11. exact re-ingest is idempotent;
12. divergent provider revision preserves old revision;
13. one Parquet fragment contains many instruments, not one file/ticker;
14. canonical Parquet rows sort by instrument_id;
15. DuckDB range query returns deterministic rows;
16. Polars scan can read same canonical dataset;
17. missing VWAP is accepted with warning;
18. missing trading bar is not forward-filled;
19. ReplayAvailabilityPolicy handles DST using America/New_York zone rules;
20. replay availability never rewrites real ingestion timestamps;
21. clean migration from empty DB passes;
22. migration from Sprint-2 DB passes;
23. full prior regression remains green;
24. Ruff + format + HTTP smoke remain green;
25. live flags remain false.

## Definition of Done

Sprint 3 closes only when:
- all scope tasks PASS;
- real Massive transport validated;
- raw provenance retained;
- canonical raw EOD materialization works for explicit known identities;
- Parquet/DuckDB/Polars path is reproducible;
- revision/idempotency semantics are tested;
- replay availability is explicit/versioned;
- full Ubuntu + Windows CI PASS;
- docs/handoff/state synchronized;
- Stage 1 still reflects honest DATA_READY status.

## First implementation task

`S3.1 — CanonicalDailyBar + ReplayAvailabilityPolicy contracts and RED acceptance tests`

Do not begin S3.2 before S3.1 gate passes.
