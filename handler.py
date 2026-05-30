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
    _crear_alerta(estudiante_id, curso_id, nivel_riesgo, mensaje)

    logger.info(
        "Alerta de riesgo creada | estudiante=%s | curso=%s | nivel=%s",
        estudiante_id,
        curso_id,
        nivel_riesgo,
    )
    return {"alertas_creadas": 1}


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
    estudiante_id: str, curso_id: str, nivel_riesgo: str, mensaje: str
) -> None:
    """Inserta una alerta en academic_alerts dentro de xai_db."""
    from lib.db_client import get_connection

    with get_connection(XAI_DATABASE_URL) as conn:
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
