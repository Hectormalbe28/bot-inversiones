# Sprint 3 Proposal — Broad Market EOD / Canonical Daily Bars

> STATUS: PROPOSED / NOT APPROVED / DO NOT IMPLEMENT

## Objective

Añadir la primera capa amplia de datos de mercado diarios reproducibles para que Stage 1 pueda avanzar desde identidad/universo hacia investigación cuantitativa y, posteriormente, scanner EOD.

Target flow:

```
Provider response / raw evidence
        ↓
canonical EOD normalization
        ↓
CanonicalDailyBar
        ↓
quality validation
        ↓
partitioned Parquet
        ↓
DuckDB
        ↓
Polars
        ↓
reproducible feature/scanner input
```

## Why this sprint is next

Sprint 2 resuelve qué instrumentos existían y qué podía conocerse en cada corte. El siguiente cuello de botella es disponer de historial OHLCV diario reproducible sobre identidades canónicas y universo PIT. Sin esa capa, scanner, features y research estadístico serían prematuros.

## Proposed scope

- seleccionar y validar un proveedor EOD amplio mediante adapter;
- conservar raw/provenance conforme al patrón existente;
- contrato canónico de daily bars con UTC, provider/feed/version y `available_at`;
- normalización estricta e idempotencia;
- almacenamiento histórico columnar en Parquet particionado;
- consultas locales mediante DuckDB;
- batch/transformación con Polars cuando aporte valor;
- quality gates para OHLCV, duplicados, huecos y timestamps;
- API/CLI de lectura solo si existe caso de uso concreto;
- pruebas reproducibles con fixtures antes de red real;
- una validación real controlada del proveedor elegido.

## Provider decision

Massive EOD es candidato de arquitectura previa, pero NO queda aprobado por este documento.

Antes de implementar debe verificarse:
- disponibilidad y términos actuales;
- cobertura;
- límites/rate limits;
- históricos incluidos;
- corporate-action adjustment semantics;
- costes/licencia;
- facilidad para preservar raw/provenance.

El provider debe entrar por adapter reemplazable.

## Non-goals

No implementar en este sprint:
- scanner/ranking completo;
- intraday/live;
- broker/execution;
- IA;
- Redis/Ray/MLflow;
- Kafka/Celery/Postgres;
- scheduler complejo;
- Stage 2 intelligence;
- trading real;
- auto-identity heuristics.

## Architectural invariants inherited from Sprint 2

- `instrument_id` sigue siendo identidad canónica.
- Historical/replay usa cortes PIT y nunca universo actual como fallback.
- UTC interno.
- Provenance completo.
- Raw no se reemplaza silenciosamente.
- Historias/revisiones no se mutan retroactivamente.
- Parquet es histórico grande; SQLite conserva metadata/governance pequeña; DuckDB consulta; Polars procesa.
- Correctness/reproducibility precede performance.

## Proposed acceptance direction

Antes de aprobar Sprint 3, convertir este proposal en un CURRENT_SPRINT que especifique:
- provider seleccionado y contrato;
- CanonicalDailyBar definitivo;
- partition strategy;
- adjustment policy;
- data-quality policy;
- idempotency/revision semantics;
- clean/replay tests;
- corrupted/missing data tests;
- PIT join con HistoricalUniverse;
- Definition of Done.

## Gate

Decision required from Khazlo/Astra/user:

`APPROVE_SPRINT_3_DESIGN`
or
`MODIFY_SPRINT_3_PROPOSAL`
or
`PAUSE`

No código de Sprint 3 debe comenzar antes de ese gate.
