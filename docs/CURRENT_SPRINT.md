# SPRINT 2 — IN PROGRESS
## DEVELOPMENT PAUSED FOR REVIEW
- **LAST PASS:** S2.12AB
- **NEXT CODE TASK AFTER REVIEW:** S2.13AB
- **NEXT ACTION:** ARCHITECTURE_AND_SPEC_REVIEW

Estado: `IN_PROGRESS`. Rama: `codex/sprint-2`.
Objetivo: Implementar el contrato temporal Point-In-Time universal, ingesta de universo Nasdaq y snapshots históricos.

> [!IMPORTANT]
> El desarrollo está **PAUSADO** para una revisión planificada de arquitectura y especificación contra la especificación v6.4, el documento de ejecución de sprint, el Prompt Master y las decisiones acumuladas en Sprint 2.
> **NO CONTINUAR LA IMPLEMENTACIÓN DE S2.13AB AUTOMÁTICAMENTE.**

## Capacidades completadas en Sprint 2

### 1. Núcleo Temporal (PIT Core)
- Contrato temporal Point-in-Time (S2.1B) en `docs/DECISIONS.md`: regla universal de elegibilidad histórica `available_at <= as_of` (inclusive).
- Enforzamiento estricto de timezone UTC en todos los timestamps (`require_utc`).
- Test de aceptación PIT para eventos futuros conocidos (S2.1C) en `tests/test_temporal_baseline.py`.
- Protocolo genérico `PointInTimeRepository` (S2.2A) en `app/application/ports.py` (`get_as_of`, `scan_as_of`, `latest_available`).
- Suite de pruebas de aceptación PIT (S2.2B) en `tests/test_pit_acceptance.py`.
- Implementación de operaciones PIT en `InstrumentRepository` (S2.3A) en `app/infrastructure/storage/sqlite.py`.
- Split semántico temporal (S2.3B): `TemporalEvidence` permite hechos con vigencia futura conocidos previamente; `MarketObservation` restringe observaciones de mercado a `event_time <= available_at`.
- Criterio de desempate y ordenamiento determinista: `available_at DESC, version DESC` sin introducir `event_time` como filtro general.

### 2. Dominio de Identidad y Universo Histórico (S2.5)
- `InstrumentVersion` (S2.5A) en `app/domain/models.py`: versionado histórico efectivo con `valid_from` y `valid_to`.
- `SymbolAlias` (S2.5B): intervalo semiabierto `[valid_from, valid_to)` e identidad canónica estable `instrument_id`.
- `CorporateAction` (S2.5C): 8 tipos canónicos de eventos corporativos sin mutación de identidad.
- `HistoricalUniverseSnapshot` (S2.5D): membresía basada en tupla de `instrument_ids` estables únicos sin deduplicación silenciosa.

### 3. Persistencia de Universo Histórico — Migración 002 (S2.6)
- Tabla `source_ingestions` (S2.6A): procedencia, SHA256 (64 hex), verificación de orden temporal (`received_at <= processed_at <= available_at`, `source_timestamp <= available_at`) y status restringido.
- Tabla `universe_snapshots` (S2.6B): metadatos de snapshots con FK a `source_ingestions`.
- Tabla `universe_snapshot_members` (S2.6C): membresía normalizada por `instrument_id` con clave foránea compuesta `(instrument_id, provider, feed, instrument_version) -> instrument_versions`.
- Suite de aceptación y hardening (S2.6D, 22 casos).
- **`002_universe.sql` está FORMALMENTE CONGELADA / INMUTABLE.**

### 4. Ruta de Lectura de Universo Histórico (S2.7)
- Protocolo `HistoricalUniverseRepository` (S2.7A) en `app/application/ports.py` con `get_as_of` y `members_as_of`.
- Suite de aceptación conductual (S2.7B, 18 casos) en `tests/test_historical_universe_repository_acceptance.py`.
- Implementación SQLite `SQLiteHistoricalUniverseRepository` (S2.7C) en `app/infrastructure/storage/sqlite.py`.
- Elegibilidad dual temporal estricta: `available_at <= query_time` Y `snapshot.as_of <= query_time`.
- Desempate determinista cuádruple: `as_of DESC, available_at DESC, version DESC, snapshot_id ASC`.
- Membresía canónica ordenada por `instrument_id ASC`.
- Preservación estricta de `None` (sin snapshot elegible) vs `()` (snapshot explícitamente vacío); sin fallback a universo actual.
- No retroactividad de revisiones verificada.

### 5. Pipeline de Proveedor Nasdaq (S2.8 & S2.9)
- 10 fixtures crudos deterministas en `tests/fixtures/nasdaq/*.txt` y suite de integridad en `tests/test_nasdaq_fixtures.py` (12 PASS).
- Parser estricto y determinista `parse_nasdaqlisted` (S2.8B) en `app/infrastructure/providers/nasdaq.py` con DTOs `NasdaqListedRawRecord` y `NasdaqListedFile` (18 PASS). Validación estricta del encabezado oficial (8 columnas) y footer `File Creation Time`.
- Normalizador determinista de registros `normalize_nasdaq_record` (S2.9A) con DTO `NasdaqNormalizedRecord` (25 PASS).
- Normalizador determinista de archivo `normalize_nasdaqlisted` (S2.9B) con DTO `NasdaqNormalizedFile` (13 PASS).
- Preservación estricta de evidencia de proveedor: filas duplicadas, test issues, financial status codes, sin inferencia de identidad.

### 6. Resolver Temporal de Identidad (S2.10)
- Resolver neutral de proveedor `resolve_symbol_identity` (S2.10A) en `app/application/identity.py`:
  - Dos ejes temporales: corte de conocimiento (`available_at <= query_time`) e intervalo efectivo (`valid_from <= effective_time < valid_to`).
  - DTO `IdentityResolution` con estados `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS` y razones deterministas.
  - Suite de aceptación de 27 casos en `tests/test_identity_resolver.py`.
- Orquestación sobre archivo Nasdaq `resolve_nasdaq_identities` (S2.10B) en `app/infrastructure/providers/nasdaq.py` (19 PASS en `tests/test_nasdaq_identity_resolution.py`).
  - Soporte de transiciones de ticker y reutilización de ticker con evidencia explícita de `SymbolAlias`.
  - Cero inferencia por similitud de nombres, sin asignación automática de identidades, sin fallback hacia atrás desde estado actual.

### 7. Gate de Persistencia de Identidad y Almacén de Procedencia Cruda (S2.11)
- Gate de persistencia de identidad (S2.11A): función pura `build_identity_persistence_gate` y enum `PersistenceEligibility`:
  - `RESOLVED` -> `ELIGIBLE` (propaga `instrument_id`).
  - `UNRESOLVED` -> `PENDING_IDENTITY` (`instrument_id = None`).
  - `AMBIGUOUS` -> `IDENTITY_CONFLICT` (`instrument_id = None`).
  - Suite de 25 casos en `tests/test_identity_persistence_gate.py`.
- Almacén de procedencia cruda `RawIngestionStore` / `save_raw_ingestion` (S2.11B) en `app/infrastructure/storage/raw.py`:
  - Almacenamiento inmutable content-addressed en filesystem: `<raw_root>/<provider>/<feed>/<sha256>.raw`.
  - Cálculo interno obligatorio de SHA256.
  - Registro idempotente en tabla `source_ingestions` mediante clave `(provider, feed, source_name, sha256)` con transacción atómica `BEGIN IMMEDIATE`.
  - Validación de cadena temporal UTC (`received_at <= processed_at <= available_at`, `source_timestamp <= available_at`).
  - Suite de 30 casos en `tests/test_raw_ingestion_store.py`.

### 8. Ruta de Escritura de Universo Histórico (S2.12)
- Contrato de aplicación `HistoricalUniverseWriteRepository` (S2.12A) en `app/application/ports.py`.
- Estructura `HistoricalUniverseMemberRef` y excepción `HistoricalUniverseWriteConflict` en `app/application/universe.py`.
- Suite de contrato (12 casos) en `tests/test_historical_universe_write_contract.py`.
- Implementación SQLite `SQLiteHistoricalUniverseWriteRepository` (S2.12B) en `app/infrastructure/storage/sqlite.py`:
  - Transacción atómica unitaria con `BEGIN IMMEDIATE` para snapshot y miembros.
  - Replay idéntico idempotente retorna `False`.
  - Replay con metadatos o membresía divergente lanza `HistoricalUniverseWriteConflict`.
  - Validación de paridad de conjuntos `snapshot.instrument_ids == {m.instrument_id for m in members}` y rechazo de duplicados.
  - Inserción canónica ordenada por `instrument_id ASC`.
  - Claves foráneas estrictas enforced (`source_ingestion_id -> source_ingestions`, `(instrument_id, provider, feed, instrument_version) -> instrument_versions`).
  - Sin generación artificial de IDs, sin inferencia de versiones, sin mutación por UPSERT (`INSERT OR REPLACE` prohibido).
  - Soporte de snapshots futuros (`available_at < as_of`), de disponibilidad tardía (`as_of < available_at`), y eventos `event_time > available_at`.
  - No retroactividad de revisiones verificada.
  - Suite de aceptación (31 casos) en `tests/test_historical_universe_writer_acceptance.py`.

## Aún no implementado (Pendiente en Sprint 2)

- Orquestación canónica de ingesta de universo Nasdaq
- Flujo de refresco automático de proveedor
- Política de calidad de datos (DataQuality / ingestion policy)
- Adaptador HTTP de Nasdaq con manejo de reintentos/fallos
- CLI de refresco manual de universo
- Endpoint REST `/v1/universe`
- Filtrado de invertibilidad
- Materialización de universo operativo actual
- Política automatizada de creación de `SymbolAlias`
- Política de asignación canónica de nuevos instrumentos
- Ingesta de proveedores de acciones corporativas
- Bloque final de regresión histórica de supervivencia / ticker changes
- Hardening final de Sprint 2
- Cierre final de documentación de Sprint 2

> [!WARNING]
> El Sprint 2 está `IN_PROGRESS`. La Etapa 1 NO se presenta como DATA READY y Nasdaq NO está completamente integrado en producción.

## Alcance de la próxima revisión de arquitectura y especificación

Categorías de evaluación:
- **KEEP:** Decisiones y contratos que deben mantenerse sin cambio.
- **CHANGE:** Ajustes necesarios antes de continuar.
- **REMOVE:** Componentes o complejidades innecesarias.
- **DEFER:** Funcionalidades que deben postergarse a etapas posteriores.
- **SPEC_GAP:** Brechas entre la especificación v6.4 y la implementación actual.
- **TECH_DEBT:** Deuda técnica identificada.
- **NEXT:** Priorización del siguiente incremento funcional.

Áreas bajo inspección prioritaria:
1. Corrección temporal y prevención de look-ahead / revision bias.
2. Prevención de sesgo de supervivencia (survivorship bias).
3. Semántica de identidad de instrumentos, transiciones de ticker y reutilización de símbolos.
4. Procedencia, almacenamiento crudo inmutable y persistencia SQLite.
5. Idempotencia y atomicidad en rutas de lectura y escritura.
6. Fronteras modulares entre parser, normalizador, resolver de identidad y persistencia.
7. Cobertura de pruebas y eliminación de sobreingeniería.

## Evidencia y validación del estado pausado

- **Suite completa de pruebas pytest:** **388 PASS**, 0 fallos, 2 warnings upstream (Starlette/AnyIO deprecation).
- **Pruebas de contrato y aceptación de escritura S2.12:** 43 PASS (`test_historical_universe_write_contract.py` [12], `test_historical_universe_writer_acceptance.py` [31]).
- **Regresión completa de repositorio de universo histórico:** 66 PASS.
- **Regresión completa de migraciones de universo:** 46 PASS.
- **Ruff check:** PASS en todo el proyecto.
- **Ruff format --check:** PASS en todo el proyecto.
- **Seguridad:** `live_trading_enabled = false`, `live_approved = false`.
- **Migración 001:** `001_foundation.sql` inalterada.
- **Migración 002:** `002_universe.sql` congelada e inmutable.
