# Decisiones

## 2026-10-21 — Sprint 3 EOD architecture freeze

### Provider

Se aprueba **Massive Stocks Daily Market Summary** como provider primario de Sprint 3,
mediante adapter reemplazable. El endpoint agrupado devuelve OHLCV diario para todo el
mercado US en una llamada por fecha. El baseline de desarrollo usa Stocks Basic/free;
Flat Files queda como upgrade posterior y no como dependencia del sprint.

Provider/feed canónico inicial:
- provider: `massive`
- feed: `grouped_daily`
- endpoint conceptual: `/v2/aggs/grouped/locale/us/market/stocks/{date}`

No se introduce SDK del vendor en domain/application. El transporte queda detrás de un adapter.

### Precio observado vs ajustes

La evidencia canónica de Sprint 3 se solicita y almacena con `adjusted=false`.
No se guarda una serie split-adjusted como verdad primaria. Splits/dividendos/otros
ajustes pertenecen a una capa derivada y versionada de corporate actions.

`adjustment_policy = raw` es LOCKED para persistencia canónica de este sprint.

### Identidad

El response agrupado puede contener miles de tickers. Raw conserva toda la respuesta.
Solo se materializan como `CanonicalDailyBar` aquellos registros cuyo símbolo puede
resolverse mediante evidencia explícita de identidad ya conocida. Los demás se
clasifican/quarantinan; no se crean `instrument_id` por ticker o nombre.

Sprint 3 NO amplía automáticamente identidad a NYSE/AMEX/OTC.

### CanonicalDailyBar

Sprint 3 introduce una especialización diaria explícita en lugar de debilitar
`CanonicalBar` existente. Debe contener como mínimo:
- `instrument_id`;
- `symbol` de proveedor;
- `session_date`;
- `event_time`/timestamp de ventana reportado por provider;
- OHLC;
- volume;
- VWAP opcional;
- trade_count opcional;
- OTC flag opcional;
- provider/feed/version;
- source/provenance;
- `adjustment_policy=raw`.

### Point-in-Time y backfill: SPEC_GAP resuelto por política de replay

No se falsificará `TemporalEvidence.available_at` moviéndolo artificialmente al pasado
cuando una descarga histórica se recibe hoy. El timestamp de ingestión real permanece
auditable.

Para replay EOD se define una capa separada y versionada:
`ReplayAvailabilityPolicy`.

V1 conservadora:
- una barra de sesión D solo puede consumirse en replay desde las 00:00 America/New_York
  del día calendario siguiente, convertidas a UTC;
- el valor es DERIVED/SYNTHETIC y conserva `policy_id`, `policy_version`;
- nunca reemplaza timestamps reales de provenance;
- live/shadow futuro no usa esta reconstrucción: usa disponibilidad observada real.

Esto permite investigación EOD sin mentir sobre cuándo se descargó el backfill y sin
habilitar señales intradía/same-day con información diaria.

### Storage

Raw:
- reutilizar almacenamiento inmutable/content-addressed.

Parquet:
- un archivo/fragmento por sesión, nunca por ticker;
- partición lógica por `provider/feed/session_date`;
- `instrument_id` y `symbol` son columnas;
- cada revisión es inmutable; no overwrite silencioso.

SQLite:
- metadata de particiones, source_ingestion, hashes, row_count, versión/revisión,
  quality y ReplayAvailabilityPolicy.

DuckDB:
- lectura analítica sobre Parquet.

Polars:
- batch/normalización/validación/feature input cuando exista beneficio medible.

### Missing data

No crear barras ficticias ni forward-fill en la capa canónica. Un ticker sin trade puede
no producir barra. Un response vacío se conserva como evidencia de fuente; la decisión
de si fue feriado/no-session corresponde a calendario/quality, no a inventar OHLC.

### Infraestructura

No Redis, Ray, MLflow, Kafka, Celery, Airflow, Spark, Kubernetes, Postgres ni TimescaleDB
en Sprint 3. Correctness, provenance y reproducibilidad preceden escalado.

## 2026-10-21 — S2.18 Universo operativo materializado

El universo operativo es una materialización separada y reproducible de un
`HistoricalUniverseSnapshot`, nunca una mutación o filtro de la evidencia histórica.
Su identidad es `(source_snapshot_id, policy_id, policy_version)`; el contenido de
decisiones por `instrument_id` debe coincidir exactamente en un replay o se rechaza por
conflicto. La política se inyecta explícitamente en el refresh: no existe un default
oculto dentro del repositorio. La migración `005` satisface este contrato y no se crea
`006`.

## 2026-09-10 — Corte del sprint 1

La sección 17 ordena bootstrap, modelos y registry antes de Nasdaq/EOD. Se cierra aquí
el primer incremento verificable. Se descartó incluir toda la Etapa 1 en un solo sprint.
Consecuencia: API vacía de mercado hasta la ingesta siguiente; no se presenta como DATA READY.

## 2026-09-10 — Python y persistencia local

Python 3.12, FastAPI/Pydantic, SQLite directo con transacciones y Parquet/DuckDB para
verificación de capacidades. Domain y ports no importan SDKs ni stores concretos.
Se difieren Polars, NumPy, APScheduler, Redis, MLflow y Ray hasta tener consumidores.
El lock fija dependencias; Docker usa instalación runtime sin extras de desarrollo.

## 2026-09-10 — Tiempo, identidad y revisiones

`event_time` representa vigencia del hecho; `available_at` la disponibilidad para consumirlo.
Se exige `received_at <= processed_at <= available_at` y ninguna fuente/fecha de publicación
posterior a disponibilidad. Una fecha programada futura vive en `scheduled_at`, separada
del instante de anuncio. Todos los datetimes del dato se normalizan a UTC y deben tener zona.

El contrato usa `event_time` como timestamp canónico en lugar del `timestamp` abreviado
de ejemplos anteriores del documento. Es una decisión explícita para este proyecto nuevo;
no existe contrato público previo que migrar.

La clave de revisión es `(instrument_id, provider, feed, version)`. Repetir un payload
equivalente no duplica; cambiarlo bajo la misma clave falla. `get_as_of` filtra antes
de seleccionar el estado vigente y después resuelve el ticker, evitando resucitar un alias
antiguo. Empates de fuentes/identidad requieren reconciliación (HTTP 409), sin mezcla silenciosa.
Esto no implementa aún snapshots de universo, ajustes ni corporate actions.

## 2026-09-10 — Migraciones y recuperación

SQL empaquetado, ordenado y registrado por nombre/checksum. `BEGIN IMMEDIATE` protege
DDL y registro en una transacción; un fallo revierte ambos. Un esquema futuro o checksum
alterado impide startup. Rollback de aplicación requiere schema compatible o restauración
de un backup; no se introdujeron downgrades ni comandos destructivos.

## 2026-09-10 — Proveedores y alcance operativo

Registry describe configuración, no entitlements verificados. Providers no conectados
permanecen DISABLED. Solicitar AI sin adapter produce DEGRADED opcional y no bloquea API.
No se introducen clientes externos ni flags que activen trading real. Los logs propios
excluyen query strings, payloads y mensajes de excepción para no revelar credenciales.

## 2026-09-10 — Continuidad

Se conserva copia de la especificación y archivos de handoff. No se ejecutó ni instaló Granite.
La distribución Astra/Granite del documento queda como workflow posible, no como una
acción solicitada automáticamente. Se usa el modelo activo de esta sesión para el incremento.

## Contrato temporal point-in-time (Point-in-Time Semantics)

Reglas oficiales y vinculantes para la semántica temporal y consultas históricas (freeze previo a `PointInTimeRepository`):

### 1. as_of
`as_of` es el timestamp de decisión o consulta histórica.
- Requisitos estrictos: timezone-aware y normalizado internamente a UTC.
- Los datetimes sin zona horaria (naïve datetimes) son inválidos y deben ser rechazados.

### 2. available_at
`available_at` es el instante más temprano en que la información pudo haber sido legalmente conocida o utilizada por el sistema.
- **Regla universal de elegibilidad histórica:**
  ```
  available_at <= as_of
  ```
- El límite es inclusivo: si `available_at == as_of`, la información **ES visible**.

### 3. event_time
`event_time` representa cuándo ocurrió o entra en vigor el hecho.
- **REGLA CRÍTICA:** Se rechaza explícitamente `event_time <= as_of` como regla universal de elegibilidad PIT (`EVENT_TIME_GLOBAL_FILTER=NO`). Definir `event_time <= as_of` como criterio universal sería incorrecto.
- **Eventos futuros programados:**
  - Ejemplo: al corte de `2026-09-01`, el sistema ya puede conocer que un evento de resultados (earnings) está programado para `2026-09-20`.
  - Por lo tanto, `event_time > as_of` es válido mientras `available_at <= as_of`, y el evento programado **debe ser visible**.

### 4. received_at / processed_at
- Representan timestamps de ingestión, auditoría y latencia.
- **NO deben sustituir** a `available_at`.
- **NO deben determinar** la elegibilidad histórica.

### 5. Revisiones (revisions)
- Para una consulta `as_of`, únicamente son elegibles las revisiones que satisfagan:
  ```
  available_at <= as_of
  ```
- Entre las revisiones elegibles, se debe retornar la revisión más reciente de forma determinista.
- Una revisión recibida o creada posteriormente debe permanecer estrictamente invisible para consultas históricas anteriores.

### 6. No retroactividad (non-retroactivity)
- Persistir o añadir una nueva revisión **NUNCA** debe alterar la respuesta de una consulta histórica previa.
- Ejemplo:
  - Revisión A: `available_at` = 10 de enero (Jan 10)
  - Revisión B: `available_at` = 20 de enero (Jan 20)
  - Consulta `as_of` 15 de enero (Jan 15) -> devuelve Revisión A.
  - Persistir la Revisión B posteriormente jamás debe alterar esa respuesta.

### 7. Código histórico y replay (historical/replay)
- El código histórico y de repetición (replay) **DEBE** utilizar exclusivamente APIs point-in-time, tales como:
  - `get_as_of(...)`
  - `scan_as_of(...)`
  - `latest_available(...)`
- Queda **estrictamente prohibido** utilizar un `get_latest()` sin restricciones para reconstruir la historia.

### 8. Desempate determinista (deterministic ties)
- Si múltiples registros comparten exactamente el mismo `available_at`, la resolución debe utilizar un ordenamiento determinista y explícito basado en `(revision / version / source)`.
- Los timestamps de auditoría (`received_at`, `processed_at`) no deben convertirse en criterios de elegibilidad.

## 2026-09-11 — Contrato HistoricalUniverseRepository (S2.7A)

Congela la semántica de resolución histórica de universo en `app.application.ports`.
`HistoricalUniverseRepository` es un contrato de aplicación independiente; no redefine
`PointInTimeRepository`.

- Eje de conocimiento: `available_at <= query_time` (inclusivo).
- Eje efectivo: `snapshot.as_of <= query_time` (inclusivo).
- Ambos son obligatorios. Conocido pero no vigente, o vigente pero no conocido, no es elegible.
- Alcance explícito por `provider` y `feed`. Sin combinación silenciosa de fuentes.
- Orden de selección entre elegibles: `as_of DESC`, `available_at DESC`, `version DESC`,
  `snapshot_id ASC`. No usar `event_time`, `received_at` ni `processed_at`.
- Sin fallback a universo actual: si no hay snapshot elegible, `get_as_of` y
  `members_as_of` retornan `None`.
- `members_as_of` distingue `None` (sin snapshot) de `()` (snapshot elegible vacío).
- La membresía canónica es `instrument_id`, no símbolo.
- `query_time` es timezone-aware; naïve se rechaza; no-UTC se normaliza con `require_utc`.
- Este freeze cubre solo lectura. Escrituras de ingesta quedan para un task posterior.

## 2026-09-11 — Orden canónico de membresía histórica (S2.7B)

`HistoricalUniverseSnapshot.instrument_ids` no tiene orden de negocio. La persistencia
(`universe_snapshot_members`) tampoco tiene ordinal. La reconstrucción del repositorio
debe devolver membresía ordenada por `instrument_id ASC`. El orden de inserción SQL y
el orden de símbolos no son semánticos. No se añade columna ordinal ni se modifica
`002_universe.sql`.

## 2026-09-11 — Congelamiento de migración 002_universe.sql (S2.6D)

- `002_universe.sql` contiene la persistencia de procedencia de ingesta (`source_ingestions`), metadatos de snapshots de universo (`universe_snapshots`) y membresía normalizada por `instrument_id` (`universe_snapshot_members`).
- La migración queda formalmente aceptada y congelada (frozen/inmutable) tras superar la suite de aceptación final S2.6D.
- Toda evolución o cambio futuro del esquema de base de datos deberá implementarse en migraciones sucesivas (`003_*.sql`, etc.).
- `001_foundation.sql` permanece inalterado e inmutable.
