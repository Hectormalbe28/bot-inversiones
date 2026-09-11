# Changelog

## 0.2.0-dev — 2026-09-11 — Sprint 2: S2-TEMPORAL-NASDAQ-UNIVERSE (En progreso — Pausado para revisión de arquitectura)

- Congelación oficial del contrato temporal Point-in-Time (disponibilidad histórica: `available_at <= as_of`).
- Rechazo explícito de `event_time <= as_of` como filtro universal de elegibilidad PIT.
- Protocolo genérico `PointInTimeRepository` en `app.application.ports` (`get_as_of`, `scan_as_of`, `latest_available`).
- Implementación de operaciones PIT en `InstrumentRepository` con desempate determinista (`available_at DESC, version DESC`).
- Split semántico temporal: `MarketObservation` para `CanonicalBar`, `CanonicalQuote` y `CanonicalTrade` (`event_time <= available_at`), permitiendo hechos no de mercado con vigencia futura conocidos previamente (`Instrument`, `ScheduledEvent`).
- Suite de pruebas de aceptación PIT (9 casos mandatorios) y pruebas de regresión temporal.
- Contratos de dominio de universo (S2.5): `InstrumentVersion`, `SymbolAlias` con semántica semiabierta `[valid_from, valid_to)`, `CorporateAction` con 8 tipos de acciones corporativas, y `HistoricalUniverseSnapshot` con membresía de identidades canónicas estables.
- Persistencia y congelamiento de migración 002 (S2.6): tablas `source_ingestions`, `universe_snapshots` y `universe_snapshot_members` con clave foránea compuesta hacia `instrument_versions`. Migración `002_universe.sql` formalmente congelada.
- Contrato e implementación de `HistoricalUniverseRepository` (S2.7): contrato formal en `ports.py`, suite de aceptación de 18 casos y clase concreta `SQLiteHistoricalUniverseRepository` en `sqlite.py` con elegibilidad dual temporal (`available_at <= query_time` y `as_of <= query_time`), desempate determinista cuádruple, ordenamiento de miembros por `instrument_id ASC` y sin fallback a universo actual.
- Fixtures deterministas y parser estricto de Nasdaq (S2.8): 10 fixtures crudos oficiales en `tests/fixtures/nasdaq/`, DTOs `NasdaqListedRawRecord` / `NasdaqListedFile` y función `parse_nasdaqlisted` en `app.infrastructure.providers.nasdaq`.
- Normalizador determinista de Nasdaq (S2.9): normalización tipada de registros `normalize_nasdaq_record` (`NasdaqNormalizedRecord`) y archivo completo `normalize_nasdaqlisted` (`NasdaqNormalizedFile`) con política all-or-nothing y preservación de evidencia de proveedor.
- Resolver temporal de identidad (S2.10): función neutral de proveedor `resolve_symbol_identity` en `app.application.identity` con doble eje temporal (`query_time` y `effective_time`), estados `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`, y orquestación de archivo Nasdaq `resolve_nasdaq_identities`. Soporte de transiciones y reuso de tickers con evidencia explícita de `SymbolAlias`; sin heurísticas de nombres ni fallback hacia atrás.
- Gate de persistencia de identidad y almacén crudo de procedencia (S2.11): gate `build_identity_persistence_gate` (`PersistenceEligibility`: `ELIGIBLE`, `PENDING_IDENTITY`, `IDENTITY_CONFLICT`) y almacén inmutable content-addressed `RawIngestionStore` / `save_raw_ingestion` en `app.infrastructure.storage.raw` con registro idempotente en `source_ingestions`.
- Contrato de escritura y adaptador atómico de universo histórico (S2.12): contrato `HistoricalUniverseWriteRepository` en `ports.py`, DTO `HistoricalUniverseMemberRef` y excepción `HistoricalUniverseWriteConflict` en `universe.py`, e implementación `SQLiteHistoricalUniverseWriteRepository` en `sqlite.py` con transacción atómica `BEGIN IMMEDIATE`, idempotencia exacta, validación de paridad de membresía, orden canónico `instrument_id ASC` y enforzamiento estricto de claves foráneas.
- Estado de verificación: **388 pruebas PASS** sin fallos (2 warnings upstream).
- Checkpoint de pausa: desarrollo formalmente pausado para revisión integral de arquitectura y especificación antes de abordar la orquestación de ingesta en S2.13.
- Pendientes en Sprint 2: orquestación canónica de ingesta de universo Nasdaq (S2.13), política DataQuality, adaptador HTTP, CLI de refresco, endpoint `/v1/universe`, filtrado de invertibilidad y cierre de Sprint 2.

## 0.1.0 — 2026-09-10 — Sprint 1

- Inicialización del proyecto con Python 3.12, FastAPI, Pydantic y dependencias bloqueadas.
- Bootstrap local con SQLite WAL/FTS5, migraciones atómicas con checksum y Parquet/DuckDB.
- Contratos canónicos con UTC, provenance, validación numérica y disponibilidad temporal.
- Repositorio inmutable de instrumentos, idempotencia y consulta histórica `as_of`.
- Health/readiness, capabilities, provider registry y consulta de instrumentos.
- Logs JSON, IDs de request y rechazo de flags live.
- 30 pruebas de aceptación/resiliencia, smoke HTTP real y validación de estilo.
- Empaquetado wheel/sdist, Dockerfile y Compose core.
- Estado de proyecto, decisiones, handoff, sesión y copia de especificación.
- Alineación final S1.7: IDs centralizados, DomainError seguro y aliases de health/readiness/capabilities.
- 33 pruebas de aceptación/resiliencia/contrato PASS; smoke HTTP actualizado para los aliases.

Pendiente operativo: build y ejecución Docker (motor no activo durante la sesión).
La captura de datos y la Etapa 1 completa continúan en futuros sprints.
