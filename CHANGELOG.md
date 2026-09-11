# Changelog

## 0.2.0-dev — 2026-09-11 — Sprint 2: S2-TEMPORAL-NASDAQ-UNIVERSE (En progreso)

- Congelación oficial del contrato temporal Point-in-Time (disponibilidad histórica: `available_at <= as_of`).
- Rechazo explícito de `event_time <= as_of` como filtro universal de elegibilidad PIT.
- Protocolo genérico `PointInTimeRepository` en `app.application.ports` (`get_as_of`, `scan_as_of`, `latest_available`).
- Implementación de operaciones PIT en `InstrumentRepository` con desempate determinista (`available_at DESC, version DESC`).
- Split semántico temporal: `MarketObservation` para `CanonicalBar`, `CanonicalQuote` y `CanonicalTrade` (`event_time <= available_at`), permitiendo hechos no de mercado con vigencia futura conocidos previamente (`Instrument`, `ScheduledEvent`).
- Suite de pruebas de aceptación PIT (9 casos mandatorios) y pruebas de regresión temporal.
- Contratos de dominio de universo (S2.5): `InstrumentVersion`, `SymbolAlias` con semántica semiabierta `[valid_from, valid_to)`, `CorporateAction` con 8 tipos de acciones corporativas, y `HistoricalUniverseSnapshot` con membresía de identidades canónicas estables.
- Persistencia y congelamiento de migración 002 (S2.6): tablas `source_ingestions`, `universe_snapshots` y `universe_snapshot_members` con clave foránea compuesta hacia `instrument_versions`. Migración `002_universe.sql` formalmente congelada.
- Contrato de aplicación `HistoricalUniverseRepository` (S2.7A): elegibilidad dual (`available_at` y `as_of`), alcance `provider`/`feed`, sin fallback a universo actual; `None` distinto de snapshot vacío.
- Pendientes en S2: implementación SQLite S2.7B, ingesta Nasdaq, fixtures, normalizador, resolución de identidad, DataQuality y Universe API.

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
