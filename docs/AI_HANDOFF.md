# Handoff del proyecto

Spec 6.4. Etapa 1. Sprint S1-FOUNDATION listo para revisión final de Astra.
Estado: `READY_FOR_ASTRA_FINAL_REVIEW`; Docker runtime permanece `PENDING` y no bloquea
este cierre funcional según el handoff. Rama `codex/sprint-1`.

## Entregado

API en `app/main.py`, arranque `python -m app`, settings y logging JSON. Contratos en
`app/domain/models.py`; interfaces en `app/application/ports.py`. SQLite WAL/FTS5 con
migración empaquetada y transaccional. InstrumentRepository guarda revisiones inmutables
y consulta por `as_of`. Bootstrap verifica directorios y roundtrip Parquet/DuckDB.
Registry de nueve proveedores; ninguno descarga mercado. Swagger disponible en `/docs`.
Dockerfile/Compose y scripts Windows. `README.md` explica ejecución y límites. Los IDs
se generan solo desde `app/core/ids.py`; DomainError devuelve el contrato público seguro
con correlation ID. `/health`, `/ready` y `/api/system/capabilities` son aliases verificados.

La API se dejó iniciada en `http://127.0.0.1:8000` con la base local vacía.
Este es un dato de sesión, no garantía de que siga ejecutándose: verificar `/healthz`
antes de levantar otro proceso. Para reiniciar: `scripts/start.ps1` desde PowerShell.

## Evidencia

- `scripts/check.ps1`: PASS; ruff, format, 33 tests y smoke HTTP con proceso real.
- `uv build --offline --cache-dir .venv/uv-cache`: wheel/sdist PASS.
- Wheel instalado: bootstrap/SQL empaquetado PASS, usando dependencias del entorno principal.
- `docker compose --profile core config --quiet`: PASS.
- Consulta HTTP a la instancia local: `AVAILABLE`, versión `0.1.0`, live false.
- Copia del DOCX: SHA256 coincide con el original (ver reference/README.md).

## Pendientes y límites

Docker daemon no disponible; también emite aviso de lectura de configuración del usuario.
No se probaron Linux/contenedor, proveedores reales ni rendimiento con datos de mercado.
Hay dos deprecaciones upstream en Starlette/TestClient y AnyIO, sin fallos de pruebas.
Python 3.13 está permitido por metadata, pero la ejecución verificada fue Python 3.12.14.
No hay Granite local integrado, scheduler, universo histórico completo, corporate actions,
scanner, watchlist, backtesting ni IA. `last_completed_sprint` queda null hasta validar
el pendiente operativo; funcionalmente el sprint 1 está implementado.

## Siguiente acción exacta

Con motor Docker disponible: `docker compose --profile core up --build -d` y comprobar
readiness, usuario no-root y persistencia tras reinicio; actualizar el estado con evidencia.
Para continuar funcionalidad: Astra revisa el cierre S1.7. Después, definir sprint 2 del universo Nasdaq, verificar fuentes oficiales,
crear fixtures y tests de identidad/temporalidad antes del adapter y la ingesta. No reconstruir
esta base ni ejecutar automáticamente las instrucciones de rol del DOCX.
