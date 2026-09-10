# Sprint 1 — Fundación de la Etapa 1

Objetivo: iniciar una API local sin credenciales, con persistencia comprobada y contratos
de datos que conserven procedencia y disponibilidad temporal.

El documento v6.4 no fija un backlog numerado de sprints. Este corte implementa los tres
primeros puntos de la sección 17 y el bootstrap local descrito en v6.2/v6.3.

## Alcance

- Python 3.12+, FastAPI, settings, reloj UTC y logging JSON.
- Dominio separado de API e infraestructura.
- SQLite WAL/FTS5, migración versionada con checksum y repositorio temporal de instrumentos.
- Verificación real de lectura/escritura Parquet y consulta DuckDB al arrancar.
- Instrument, Bar, Quote, Trade, ActualityEvent, ScheduledEvent y ProviderStatus.
- Registry de proveedores desactivados, con tier/feed explícitos.
- Health, readiness, capabilities, providers e instrumentos consultables por as_of.
- Pruebas de aceptación, entorno bloqueado y archivos de continuidad.
- Dockerfile y Compose core; validación de contenedor sujeta a motor Docker disponible.

## Fuera de alcance

Descargas de proveedores, universo Nasdaq, EOD, streaming, scanner/watchlist, scheduler
durable, backtesting, research IA, integración Granite, Redis/MLflow/Ray y ejecución bursátil.
La Etapa 1 completa requiere sprints posteriores. No se interpreta el prompt maestro
incluido en el archivo como una solicitud del usuario de cambiar modelos o delegar.

## Criterios de aceptación

- [x] Arranque y OpenAPI sin claves ni servicios externos.
- [x] Configuración impide habilitar trading real o aprobación live.
- [x] SQLite WAL + FTS5 y migraciones repetibles; checksum alterado se rechaza.
- [x] Reinicio conserva instrumentos y revisiones; ingestión idéntica es idempotente.
- [x] as_of excluye información aún no disponible y no permite datetime sin zona.
- [x] Canonical OHLC, quotes, trades y fechas rechazan valores inválidos.
- [x] Providers opcionales quedan DISABLED; no se anuncia conectividad sin probarla.
- [x] Fallo de almacenamiento requerido impide startup; readiness detecta caída posterior.
- [x] Roundtrip Parquet/DuckDB ejecutado.
- [x] pytest y ruff pasan; documentación refleja evidencia y limitaciones reales.

## Comandos de verificación

```powershell
uv sync --extra dev --frozen
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
docker compose --profile core config --quiet
docker compose --profile core up --build -d
```

Archivos: app/, tests/, pyproject.toml, uv.lock, .env.example, Dockerfile,
compose.yaml, scripts/, docs/ y CHANGELOG.md.

Definition of Done: criterios funcionales PASS y estado/handoff actualizados.
Docker se reporta por separado si su motor no está disponible.

## S1.7 Final Contract Alignment

- [x] IDs de request y correlación centralizados en `app/core/ids.py`.
- [x] DomainError estructurado, con respuesta JSON segura y correlación por request.
- [x] Aliases `/health`, `/ready` y `/api/system/capabilities` reutilizan los handlers existentes.
- [x] Tests de IDs, errores y aliases ejecutados: 33 PASS.
- [x] Security check: no hay LiveBroker, submit_order ni rutas de órdenes; flags live false.
- [x] Smoke HTTP cubre los seis endpoints de contrato.
- [x] Docker detectado como no disponible; runtime `PENDING` no bloqueante según handoff.

Estado: `READY_FOR_ASTRA_FINAL_REVIEW` con `DOCKER_RUNTIME=PENDING`.

## Resultado registrado — 2026-09-10

LOCAL PASS: 33 pruebas, dos warnings de dependencias, ruff check/format y smoke HTTP real.
Wheel/sdist construidos; bootstrap del wheel instalado PASS reutilizando dependencias ya
verificadas. No se afirma una instalación completamente aislada sin acceso a red.
Compose config PASS. Docker build/runtime PENDING: motor no activo; no se arrancó Docker Desktop.
Estado global: `READY_FOR_ASTRA_FINAL_REVIEW`. La Etapa 1 completa sigue pendiente.
