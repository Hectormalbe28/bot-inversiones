# AI HANDOFF — Sprint 2 cerrado

## Estado actual

- Spec: 6.4
- Etapa: 1 — DATA foundation
- Stage 1 DATA_READY: false
- Sprint 2: CLOSED / PASS
- Branch: `codex/sprint-2`
- Implementación S2.18 aceptada: `cababbbad4cbabe3624cec5369dd2a6b13d49fac`
- CI de cierre aceptado: `1c25358bf5561ea61e22133bd04c71dddf735f5f`
- GitHub Actions run: 39660634890 — SUCCESS en Ubuntu y Windows
- Próxima acción: revisar y aprobar `docs/SPRINT_3_PROPOSAL.md`. No iniciar Sprint 3 sin aprobación explícita.

## Resultado del cierre

Sprint 2 construyó y verificó la base temporal e histórica del universo Nasdaq:

- contratos Point-in-Time con `available_at <= query_time`;
- identidad estable por `instrument_id`;
- `InstrumentVersion` y `SymbolAlias` temporales;
- snapshots históricos sin fallback al universo actual;
- raw inmutable y provenance;
- parser y normalizador Nasdaq;
- resolución temporal de identidad y cuarentena;
- pipeline canónico de ingesta y transporte HTTPS;
- API y CLI de consulta/refresco manual;
- quality report;
- universo operativo derivado y materializado por `policy_id/policy_version`;
- replay idempotente y conflicto ante divergencia.

La descarga real Nasdaq terminó correctamente en `QUARANTINED/PENDING_IDENTITY` sin aliases/versiones canónicas. Ese comportamiento es intencional: no se crean identidades artificiales ni snapshots parciales.

## Evidencia de cierre

GitHub Actions, Python 3.12, dependencias bloqueadas con `uv.lock`:

- Ubuntu: 419 PASS, 2 warnings; Ruff PASS; format PASS; HTTP smoke PASS.
- Windows: 419 PASS, 2 warnings; Ruff PASS; format PASS; HTTP smoke PASS.
- El bloqueo previo de TestClient queda clasificado como `ENVIRONMENT_BLOCKER_CONFIRMED` de la sandbox anterior.
- Regresión PIT/survivorship cubierta por tests: ticker change mantiene identidad, aliases tardíos no filtran hacia atrás, revisiones no son retroactivas, no existe current-universe fallback y snapshot ausente se distingue de snapshot vacío.
- `live_trading_enabled=false` y `live_approved=false`.

Warnings conocidos no bloqueantes:
- deprecación Starlette/FastAPI TestClient/httpx;
- alias de AnyIO deprecado;
- advertencia GitHub Actions sobre acciones basadas en Node.js 20 forzadas a Node.js 24.

## Invariantes que siguen LOCKED

1. `available_at <= query_time` es el corte de conocimiento histórico.
2. `event_time <= query_time` NO es un filtro PIT universal.
3. Todos los datetimes son timezone-aware UTC.
4. `instrument_id` es identidad canónica; ticker es evidencia de proveedor.
5. `SymbolAlias` usa intervalos `[valid_from, valid_to)`.
6. No fuzzy identity, no auto-creación por nombre/ticker.
7. No fallback histórico a universo actual.
8. Evidencia histórica y universo operativo son capas separadas.
9. Raw es inmutable/content-addressed.
10. Migraciones aceptadas no se reescriben.
11. Etapa 5 / trading real permanece prohibida.

## Próximo owner recomendado

Khazlo/Astra para revisar y autorizar Sprint 3. Granite/ejecutor solo después de un CURRENT_SPRINT nuevo y aprobado.
