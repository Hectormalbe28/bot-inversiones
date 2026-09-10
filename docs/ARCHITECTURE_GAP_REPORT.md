# Estado inicial y brechas

Inspección: 2026-09-10. El workspace contenía `clip-factory`, `output` y `tmp`;
no había proyecto de inversiones ni baseline de pruebas para él. El repositorio padre
estaba en `master`, sin commits, con esos directorios sin seguimiento.
Se creó `bot-inversiones/` con repositorio independiente y rama `codex/sprint-1`.
No se modificó código de los otros proyectos.

El documento contiene versiones acumuladas y prompts de rol. Se tomaron como requisitos
del producto sus contratos vigentes compatibles y el orden 1 → 2 → 3 → 4 → 6 → 5.
El pedido del usuario autoriza arrancar desde cero y avanzar sprint 1; no pide ejecutar
todos los prompts, cambiar modelo, instalar Granite o enviar tareas a otros modelos.

| Área | Inicial | Al cierre funcional del sprint 1 |
| --- | --- | --- |
| Config/API | Ausente | Implementado y probado |
| Persistencia metadata | Ausente | SQLite WAL, FTS5 y migraciones |
| Temporalidad | Ausente | Contrato UTC, disponibilidad y consulta de instrumentos as_of |
| Parquet/DuckDB | Ausente | Capacidad comprobada; repositorio de barras pendiente |
| Providers | Ausente | Registry y ports; adapters pendientes |
| Histórico de universo/corporate actions | Ausente | Pendiente; instrumento versionado es solo el primer contrato |
| Scanner/stream/watchlist | Ausente | Pendiente |
| Scheduler durable | Ausente | Pendiente |
| Knowledge/research IA | Ausente | Solo FTS5 preparado; funcionalidades pendientes |
| Etapas 2–6 | Ausente | Fuera del sprint 1 |
| Docker | Motor inaccesible | Compose válido; build/runtime sin verificar |

No existe evidencia de estrategia, rentabilidad ni datos de mercado reales. Las pruebas
usan fixtures sintéticos claramente identificados; no se cargan en la base operativa.
Health refresca SQLite/FTS5 por petición; motores y directorios conservan el resultado
y `checked_at` del bootstrap. No representa un monitor continuo de proveedores.
