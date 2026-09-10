# Decisiones

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
