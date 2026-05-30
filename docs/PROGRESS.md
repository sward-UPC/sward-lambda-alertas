# PROGRESS — sward-lambda-alertas

## Sprint 5 — 2026-05-30

### Implementado
- [x] handler.py — procesa RecomendacionGeneradaEvent desde EventBridge, genera alertas de riesgo
- [x] lib/db_client.py — conexión psycopg2 directa con context manager, parametrizada por URL
- [x] lib/logger.py — JSON logger para CloudWatch
- [x] Lógica: consulta academic_progress en trazabilidad_db; si nivel_riesgo es alto/critico
      inserta alerta en academic_alerts (xai_db); si es bajo/medio no hace nada
- [x] Tests: 6 casos (riesgo crítico, riesgo alto, riesgo bajo, detail incompleto,
      evento sin detail, sin progreso registrado)
- [x] template.yaml — AWS SAM con EventBridge rule (detail-type sward.recomendacion.RecomendacionGenerada)
- [x] GitHub Actions CI
