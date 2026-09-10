# Siguientes incrementos

Orden global: Etapas 1, 2, 3, 4, 6, 5. La Etapa 5 sigue reservada.

1. Sprint 1: fundación local — código y validación local completados; Docker runtime pendiente.
2. Sprint 2: universo Nasdaq. Verificar documentación oficial y política de uso;
   fixtures de archivos de directorio, normalizador, reconciliación de identidad, ingestión
   idempotente, historial y endpoints de consulta. Conservar raw, hash, fecha de recepción
   y disponibilidad. No tratar el universo actual como histórico de fechas anteriores.
3. Sprint 3 propuesto: Massive EOD, repositorio Parquet particionado y consultas DuckDB.
4. Sprint 4 propuesto: scanner EOD con cálculos reproducibles y calidad de datos.
5. Incrementos posteriores: Alpaca IEX, buffers/microbatch, calendario/jobs durables,
   SEC/eventos, watchlist/catalizadores, knowledge y research opcional.

Los números posteriores al sprint 2 son planificación provisional, no alcance aprobado
para ejecutar automáticamente en esta sesión. El siguiente contrato detallado se escribirá
en CURRENT_SPRINT al comenzar sprint 2.
