# Handoff del proyecto

Spec 6.4. Etapa 1. Sprint: `S2-TEMPORAL-NASDAQ-UNIVERSE`.
Estado: `IN_PROGRESS`. Rama: `codex/sprint-2`.

## Actualmente completado (Sprint 2)

- **Contrato Point-In-Time:** Especificado en `docs/DECISIONS.md` y `app/application/ports.py` (`PointInTimeRepository`).
- **Pruebas de aceptación PIT:** 9 casos de aceptación mandatorios más pruebas de regresión en `tests/test_pit_acceptance.py`.
- **Implementación SQLite PIT:** `InstrumentRepository` implementa `get_as_of`, `scan_as_of` y `latest_available` en `app/infrastructure/storage/sqlite.py`.
- **Split semántico temporal:** `TemporalEvidence` permite hechos con vigencia futura conocidos previamente; `MarketObservation` restringe observaciones de mercado (`CanonicalBar`, `CanonicalQuote`, `CanonicalTrade`) a `event_time <= available_at`.
- **Ordenamiento determinista:** Desempate estricto por `available_at DESC, version DESC` sin `event_time`.

## Aún no implementado (Sprint 2)

- `InstrumentVersion`
- `SymbolAlias`
- `CorporateAction`
- `HistoricalUniverseSnapshot`
- Ingesta de universo Nasdaq
- API de consulta de universo

> [!WARNING]
> No se afirma que la Etapa 1 sea DATA READY ni que el Sprint 2 esté completo.

## Evidencia verificada en esta sesión

- `tests/test_pit_acceptance.py` y `tests/test_temporal_baseline.py`: 18 PASS.
- Suite completa pytest: 51 PASS, 0 fallos, 2 warnings upstream.
- `ruff check .`: PASS.
- `ruff format --check .`: PASS.
- Seguridad: `live_trading_enabled = false`, `live_approved = false`.

## Siguiente acción exacta

Astra valida el núcleo temporal de Sprint 2 (`S2-TEMPORAL-NASDAQ-UNIVERSE`); el siguiente bloque corresponde a los contratos de universo histórico (`HistoricalUniverseSnapshot`, `SymbolAlias`, `InstrumentVersion`).
