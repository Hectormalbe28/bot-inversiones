# Revisión de Arquitectura y Especificación — Sprint 2

Fecha de revisión: 2026-10-16.

## Veredicto

El diseño implementado hasta S2.12AB es consistente en sus contratos temporales, de
identidad y de persistencia. La continuación hacia S2.13AB quedó aprobada por el
usuario el 2026-10-16 para la persistencia operativa de identidad y resultados de
ingesta. S2.13A implementó la migración `003` y sus contratos; S2.13B añadió el
onboarding PIT de versiones canónicas; S2.13C materializó el pipeline offline; y
S2.13D añadió una descarga HTTPS explícita, acotada y probada con dobles.

No se debe publicar un snapshot de universo parcial ni crear identidades a partir de
un ticker o nombre de proveedor.

## KEEP

- La elegibilidad histórica universal es `available_at <= query_time`, inclusiva.
- La identidad estable es `instrument_id`; `symbol` solo es evidencia de proveedor.
- Los intervalos de `SymbolAlias` son `[valid_from, valid_to)` y usan el corte de
  conocimiento `available_at <= query_time`.
- Las migraciones `001_foundation.sql` y `002_universe.sql` permanecen inmutables.
- Los raw se direccionan por SHA-256; la escritura de snapshot y miembros es atómica,
  ordenada por `instrument_id` e idempotente ante replay exacto.
- La frontera parser -> normalizador -> resolver -> gate -> persistencia se mantiene.

## CHANGE — Decisiones requeridas antes de S2.13AB

### 1. Identidad persistida y onboarding canónico

`SymbolAlias` solo existe hoy como modelo y argumento en memoria. No hay tabla,
repositorio ni flujo administrativo que lo persista; tras un reinicio no hay evidencia
para resolver una descarga real. Además, `universe_snapshot_members` requiere que
cada `InstrumentVersion` exista ya por clave foránea.

S2.13A resolvió la persistencia PIT de aliases. S2.13B añadió la persistencia explícita
de `InstrumentVersion`, exige que exista el instrumento base y resuelve la versión por
tiempo efectivo y corte de conocimiento. La tabla existente
`instrument_versions` guarda payloads de `Instrument`, no de `InstrumentVersion`, y
por ello los registros de onboarding permanecen separados y enlazados por clave
foránea. S2.13C puede usar esa consulta PIT para construir un
`HistoricalUniverseMemberRef` correcto sin inventar versiones.

Decisión propuesta: crear en migración `003` un almacenamiento inmutable y temporal
para aliases, más un repositorio PIT de lectura. El alta/cambio de instrumento y alias
debe ser explícito, auditado y externo a S2.13; S2.13 solo lo consulta. No hay
autocreación por símbolo, nombre ni similitud.

### 2. Resultado de ingesta y conservación de raw inválido

`source_ingestions` identifica el contenido por `(provider, feed, source_name, sha256)`
en el repositorio actual. Si se guarda el raw como `PENDING` o `FAILED`, no existe una
transición posterior que pueda completar de forma inmutable el mismo intento con el
conteo validado y estado `SUCCESS`. Si se parsea antes de guardarlo, se pierde la
evidencia de un raw inválido.

Decisión propuesta: agregar en `003` un registro de intento/resultados separado de
`source_ingestions`, con estados terminales y referencia al raw. Así se conserva todo
payload descargado y se registran fallos de transporte, schema, normalización, calidad
e identidad sin alterar la evidencia previa.

### 3. Política de calidad y cobertura

Decisión propuesta para el proveedor-universo histórico:

- Conservar todas las filas recibidas como evidencia raw, incluidos `Test Issue=Y` y
  estados financieros no normales.
- No confundir calidad operativa/invertibilidad con membresía histórica del directorio.
  El filtrado de invertibilidad queda para scanner o un universo operativo posterior.
- Si una fila no puede resolver una identidad o es ambigua, el archivo queda en
  cuarentena de identidad y no produce snapshot publicable. Un snapshot parcial
  introduciría omisiones históricas y sesgo de supervivencia.
- Reportar conteos por `ELIGIBLE`, `PENDING_IDENTITY`, `IDENTITY_CONFLICT`, test issue
  y estado financiero para la corrección manual.

### 4. Tiempo, versión e idempotencia de snapshot

La especificación oficial de Nasdaq indica que el último registro contiene `File
Creation Time` y que sirve para valorar la actualidad del archivo, pero no aporta en
esa definición una zona horaria contractual para el sistema. El parser conserva el
valor crudo, pero no lo interpreta todavía.

Decisión propuesta: no convertir ni usar el timestamp de archivo como `as_of` hasta
documentar la zona horaria y el formato aceptado. S2.13 debe conservarlo como
evidencia raw; las timestamps de disponibilidad son UTC y se asignan al recibir y
procesar. La decisión definitiva de `as_of` y `source_timestamp` debe tener una
prueba de aceptación con fixture oficial.

El `snapshot_id` debe ser determinista y derivarse de proveedor, feed y SHA-256 del
raw. La semántica de `version` debe definirse para archivos distintos con el mismo
corte efectivo antes de depender de su orden de desempate.

### 5. Alcance del proveedor

S2.8-S2.12 cubren exclusivamente `nasdaqlisted.txt`: securities listados en Nasdaq.
No representan un universo amplio de acciones de EE. UU.; el directorio oficial trata
los valores de otras bolsas en un archivo separado. Mantener este alcance explícito
en S2.13. La ampliación a otras bolsas es un incremento posterior, no un cambio
silencioso de semántica.

## REMOVE / DEFER

- No scheduler ni refresh automático en S2.13.
- No endpoint REST de universo ni CLI antes del servicio offline probado.
- No política automática de creación de aliases.
- No infraestructura adicional: Redis, workers, colas o servicios distribuidos.
- No filtrado de invertibilidad dentro del snapshot de evidencia del proveedor.

## TECH DEBT

- `/v1/system/health` y la descripción de FastAPI aún indican Sprint 1.
- `PROJECT_STATE.json` y el checkpoint deben reflejar este resultado de revisión.
- La unicidad de idempotencia de `source_ingestions` se aplica desde el repositorio,
  no mediante una restricción `UNIQUE` del esquema.
- Un fallo de base de datos tras guardar raw puede dejar un archivo huérfano; falta un
  proceso de reconciliación.
- Falta una prueba end-to-end de bytes de proveedor hasta snapshot, con los resultados
  de cuarentena y replay incluidos.

## Plan de ejecución

1. **Aprobación de contrato S2.13**: decidir migración `003`, autoridad de identidad,
   política de cuarentena y semántica temporal del timestamp Nasdaq.
2. **S2.13A — Contratos y pruebas RED**: puertos, DTOs de resultado, política de
   calidad y pruebas de aceptación offline. No conexión de red.
3. **S2.13B — Onboarding de identidad**: repositorio para versiones canónicas de
   instrumento y una consulta PIT que devuelva la versión exacta para la membresía.
   No crea identidades desde Nasdaq; recibe altas explícitas y auditadas.
4. **S2.13C — Servicio canónico offline (completado)**: raw, parse, normalización, resolución,
   gate, cuarentena y persistencia de snapshot solo si la cobertura es completa y
   cada miembro tiene una versión canónica explícita.
5. **S2.13D — Adaptador Nasdaq (completado)**: transporte HTTPS explícito, timeout,
   reintentos transitorios acotados y pruebas con dobles. No dispara ingesta ni
   interpreta timestamps del archivo.
6. **S2.15 — Consumo**: endpoint histórico y CLI manual, únicamente después de la
   validación end-to-end de S2.13.

## Evidencia consultada

- Implementación y pruebas hasta S2.12AB en la rama `codex/sprint-2`.
- Especificación de referencia y Prompt Maestro.
- Handoff, decisiones y estado del Sprint 2.
- Definiciones oficiales de Nasdaq Symbol Directory, consultadas el 2026-10-16.
