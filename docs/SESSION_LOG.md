# Registro de sesiones

## 2026-09-10 — Codex GPT-6 — Sprint 1

Pedido: iniciar desde cero y avanzar sprint 1 a partir del DOCX v6.4.
Baseline: proyecto inexistente, sin tests anteriores. Se escribieron criterios y tests
de aceptación antes del código; la primera ejecución se realizó después de instalar
dependencias y completar implementación. No se afirma una ejecución RED previa.

Archivos: proyecto nuevo en `bot-inversiones/`; app, tests, configuración, empaquetado,
Docker/Compose, scripts, docs, lock y referencia original. Rama `codex/sprint-1` sin commits.

Comandos/evidencia:

- Inspección del workspace y Git padre: otros proyectos preservados, sin baseline de inversiones.
- Lectura XML del DOCX y SHA256: copia de referencia verificada.
- Venv Python 3.12.14; `pip install uv` y `uv sync --extra dev` completados con acceso de red autorizado.
- Primera prueba: 22 PASS; ruff detectó formato, corregido con format/import sorting.
- Suite ampliada de fallos/atomicidad/provenance: 30 PASS, 2 warnings upstream.
- `scripts/check.ps1`: ruff/format PASS; 30 PASS en 2.29s; smoke HTTP real PASS.
- `uv build --offline --cache-dir .venv/uv-cache`: wheel y sdist generados.
- Instalación offline de dependencias en venv de prueba: caché insuficiente, no completada.
  Se verificó el wheel local con `--no-deps`, reutilizando dependencias instaladas y comprobando
  que `app` proviniera del wheel. Bootstrap y migración empaquetada PASS.
- `docker compose --profile core config --quiet`: exit 0; avisos de config Docker del usuario.
- `docker version`: motor no disponible; build/runtime no ejecutados.
- `python -m app`: API iniciada en puerto 8000; GET system/health devuelve AVAILABLE y live false.

Decisiones: corte bootstrap/modelos/registry, UTC y versiones inmutables, servicios externos
pospuestos, estado persistido. No se delegó a Granite ni se configuró modelo local.

Pendiente operativo: Docker build/runtime. Próximo incremento funcional: Nasdaq universe
con fixtures y política temporal; ver ROADMAP.md. No hay commits ni publicación remota.

## 2026-09-10 — Codex — S1.7 Final Contract Alignment

Se leyó el handoff Astra -> Granite y se verificó el root `bot-inversiones`, rama
`codex/sprint-1` y commits existentes antes de modificar. Se completaron las partes que
faltaban: `app/core/ids.py` es la única fuente de UUID; `DomainError` es una excepción
con payload público seguro; el middleware propaga request/correlation IDs; y se añadieron
aliases `/health`, `/ready`, `/api/system/capabilities` al mismo handler que sus rutas base.

Comandos/evidencia:

- `python -m pytest -q`: 33 PASS, 2 warnings upstream.
- `ruff check .` y `ruff format --check .`: PASS.
- `scripts/smoke_http.py`: PASS; incluye los tres aliases y las rutas originales.
- Security scan de código: no hay LiveBroker, submit_order, endpoints de broker/order ni flags live true.
- `docker version`: daemon no disponible; `docker compose --profile core config --quiet`: PASS.

Docker runtime queda PENDING, no bloqueante por regla explícita del handoff. El próximo owner
es Astra para revisión final; después corresponde el Sprint 2 del universo Nasdaq.

## 2026-09-10 — Antigravity — Sprint 2: S2-TEMPORAL-NASDAQ-UNIVERSE

Implementación del núcleo temporal Point-In-Time (PIT) bajo especificación v6.4:
- S2.1B: Congelación oficial del contrato temporal en `docs/DECISIONS.md`. Regla universal `available_at <= as_of`.
- S2.1C: Test de aceptación para eventos futuros conocidos (`tests/test_temporal_baseline.py`).
- S2.2A: Protocolo genérico `PointInTimeRepository` en `app/application/ports.py` con `get_as_of`, `scan_as_of`, `latest_available`.
- S2.2B: Suite de aceptación conductual `tests/test_pit_acceptance.py` con los 9 casos mandatorios (RED inicial esperado).
- S2.3A: Implementación de operaciones PIT en `InstrumentRepository` (`sqlite.py`), eliminación de filtro global `event_time <= as_of`.
- S2.3B: Split semántico (`MarketObservation` para `CanonicalBar`, `CanonicalQuote`, `CanonicalTrade` con `event_time <= available_at`), ordenamiento determinista por `available_at DESC, version DESC`, actualización de tests de aceptación y sincronización del estado persistente a Sprint 2 en rama `codex/sprint-2`.

Comandos/evidencia:
- `pytest -q`: 51 PASS, 2 warnings upstream.
- `ruff check .` y `ruff format --check .`: PASS.
- Seguridad: `live_trading_enabled = false`, `live_approved = false`.
- Pendientes en S2: `InstrumentVersion`, `SymbolAlias`, `CorporateAction`, `HistoricalUniverseSnapshot`, ingesta Nasdaq, universe API.

## 2026-09-11 — Antigravity — Sprint 2: S2.5 Domain Contracts & S2.6 Persistence Hardening

Implementación de contratos de dominio de universo y persistencia SQLite bajo v6.4:
- S2.5A: Contrato `InstrumentVersion` en `app/domain/models.py`, validación UTC estricta y soporte de versiones con vigencia futura (`available_at < valid_from`).
- S2.5B: Contrato `SymbolAlias` con semántica de intervalos semiabiertos `[valid_from, valid_to)` y preservación de identidad estable `instrument_id` sin inferencia.
- S2.5C: Contrato `CorporateAction` con 8 tipos canónicos de acciones corporativas (`ticker_change`, `split`, `reverse_split`, `dividend`, `merger`, `acquisition`, `spin_off`, `delisting`).
- S2.5D: Contrato `HistoricalUniverseSnapshot` con membresía explícita por `instrument_ids` estables y rechazo de duplicados sin deduplicación silenciosa.
- S2.6A: Migración `app/migrations/002_universe.sql` introduciendo la tabla `source_ingestions` con validación de hash SHA256 y orden temporal estricto (`received_at <= processed_at <= available_at`).
- S2.6B: Extensión de `002_universe.sql` con la tabla `universe_snapshots` y clave foránea a `source_ingestions`.
- S2.6C: Inclusión de la tabla `universe_snapshot_members` con clave foránea compuesta hacia `instrument_versions(instrument_id, provider, feed, version)`.
- S2.6D: Suite de pruebas de aceptación final de migración (22 casos en `tests/test_universe_migration_acceptance.py`) y congelación oficial de la migración `002_universe.sql`.
- S2.6E: Sincronización de estado persistente del proyecto.

Comandos/evidencia:
- `pytest -q`: 153 PASS, 0 fallos, 2 warnings upstream.
- `ruff check .` y `ruff format --check .`: PASS.
- Migración `001_foundation.sql`: inalterada byte-por-byte.
- Migración `002_universe.sql`: congelada e inmutable tras aceptación S2.6D.
- Seguridad: `live_trading_enabled = false`, `live_approved = false`.
- Próxima acción: S2.7 Implementación de `HistoricalUniverseRepository`.

## 2026-09-11 — Antigravity — Sprint 2: S2.7 Historical Universe Repository

Implementación y aceptación del repositorio de universo histórico bajo especificación v6.4:
- S2.7A: Contrato de aplicación `HistoricalUniverseRepository` en `app/application/ports.py`. Elegibilidad dual: `available_at <= query_time` Y `snapshot.as_of <= query_time`. Selección determinista: `as_of DESC, available_at DESC, version DESC, snapshot_id ASC`. Distinción estricta de `None` (sin snapshot) vs `()` (snapshot vacío).
- S2.7B: Suite de pruebas de aceptación conductual (18 casos mandatorios) en `tests/test_historical_universe_repository_acceptance.py`.
- S2.7C: Implementación `SQLiteHistoricalUniverseRepository` en `app/infrastructure/storage/sqlite.py` con ordenamiento determinista cuádruple, ordenamiento de miembros por `instrument_id ASC` y sin fallback a universo actual.
- S2.7D: Sincronización de estado persistente del proyecto.

Comandos/evidencia:
- `pytest -q`: 176 PASS, 0 fallos, 2 warnings upstream.
- Pruebas dirigidas de contrato S2.7A: 5 PASS (`test_historical_universe_repository_contract.py`).
- Pruebas de aceptación S2.7B/C: 18 PASS (`test_historical_universe_repository_acceptance.py`).
- `ruff check .` y `ruff format --check .`: PASS.
- `002_universe.sql`: congelada e inmutable.
- `PointInTimeRepository`: inalterado.
- Seguridad: `live_trading_enabled = false`, `live_approved = false`.
- Próxima acción: S2.8 Implementación de fixtures de universo Nasdaq.

## 2026-09-11 — Antigravity — Sprint 2: S2.8AB Nasdaq Raw Fixtures & Deterministic Symbol Directory Parser

Implementación de fixtures crudos y parser determinista del Symbol Directory de Nasdaq (nasdaqlisted.txt) bajo v6.4:
- Inspección de documentación oficial en Nasdaq Trader: esquema congelado oficial `Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares` (8 columnas) y footer `File Creation Time: mmddyyyyhhmm|||||||`.
- Fase A: Creación de los 10 fixtures mandatorios en `tests/fixtures/nasdaq/*.txt` y suite de integridad `tests/test_nasdaq_fixtures.py` (12 PASS).
- Fase B1: Suite de aceptación de parser en `tests/test_nasdaq_parser.py` (18 casos, RED válido inicial antes de implementar).
- Fase B2: DTOs inmutables `NasdaqListedRawRecord` y `NasdaqListedFile`, y parser determinista `parse_nasdaqlisted` en `app/infrastructure/providers/nasdaq.py`.
- Validación estricta de esquema y formato de footer; separación de metadatos de creación de archivo; soporte de universo vacío; preservación de evidencia cruda (duplicados, test issues, financial status, variantes de símbolos); rechazo de malformaciones y extensiones no documentadas.
- Sin inferencia de identidad, sin normalización de dominio, sin base de datos, sin acceso a red en runtime de parser.

Comandos/evidencia:
- Fixtures tests: 12 PASS (`test_nasdaq_fixtures.py`).
- Parser tests: 18 PASS (`test_nasdaq_parser.py`).
- Combined tests: 30 PASS en 0.50s.
- Full suite: 206 PASS, 2 warnings upstream.
- `ruff check`: PASS en todo el proyecto.
- `ruff format --check`: PASS en todo el proyecto.
- Migraciones: `001_foundation.sql` y `002_universe.sql` inalteradas y congeladas.
- Contratos de dominio y repositorios: inalterados.
- Próxima acción: S2.9 Normalización/resolución de identidad de universo Nasdaq.

## 2026-09-11 — Antigravity — Sprint 2: S2.9AB Nasdaq Record Normalization + File Normalization

Implementación del pipeline determinista de normalización de registros y archivos del Symbol Directory de Nasdaq bajo v6.4:
- Fase A: Normalización de registros individuales `NasdaqListedRawRecord -> NasdaqNormalizedRecord`. Tipado determinista de `market_category` (Q, G, S), `test_issue` (bool), `financial_status` (N, D, E, Q, G, H, J, K), `round_lot_size` (int >= 1), `is_etf` (bool), `is_nextshares` (bool) y validación de símbolos (`^[A-Z0-9.]{1,14}$`) sin inferencia de identidad.
- Fase A1: Suite de aceptación de normalización de registros en `tests/test_nasdaq_normalizer.py` (25 casos, RED inicial válido).
- Fase A2: Implementación de `normalize_nasdaq_record` y `NasdaqNormalizedRecord` en `app/infrastructure/providers/nasdaq.py` (25 PASS, GATE A cumplido).
- Fase B: Normalización por lotes `NasdaqListedFile -> NasdaqNormalizedFile` mediante `normalize_nasdaqlisted` con política all-or-nothing, preservación estricta de orden de filas de procedencia, preservación de duplicados, soporte de universo vacío y preservación de timestamp crudo del footer.
- Fase B1: 13 casos de aceptación de archivo (RED inicial válido).
- Fase B2: Implementación de `NasdaqNormalizedFile` y `normalize_nasdaqlisted` (38 PASS en normalizer).
- Sin inferencia de identidad (`instrument_id`), sin conversión a modelos de dominio (`Instrument`, `InstrumentVersion`), sin filtrado de elegibilidad comercial, sin persistencia y sin acceso a red.

Comandos/evidencia:
- Normalizer tests: 38 PASS (`test_nasdaq_normalizer.py`).
- Combined Nasdaq block: 68 PASS (`test_nasdaq_fixtures.py`, `test_nasdaq_parser.py`, `test_nasdaq_normalizer.py`).
- Full test suite: 244 PASS, 2 warnings upstream.
- `ruff check`: PASS en todo el repositorio.
- `ruff format --check`: PASS en todo el repositorio.
- Modelos de dominio, puertos, migraciones y SQLite: inalterados.
- Próxima acción: S2.10 Resolución de identidad de universo Nasdaq.

## 2026-09-11 — Antigravity — Sprint 2: S2.10AB Temporal Identity Resolver & Nasdaq Identity Resolution

Implementación del resolver temporal de identidad y resolución sobre archivos normalizados de Nasdaq bajo v6.4:
- Fase A: Resolver genérico neutral de proveedor `resolve_symbol_identity` en `app/application/identity.py` usando evidencia explícita de `SymbolAlias`.
  - Dos ejes temporales independientes: `query_time` (`available_at <= query_time`) y `effective_time` (`valid_from <= effective_time < valid_to`).
  - DTO `IdentityResolution` con estados `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS` y motivos `EXPLICIT_ALIAS`, `NO_ELIGIBLE_ALIAS`, `CONFLICTING_IDENTITIES`.
  - Múltiples alias con el mismo `instrument_id` resuelven a dicho ID; múltiples alias con IDs distintos producen `AMBIGUOUS` con `instrument_id=None`.
  - Validación estricta de timezone UTC (rechazo de naïve con ValueError, normalización de aware a UTC).
  - Suite de aceptación: 27 PASS (`tests/test_identity_resolver.py`, RED inicial válido).
- Fase B: Orquestación a nivel de proveedor `resolve_nasdaq_identities` en `app/infrastructure/providers/nasdaq.py`.
  - DTOs `NasdaqIdentityRecord` y `NasdaqIdentityResolutionFile`.
  - Preservación estricta de orden de filas de procedencia y filas duplicadas (resueltas independientemente).
  - Soporte de transiciones de ticker (`OLD -> NEW`), reutilización de tickers (`ABC -> INST-1` luego `ABC -> INST-2`), alias conocidos a futuro y conocidos tardíamente.
  - Cero inferencia de identidad por nombre, sin fallback hacia atrás desde estado actual, sin síntesis de `CorporateAction`, sin creación de `SymbolAlias`, sin asignación/generación de IDs artificiales.
  - Suite de aceptación: 19 PASS (`tests/test_nasdaq_identity_resolution.py`, RED inicial válido).

Comandos/evidencia:
- Identity tests: 27 PASS (`test_identity_resolver.py`).
- Nasdaq identity tests: 19 PASS (`test_nasdaq_identity_resolution.py`).
- Pipeline completo Nasdaq + Identity: 114 PASS en 0.73s.
- Full test suite: 290 PASS, 2 warnings upstream.
- `ruff check`: PASS en todo el repositorio.
- `ruff format --check`: PASS en todo el repositorio.
- Modelos de dominio, puertos, migraciones y SQLite: inalterados.
- Próxima acción: S2.11 Flujo de ingesta y procedencia de snapshots de universo Nasdaq.

## 2026-09-11 — Antigravity — Sprint 2: S2.11AB Identity Persistence Gate & Raw Provenance Store

Implementación de las dos fases del gate de persistencia y almacenamiento de procedencia cruda:
- Fase A: Gate de persistencia de identidad neutral en `app/application/identity.py`:
  - Enum `PersistenceEligibility` (`ELIGIBLE`, `PENDING_IDENTITY`, `IDENTITY_CONFLICT`).
  - DTOs `NasdaqIdentityGateRecord` y `NasdaqIdentityPersistenceGate`.
  - Función pura `build_identity_persistence_gate(resolved, *, source_timestamp, received_at, processed_at, available_at, provider, feed)`.
  - Mapeo determinista: `RESOLVED` -> `ELIGIBLE` (propaga `instrument_id`), `UNRESOLVED` -> `PENDING_IDENTITY` (`instrument_id=None`), `AMBIGUOUS` -> `IDENTITY_CONFLICT` (`instrument_id=None`).
  - Suite de aceptación: 25 PASS (`tests/test_identity_persistence_gate.py`, RED inicial válido).
- Fase B: Almacén de procedencia cruda `RawIngestionStore` / `save_raw_ingestion` en `app/infrastructure/storage/raw.py`:
  - Layout content-addressed en sistema de archivos: `<raw_root>/<provider>/<feed>/<sha256>.raw`.
  - Cálculo de hash SHA256 interno obligatorio a partir de los bytes recibidos.
  - Escritura atómica a disco mediante archivo temporal (`mkstemp`), flush, fsync y reemplazo (`os.replace`).
  - Inserción idempotente en tabla `source_ingestions` con clave compuesta `(provider, feed, source_name, sha256)` y transacción inmediata `BEGIN IMMEDIATE`.
  - Validación rigurosa de cadena temporal UTC (`received_at <= processed_at <= available_at`, `source_timestamp <= available_at`) y restricción de status (`PENDING`, `SUCCESS`, `DEGRADED`, `FAILED`).
  - DTO `RawIngestionResult` con UUIDv4 para `ingestion_id`, digest y ruta de archivo.
  - Suite de aceptación: 30 PASS (`tests/test_raw_ingestion_store.py`, RED inicial válido).
- S2.11C: Revalidación completa de la suite de regresión en Windows utilizando un directorio temporal local (`--basetemp="$baseTemp"`), demostrando que las fallas previas correspondían a permisos del directorio temporal global de Windows.
  - Regresión de migraciones de universo: 46 PASS.
  - Regresión dirigida de S2.11: 101 PASS.
  - Suite completa: 345 PASS, 2 warnings upstream, 0 fallos, 0 errores.
  - Ruff check y Ruff format: PASS.

## 2026-09-11 — Antigravity — Sprint 2: S2.12AB Historical Universe Write Contract & SQLite Atomic Writer

Implementación del contrato de aplicación de escritura de universo histórico y su adaptador atómico SQLite:
- Fase A: Contrato de escritura y DTOs en capa de aplicación:
  - DTO inmutable `HistoricalUniverseMemberRef` y excepción `HistoricalUniverseWriteConflict` en `app/application/universe.py`.
  - Protocolo `HistoricalUniverseWriteRepository` en `app/application/ports.py` con firma `save_snapshot(snapshot, *, source_ingestion_id, members) -> bool`.
  - Semántica formal: retorna `True` si es nueva inserción; retorna `False` si es un replay exacto e idéntico; lanza `HistoricalUniverseWriteConflict` ante cualquier divergencia de metadatos o membresía.
  - Validación de paridad de conjuntos `snapshot.instrument_ids == {m.instrument_id for m in members}` y rechazo de IDs duplicados con `ValueError`.
  - Suite de pruebas de contrato: 12 PASS (`tests/test_historical_universe_write_contract.py`).
  - Suite de aceptación conductual inicial RED (31 casos en `tests/test_historical_universe_writer_acceptance.py`).
- Fase B: Implementación SQLite `SQLiteHistoricalUniverseWriteRepository` en `app/infrastructure/storage/sqlite.py`:
  - Transacción atómica unitaria mediante `BEGIN IMMEDIATE` para snapshot y todos sus miembros (todo o nada).
  - Enforzamiento estricto de claves foráneas con `PRAGMA foreign_keys=ON`:
    - `source_ingestion_id` debe existir previamente en `source_ingestions`.
    - Cada miembro `(instrument_id, provider, feed, instrument_version)` debe existir en `instrument_versions`.
  - Sin generación artificial de IDs; caller suministra `snapshot_id`.
  - Inserción canónica siempre ordenada por `instrument_id ASC`.
  - El orden de los miembros suministrados por el llamador no tiene significado semántico y no causa conflicto si es equivalente.
  - Replay idéntico detectado mediante lectura y comparación campo por campo de metadatos y miembros, retornando `False` sin mutar la BD.
  - Prohibido el uso de `INSERT OR REPLACE` u `ON CONFLICT DO UPDATE`.
  - Soporte de snapshots futuros (`available_at < as_of`), de disponibilidad tardía (`as_of < available_at`), y eventos `event_time > available_at`.
  - Verificación de no retroactividad de revisiones múltiples.
  - 31 pruebas de aceptación PASS en `tests/test_historical_universe_writer_acceptance.py`.
  - Regresión completa de repositorios de universo histórico: 66 PASS.
  - Regresión de migraciones de universo: 46 PASS.
  - Suite completa de pruebas pytest: 388 PASS, 2 warnings upstream, 0 fallos, 0 errores.
  - `ruff check .`: PASS.
  - `ruff format --check .`: PASS.

## 2026-09-11 — Antigravity — Sprint 2: S2-PAUSE-CHECKPOINT Development Pause / State Synchronization

Pausa formal del desarrollo para alineación arquitectónica y revisión de especificaciones:
- Estado del proyecto: `current_stage = 1`, `stage_1_data_ready = false`, `current_sprint = 2`, `sprint_status = "IN_PROGRESS"`, `development_status = "PAUSED_FOR_ARCHITECTURE_REVIEW"`.
- Última tarea completada: `S2.12AB` (PASS).
- Próxima acción obligatoria: `architecture_and_spec_review` (Revisión de arquitectura y especificación v6.4, Sprint execution doc, Prompt Master y decisiones de Sprint 2).
- Próxima tarea de implementación tras la revisión: `S2.13AB`.
- Evidencia verificada: 388 pruebas PASS, 2 warnings, 0 errores, Ruff check y format PASS.
- Migraciones `001_foundation.sql` y `002_universe.sql` permanecen inalteradas y congeladas.
- Ningún código de producción, tests ni migraciones fueron modificados durante este checkpoint.
- Se detiene el avance de código conforme a la directiva de Astra.
