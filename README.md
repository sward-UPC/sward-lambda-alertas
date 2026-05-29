# sward-lambda-alertas

AWS Lambda del sistema **SWARD** que genera automáticamente alertas de riesgo académico.

## Trigger

**Amazon EventBridge** rule — se activa cuando el microservicio de recomendación publica un `RecomendacionGeneradaEvent`.

## Acción

1. Consulta el progreso académico del estudiante en `trazabilidad_db`.
2. Evalúa el nivel de riesgo académico (bajo dominio en conceptos clave).
3. Registra la alerta en `xai_db` para que el docente la visualice en su dashboard.

## Estructura

```
handler.py          # LambdaAlertasHandler.handle_event()
lib/
  db_client.py      # psycopg3 directo (sin ORM)
  logger.py         # Structured JSON logger para CloudWatch
requirements.txt
template.yaml       # AWS SAM template
Makefile            # make deploy | make test | make invoke
```

## Stack

- Python 3.11 · psycopg3 · boto3 · AWS SAM

## Despliegue

```bash
make deploy ENV=staging
```

## Tests

```bash
make test
```

## Proyecto

**TP202610051** — Universidad Peruana de Ciencias Aplicadas (UPC)  
Taller de Proyecto 1 / 2026
