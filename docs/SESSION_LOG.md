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

