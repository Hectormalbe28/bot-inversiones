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

## Actualmente completado

- **PIT contract:** Especificación en `docs/DECISIONS.md` y protocolo `PointInTimeRepository` en `app/application/ports.py`.
- **PIT acceptance tests:** 9 casos de aceptación mandatorios y tests de regresión de observaciones de mercado en `tests/test_pit_acceptance.py`.
- **SQLite PIT implementation:** Operaciones `get_as_of`, `scan_as_of`, `latest_available` en `InstrumentRepository` (`app/infrastructure/storage/sqlite.py`).

## Aún no implementado (Pendiente en Sprint 2)

- `InstrumentVersion`
- `SymbolAlias`
- `CorporateAction`
- `HistoricalUniverseSnapshot`
- Ingesta Nasdaq (descarga y normalización de universo Nasdaq)
- Universe API (endpoints de consulta de universo histórico)

> [!NOTE]
> La Etapa 1 NO se presenta como DATA READY y el Sprint 2 NO está completado.

## Evidencia y validación

- Pruebas temporales dirigidas: 18 passed (`tests/test_pit_acceptance.py`, `tests/test_temporal_baseline.py`).
- Suite completa de pruebas: 51 passed (0 failed).
- Ruff check: PASS.
- Ruff format check: PASS.
- Flags live: `live_trading_enabled=false`, `live_approved=false`.
