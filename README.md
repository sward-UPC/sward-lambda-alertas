# sward-lambda-alertas

AWS Lambda del sistema **SWARD** responsable de evaluar el riesgo académico de
un estudiante, crear **alertas explicables** y notificar al docente publicando
un evento de dominio. Es un componente *event-driven*: se dispara por eventos de
Amazon EventBridge, escribe en la base de datos de XAI y vuelve a publicar en
EventBridge.

## Qué hace

Cuando el microservicio de recomendación publica un `RecomendacionGeneradaEvent`,
esta Lambda:

1. Valida el evento (requiere `estudiante_id` y `curso_id` en el `detail`).
2. Consulta el progreso académico del estudiante (`nivel_riesgo`,
   `puntaje_promedio`) en `academic_progress` de **`trazabilidad_db`**.
3. Decide si el riesgo amerita alerta: solo niveles **`alto`** o **`critico`**.
4. Construye un **mensaje explicable** en lenguaje natural acorde al nivel y al
   puntaje (XAI).
5. Inserta la alerta en `academic_alerts` de **`xai_db`**, de forma
   **idempotente** (deduplicación atómica por `event_id` vía la tabla
   `processed_events` en la misma transacción).
6. Publica el evento de dominio **`AlertaCreada`** en EventBridge para que
   `lambda-notificaciones` resuelva el docente del curso y notifique.

Si no hay progreso registrado, o el riesgo es `bajo`/`medio`, o el evento es un
duplicado, la Lambda no crea alerta y retorna `{"alertas_creadas": 0}`.

## Trigger

Regla de **Amazon EventBridge** con patrón sobre el `detail-type`
`sward.recomendacion.RecomendacionGenerada` (ver `template.yaml`).

## Qué evalúa

| Nivel de riesgo (`academic_progress`) | Acción |
|---|---|
| `critico` | Crea alerta (mensaje: intervención inmediata) |
| `alto`    | Crea alerta (mensaje: seguimiento cercano) |
| `medio` / `bajo` | No hace nada |
| sin progreso registrado | No hace nada |

## Evento que publica: `AlertaCreada`

Tras crear una alerta nueva, publica en el bus indicado por
`EVENTBRIDGE_BUS_NAME`:

- **Source**: `sward-lambda-alertas`
- **DetailType**: `sward.alertas.AlertaCreada`
- **Detail**:

```json
{
  "event_type": "sward.alertas.AlertaCreada",
  "event_id": "<id del evento origen>",
  "estudiante_id": "...",
  "curso_id": "...",
  "nivel_riesgo": "alto|critico",
  "mensaje": "..."
}
```

La publicación es *best-effort*: si falla, la alerta ya creada no se revierte y
el error se registra en logs. Si `EVENTBRIDGE_BUS_NAME` no está configurado, se
omite la publicación con un *warning*.

## Variables de entorno y secretos

Cada base de datos se resuelve de una de dos formas (la URL directa tiene
prioridad):

**Opción A — URL directa**

| Variable | Descripción |
|---|---|
| `TRAZABILIDAD_DATABASE_URL` | URL de conexión a `trazabilidad_db` |
| `XAI_DATABASE_URL` | URL de conexión a `xai_db` |

**Opción B — componentes + AWS Secrets Manager**

| Variable | Descripción |
|---|---|
| `TRAZABILIDAD_DATABASE_HOST` / `_PORT` / `_NAME` | host, puerto (def. 5432), nombre de `trazabilidad_db` |
| `TRAZABILIDAD_DB_SECRET_ARN` | ARN del secreto con `username` / `password` |
| `XAI_DATABASE_HOST` / `_PORT` / `_NAME` | host, puerto, nombre de `xai_db` |
| `XAI_DB_SECRET_ARN` | ARN del secreto con `username` / `password` |

**Otras**

| Variable | Descripción |
|---|---|
| `EVENTBRIDGE_BUS_NAME` | Bus donde se publica `AlertaCreada` (sin él, no se publica) |
| `AWS_REGION` | Región para los clientes boto3 (def. `us-east-1`) |
| `LOG_LEVEL` | Nivel de log (def. `INFO`) |

> No hay credenciales en el código. Con la Opción B, la Lambda necesita permisos
> IAM `secretsmanager:GetSecretValue` (sobre los secrets) y `events:PutEvents`
> (sobre el bus). Ver `AUDIT.md` (H3) para el wiring de infraestructura.

Ejemplo local en `.env.example`.

## Stack

Python 3.11 · `psycopg2-binary` (acceso SQL directo, sin ORM) · `boto3` ·
empaquetado como **imagen de contenedor** (`Dockerfile`, base
`public.ecr.aws/lambda/python:3.11`).

## Build y despliegue (ECR)

El despliegue es por **imagen de contenedor**. CI/CD (`.github/workflows/`):

- `ci.yml` — corre lint + tests en push/PR a `main`.
- `build-push.yml` — al hacer push a la rama **`deploy`**, construye la imagen
  del `Dockerfile` y la publica al registro (GHCR → ECR) vía el workflow
  reutilizable de la organización (`service_type: lambda`).

Build manual de la imagen:

```bash
docker build -t sward-lambda-alertas .
```

La función Lambda (apuntando a la imagen en ECR) y su regla de EventBridge se
definen en el stack de infraestructura CDK del proyecto. El `template.yaml`
(AWS SAM) se conserva como referencia de la regla EventBridge y las variables.

## Testear

```bash
make test          # instala requirements-dev y corre pytest
make lint          # ruff check + ruff format --check
```

O directamente:

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check .
```

Cobertura de tests: riesgo crítico/alto/bajo, detail incompleto, evento sin
`detail`, sin progreso registrado, idempotencia (primer evento vs. duplicado) y
extracción/generación de `event_id`.

## Proyecto

**TP202610051** — Universidad Peruana de Ciencias Aplicadas (UPC)
Taller de Proyecto 1 / 2026
