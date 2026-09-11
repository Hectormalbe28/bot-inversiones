# Handoff del proyecto

Spec 6.4. Etapa 1. Sprint: `S2-TEMPORAL-NASDAQ-UNIVERSE`.
Estado: `IN_PROGRESS`. Rama: `codex/sprint-2`.

## Actualmente completado (Sprint 2)

- **Contrato Point-In-Time:** Especificado en `docs/DECISIONS.md` y `app/application/ports.py` (`PointInTimeRepository`).
- **Pruebas de aceptación PIT:** 9 casos de aceptación mandatorios más pruebas de regresión en `tests/test_pit_acceptance.py`.
- **Implementación SQLite PIT:** `InstrumentRepository` implementa `get_as_of`, `scan_as_of` y `latest_available` en `app/infrastructure/storage/sqlite.py`.
- **Split semántico temporal:** `TemporalEvidence` permite hechos con vigencia futura conocidos previamente; `MarketObservation` restringe observaciones de mercado (`CanonicalBar`, `CanonicalQuote`, `CanonicalTrade`) a `event_time <= available_at`.
- **Ordenamiento determinista:** Desempate estricto por `available_at DESC, version DESC` sin `event_time`.
- **Contratos de dominio de universo (S2.5):**
  - `InstrumentVersion`: historial versionado y fechado efectivo de instrumentos (`valid_from`, `valid_to`).
  - `SymbolAlias`: asociación explícita de ticker a identidad canónica estable con intervalo semiabierto `[valid_from, valid_to)`.
  - `CorporateAction`: 8 tipos canónicos de acciones corporativas sin mutación de identidad ni cálculo de precios.
  - `HistoricalUniverseSnapshot`: membresía por `instrument_id` estable sin fallback de universo actual.
- **Persistencia de universo — Migración 002 (S2.6):**
  - Tabla `source_ingestions`: procedencia, SHA256, orden temporal estricto y estado de ingesta.
  - Tabla `universe_snapshots`: metadatos de snapshot con clave foránea a `source_ingestions`.
  - Tabla `universe_snapshot_members`: membresía normalizada por `instrument_id` con clave foránea compuesta a `instrument_versions`.
  - **`002_universe.sql` congelada e inmutable** tras superar la suite de aceptación final (22 casos).
- **Contrato HistoricalUniverseRepository (S2.7A):** Protocolo de lectura en `app/application/ports.py` con ejes duales, alcance `provider`/`feed` y distinción `None` vs `()`.

## Aún no implementado (Sprint 2)

- Implementación SQLite de `HistoricalUniverseRepository` (S2.7B).
- Ingesta de universo Nasdaq (descarga y parsing de `nasdaqlisted.txt`).
- Normalizador y resolución determinista de identidad.
- Flujo de procedencia cruda y validación de calidad de datos.
- API de consulta de universo.
- Adapter real de Nasdaq.

> [!WARNING]
> No se afirma que la Etapa 1 sea DATA READY ni que el Sprint 2 esté completo.

## Evidencia verificada en esta sesión

- Suite completa pytest: 153 PASS, 0 fallos, 2 warnings upstream.
- Pruebas dirigidas de migración de universo: 56 PASS.
- Pruebas dirigidas de modelos de universo: 46 PASS.
- `ruff check .`: PASS.
- `ruff format --check .`: PASS.
- Seguridad: `live_trading_enabled = false`, `live_approved = false`.

## Siguiente acción exacta

Implement S2.7B SQLite HistoricalUniverseRepository using the S2.7A contract (dual eligibility, no current-universe fallback). Do not change 002_universe.sql.
