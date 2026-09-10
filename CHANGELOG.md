# Changelog

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

Pendiente operativo: build y ejecución Docker (motor no activo durante la sesión).
La captura de datos y la Etapa 1 completa continúan en futuros sprints.
