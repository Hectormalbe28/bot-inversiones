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
