import json
import os
import uuid
from datetime import datetime, timezone

from lib.logger import setup_logger

logger = setup_logger(__name__)

TRAZABILIDAD_DATABASE_URL = os.environ.get("TRAZABILIDAD_DATABASE_URL", "")
XAI_DATABASE_URL = os.environ.get("XAI_DATABASE_URL", "")

NIVELES_RIESGO_ALERTA = {"alto", "critico"}


def handle_event(event: dict, context) -> dict:
    """Trigger: EventBridge — procesa RecomendacionGeneradaEvent y genera alertas de riesgo."""
    detail = event.get("detail")
    if not detail:
        logger.warning("Evento sin detail, se omite | event=%s", event)
        return {"alertas_creadas": 0}

    estudiante_id = detail.get("estudiante_id")
    curso_id = detail.get("curso_id")

    if not estudiante_id or not curso_id:
        logger.warning("Detail incompleto, se omite | detail=%s", detail)
        return {"alertas_creadas": 0}

    event_id = _extraer_event_id(event, detail)

    riesgo = _consultar_riesgo(estudiante_id, curso_id)
    if riesgo is None:
        logger.info(
            "Sin progreso académico registrado | estudiante=%s | curso=%s",
            estudiante_id,
            curso_id,
        )
        return {"alertas_creadas": 0}

    nivel_riesgo = (riesgo.get("nivel_riesgo") or "").lower()
    if nivel_riesgo not in NIVELES_RIESGO_ALERTA:
        logger.info(
            "Riesgo no requiere alerta | estudiante=%s | curso=%s | nivel=%s",
            estudiante_id,
            curso_id,
            nivel_riesgo,
        )
        return {"alertas_creadas": 0}

    mensaje = _construir_mensaje(nivel_riesgo, riesgo.get("puntaje_promedio"))
    creada = _crear_alerta(estudiante_id, curso_id, nivel_riesgo, mensaje, event_id)

    if not creada:
        logger.info(
            "Evento duplicado, omitido | event_id=%s | estudiante=%s | curso=%s",
            event_id,
            estudiante_id,
            curso_id,
        )
        return {"alertas_creadas": 0}

    logger.info(
        "Alerta de riesgo creada | event_id=%s | estudiante=%s | curso=%s | nivel=%s",
        event_id,
        estudiante_id,
        curso_id,
        nivel_riesgo,
    )
    return {"alertas_creadas": 1}


def _extraer_event_id(event: dict, detail: dict) -> str:
    """Obtiene el event_id del DomainEvent/EventEnvelope de sward-shared.

    Busca primero en el detail (DomainEvent dentro de EventBridge) y luego en
    el sobre del evento. Si no viaja en ningún sitio, genera uno determinístico
    a partir del contenido para no romper el procesamiento.
    """
    event_id = detail.get("event_id") or event.get("event_id") or event.get("id")
    if event_id:
        return str(event_id)

    logger.warning(
        "Evento sin event_id, se genera uno determinístico | detail=%s", detail
    )
    base = json.dumps(detail, sort_keys=True, default=str)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def _consultar_riesgo(estudiante_id: str, curso_id: str) -> dict | None:
    """Lee nivel_riesgo y puntaje_promedio desde academic_progress en trazabilidad_db."""
    from lib.db_client import get_connection

    with get_connection(TRAZABILIDAD_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nivel_riesgo, puntaje_promedio
                FROM academic_progress
                WHERE estudiante_id = %s AND curso_id = %s
                """,
                (estudiante_id, curso_id),
            )
            row = cur.fetchone()

    if row is None:
        return None
    return {"nivel_riesgo": row[0], "puntaje_promedio": row[1]}


def _crear_alerta(
    estudiante_id: str,
    curso_id: str,
    nivel_riesgo: str,
    mensaje: str,
    event_id: str,
) -> bool:
    """Inserta una alerta en academic_alerts dentro de xai_db, con dedup atómico.

    processed_events vive en xai_db (misma conexión que la alerta), por lo que
    el dedup y el INSERT de la alerta son atómicos en una sola transacción.

    Returns:
        True  -> la alerta se creó (event_id nuevo).
        False -> evento duplicado; no se creó ninguna alerta.
    """
    from lib.db_client import get_connection
    from lib.idempotency import ya_procesado

    with get_connection(XAI_DATABASE_URL) as conn:
        if ya_procesado(conn, event_id):
            conn.commit()
            return False

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO academic_alerts
                    (id, estudiante_id, curso_id, nivel_riesgo, mensaje, creada_en)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    estudiante_id,
                    curso_id,
                    nivel_riesgo,
                    mensaje,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()
    return True


def _construir_mensaje(nivel_riesgo: str, puntaje_promedio) -> str:
    """Explica el riesgo académico en lenguaje natural."""
    if puntaje_promedio is not None:
        detalle_puntaje = f" Su puntaje promedio actual es {puntaje_promedio}."
    else:
        detalle_puntaje = ""

    if nivel_riesgo == "critico":
        return (
            "El estudiante presenta un nivel de riesgo académico crítico y requiere "
            "intervención inmediata del docente." + detalle_puntaje
        )
    return (
        "El estudiante presenta un nivel de riesgo académico alto; se recomienda "
        "dar seguimiento cercano a su desempeño." + detalle_puntaje
    )


lambda_handler = handle_event
