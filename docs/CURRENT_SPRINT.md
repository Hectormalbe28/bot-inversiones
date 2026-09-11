# Sprint 2 — S2-TEMPORAL-NASDAQ-UNIVERSE

Estado: `IN_PROGRESS`. Rama: `codex/sprint-2`.
Objetivo: Implementar el contrato temporal Point-In-Time universal, ingesta de universo Nasdaq y snapshots históricos.

## Alcance del Sprint 2

- [x] Congelación de semántica temporal Point-in-Time (S2.1B) en `docs/DECISIONS.md`.
- [x] Test de aceptación PIT para eventos futuros conocidos (S2.1C).
- [x] Contrato genérico `PointInTimeRepository` (S2.2A) en `app/application/ports.py`.
- [x] Suite de pruebas de aceptación PIT (S2.2B) en `tests/test_pit_acceptance.py`.
- [x] Implementación de operaciones PIT (`get_as_of`, `scan_as_of`, `latest_available`) en `InstrumentRepository` (S2.3A).
- [x] Correcciones de checkpoint temporal Astra (S2.3B): split semántico de observaciones de mercado (`MarketObservation`), ordenamiento determinista (`available_at DESC, version DESC`), y tests de regresión.
- [x] Contratos de dominio de universo histórico (S2.5):
  - [x] `InstrumentVersion` (S2.5A) en `app/domain/models.py`.
  - [x] `SymbolAlias` (S2.5B) con intervalo semiabierto `[valid_from, valid_to)` e identidad estable.
  - [x] `CorporateAction` (S2.5C) con 8 tipos canónicos de acciones corporativas.
  - [x] `HistoricalUniverseSnapshot` (S2.5D) con membresía basada en `instrument_ids` estables.
- [x] Persistencia de universo histórico — Migración `002_universe.sql` (S2.6):
  - [x] Tabla `source_ingestions` (S2.6A) para procedencia de ingestas y artefactos crudos.
  - [x] Tabla `universe_snapshots` (S2.6B) para metadatos y procedencia de snapshots.
  - [x] Tabla `universe_snapshot_members` (S2.6C) para membresía normalizada por `instrument_id` con composite FK a `instrument_versions`.
  - [x] Hardening y suite de aceptación final de migración (S2.6D, 22 casos).
  - [x] **`002_universe.sql` está formalmente CONGELADO / INMUTABLE.**
- [ ] Implementación de `HistoricalUniverseRepository` (S2.7).
- [ ] Ingesta y normalización de universo Nasdaq (S2.8+).

## Actualmente completado

- **PIT contract:** Especificación en `docs/DECISIONS.md` y protocolo `PointInTimeRepository` en `app/application/ports.py`.
- **PIT acceptance tests:** 9 casos de aceptación mandatorios y tests de regresión de observaciones de mercado en `tests/test_pit_acceptance.py`.
- **SQLite PIT implementation:** Operaciones `get_as_of`, `scan_as_of`, `latest_available` en `InstrumentRepository` (`app/infrastructure/storage/sqlite.py`).
- **Domain models:** `InstrumentVersion`, `SymbolAlias`, `CorporateAction`, `HistoricalUniverseSnapshot` en `app/domain/models.py`.
- **Persistencia y migración 002:** `002_universe.sql` congelada conteniendo `source_ingestions`, `universe_snapshots` y `universe_snapshot_members`.

## Aún no implementado (Pendiente en Sprint 2)

- `HistoricalUniverseRepository` (con elegibilidad dual temporal y sin fallback a universo actual)
- Fixtures de Nasdaq
- Parser de Nasdaq
- Normalizador
- Resolución de identidad
- Flujo de ingesta de procedencia cruda
- Validación de calidad de datos (DataQuality)
- Universe API (endpoints de consulta de universo histórico)
- Adapter real de Nasdaq

> [!WARNING]
> El Sprint 2 está `IN_PROGRESS`. La Etapa 1 NO se presenta como DATA READY y Nasdaq NO está ingerido.

## Evidencia y validación

- Suite completa de pruebas pytest: 153 PASS (0 failed, 2 warnings upstream).
- Pruebas dirigidas de migración de universo: 56 PASS (`test_source_ingestion_migration.py`, `test_universe_snapshot_migration.py`, `test_universe_snapshot_members_migration.py`, `test_universe_migration_acceptance.py`).
- Pruebas dirigidas de modelos: 46 PASS (`test_instrument_version.py`, `test_symbol_alias.py`, `test_corporate_action.py`, `test_historical_universe_snapshot.py`).
- Ruff check: PASS.
- Ruff format check: PASS.
- Flags live: `live_trading_enabled=false`, `live_approved=false`.
