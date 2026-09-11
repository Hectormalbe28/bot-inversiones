# Handoff del proyecto — SPRINT 2 PAUSE CHECKPOINT

Spec: 6.4. Etapa: 1. Sprint: `S2-TEMPORAL-NASDAQ-UNIVERSE`.
Estado: `IN_PROGRESS` (DESARROLLO PAUSADO PARA REVISIÓN DE ARQUITECTURA).
Rama: `codex/sprint-2`.
Último bloque completado: **S2.12AB** (PASS).

> [!CAUTION]
> **DO NOT CONTINUE IMPLEMENTATION AUTOMATICALLY.**
> El desarrollo está formalmente pausado. Ningún agente o desarrollador debe iniciar la implementación de S2.13AB ni código de ingesta hasta completar la revisión de arquitectura y especificación convocada por Astra.

## Invariantes Críticos que Rigen el Código

1. **Invariante Temporal PIT:**
   - La regla universal de elegibilidad histórica es estrictamente `available_at <= query_time`.
   - `as_of <= query_time` rige la vigencia efectiva de snapshots de universo.
   - Prohibido filtrar o descartar eventos por `event_time <= available_at` salvo en `MarketObservation`.
   - Todos los datetimes deben ser UTC-aware; los naïve son rechazados con `ValueError`.

2. **Invariante de Identidad:**
   - El símbolo bursátil (`symbol`) es solo evidencia de proveedor, NUNCA la clave de identidad `instrument_id`.
   - No se asignan `instrument_id` sintéticos o inventados.
   - Resolución de identidad requiere evidencia explícita de `SymbolAlias` en el intervalo semiabierto `[valid_from, valid_to)` con `available_at <= query_time`.
   - Cero inferencia por similitud de nombres, sin heurísticas difusas y sin fallback hacia atrás desde el estado actual.

3. **Invariante de Persistencia y Migración:**
   - `001_foundation.sql` está congelado.
   - `002_universe.sql` está FORMALMENTE CONGELADO / INMUTABLE. Contiene `source_ingestions`, `universe_snapshots` y `universe_snapshot_members`.
   - No crear migraciones `003` sin aprobación explícita de Astra.
   - Claves foráneas estrictamente habilitadas (`PRAGMA foreign_keys=ON`).

4. **Invariante de Escritura de Universo (S2.12):**
   - Transacción atómica unitaria mediante `BEGIN IMMEDIATE`: snapshot y todos los miembros se guardan juntos o nada se guarda.
   - Idempotencia exacta: mismo `snapshot_id` con metadatos y miembros equivalentes retorna `False` sin mutar la BD.
   - Replay conflictivo: cualquier divergencia en metadatos o miembros lanza `HistoricalUniverseWriteConflict`.
   - Prohibido el uso de `INSERT OR REPLACE` u `ON CONFLICT DO UPDATE` sobre registros históricos.
   - Inserción canónica siempre ordenada por `instrument_id ASC`.
   - La membresía no depende del orden en que se suministren los miembros.

## Estado Exacto del Pipeline Implementado

```
RAW bytes
   ↓
parse_nasdaqlisted (S2.8) -> NasdaqListedFile (estricto, valida header/footer)
   ↓
normalize_nasdaqlisted (S2.9) -> NasdaqNormalizedFile (tipado determinista)
   ↓
resolve_nasdaq_identities (S2.10) -> NasdaqIdentityResolutionFile (RESOLVED/UNRESOLVED/AMBIGUOUS)
   ↓
build_identity_persistence_gate (S2.11A) -> NasdaqIdentityPersistenceGate (ELIGIBLE/PENDING/CONFLICT)
   ↓
RawIngestionStore.save (S2.11B) -> Archivo inmutable content-addressed + registro source_ingestions
   ↓
SQLiteHistoricalUniverseWriteRepository.save_snapshot (S2.12) -> Transacción atómica en universe_snapshots + members
   ↓
SQLiteHistoricalUniverseRepository.get_as_of / members_as_of (S2.7) -> Lectura PIT dual temporal
```

## Lo que NO está implementado (No inventar ni asumir)

- No existe código para S2.13 (orquestación canónica de ingesta de universo Nasdaq).
- No existe cliente HTTP para descarga automática de Nasdaq.
- No existe CLI de refresco manual de universo.
- No existe endpoint REST `/v1/universe`.
- No existe política de calidad de datos (`DataQuality`) ni descarte por test issues / financial status.
- No existe materialización de universo operativo actual.
- No existe política de auto-creación de `SymbolAlias` ni de asignación de nuevos instrumentos.

## Próxima Acción Obligatoria: Revisión de Arquitectura y Especificación

Antes de reanudar código, se debe realizar una sesión de revisión exhaustiva comparando:
1. Implementación actual del repositorio.
2. Especificación base v6.4 (documento master).
3. Documento de ejecución de Sprint.
4. Prompt Master.
5. Decisiones acumuladas en Sprint 2.

Categorías de la revisión:
- `KEEP`: Lo que se mantiene congelado.
- `CHANGE`: Correcciones necesarias antes de avanzar.
- `REMOVE`: Simplificaciones o eliminación de sobreingeniería.
- `DEFER`: Diferir a etapas posteriores.
- `SPEC_GAP`: Brechas detectadas entre v6.4 y la implementación.
- `TECH_DEBT`: Deuda técnica a resolver.
- `NEXT`: Siguiente incremento funcional (S2.13AB tras la revisión).

## Evidencia Verificada en este Checkpoint

- **Full pytest:** **388 PASS**, 0 fallos, 2 warnings upstream (Starlette/AnyIO).
- **Ruff check:** PASS.
- **Ruff format --check:** PASS.
- **Seguridad:** `live_trading_enabled = false`, `live_approved = false`.
- **Branch:** `codex/sprint-2`.
