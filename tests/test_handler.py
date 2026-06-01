"""Tests unitarios para sward-lambda-alertas.

Trigger: EventBridge rule → evalúa riesgo académico
"""
from unittest.mock import MagicMock, patch


from handler import handle_event


def _make_event(detail) -> dict:
    return {
        "detail-type": "sward.recomendacion.RecomendacionGenerada",
        "detail": detail,
    }


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_riesgo_critico_crea_alerta(mock_consultar, mock_crear):
    mock_consultar.return_value = {"nivel_riesgo": "critico", "puntaje_promedio": 5.0}
    event = _make_event({"estudiante_id": "e-1", "curso_id": "c-1"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 1
    mock_crear.assert_called_once()
    args = mock_crear.call_args[0]
    assert args[0] == "e-1"
    assert args[1] == "c-1"
    assert args[2] == "critico"


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_riesgo_alto_crea_alerta(mock_consultar, mock_crear):
    mock_consultar.return_value = {"nivel_riesgo": "alto", "puntaje_promedio": 8.0}
    event = _make_event({"estudiante_id": "e-2", "curso_id": "c-2"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 1
    mock_crear.assert_called_once()


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_riesgo_bajo_no_crea_alerta(mock_consultar, mock_crear):
    mock_consultar.return_value = {"nivel_riesgo": "bajo", "puntaje_promedio": 15.0}
    event = _make_event({"estudiante_id": "e-3", "curso_id": "c-3"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 0
    mock_crear.assert_not_called()


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_detail_incompleto_se_omite(mock_consultar, mock_crear):
    event = _make_event({"estudiante_id": "e-4"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 0
    mock_consultar.assert_not_called()
    mock_crear.assert_not_called()


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_evento_sin_detail_retorna_cero(mock_consultar, mock_crear):
    result = handle_event({}, None)

    assert result["alertas_creadas"] == 0
    mock_consultar.assert_not_called()
    mock_crear.assert_not_called()


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_sin_progreso_no_crea_alerta(mock_consultar, mock_crear):
    mock_consultar.return_value = None
    event = _make_event({"estudiante_id": "e-5", "curso_id": "c-5"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 0
    mock_crear.assert_not_called()


# ---------------------------------------------------------------------------
# Idempotencia (deduplicación por event_id)
# ---------------------------------------------------------------------------


def _conn_con_rowcount(rowcount: int):
    """Construye un mock de conexión psycopg2 cuyo cursor reporta rowcount."""
    cur = MagicMock()
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_primer_evento_se_procesa():
    """rowcount=1 en el INSERT del dedup => ya_procesado=False => se procesa."""
    from lib.idempotency import ya_procesado

    conn, _ = _conn_con_rowcount(1)
    assert ya_procesado(conn, "evt-1") is False


def test_evento_repetido_se_omite():
    """rowcount=0 (ON CONFLICT DO NOTHING) => ya_procesado=True => se omite."""
    from lib.idempotency import ya_procesado

    conn, _ = _conn_con_rowcount(0)
    assert ya_procesado(conn, "evt-1") is True


def test_alerta_no_se_inserta_en_duplicado():
    """Mismo event_id repetido: la primera crea alerta, la segunda se omite."""
    import handler

    conn1, cur1 = _conn_con_rowcount(1)
    conn2, cur2 = _conn_con_rowcount(0)
    conns = iter([conn1, conn2])

    def _fake_get_connection(_url):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield next(conns)

        return _cm()

    with patch("lib.db_client.get_connection", side_effect=_fake_get_connection):
        creada_1 = handler._crear_alerta("e-1", "c-1", "critico", "msg", "evt-dup")
        creada_2 = handler._crear_alerta("e-1", "c-1", "critico", "msg", "evt-dup")

    assert creada_1 is True
    assert creada_2 is False
    # Primer evento: dedup (CREATE+INSERT) + INSERT de la alerta = 3 execs.
    assert cur1.execute.call_count == 3
    # Duplicado: solo el dedup (CREATE+INSERT), sin INSERT de alerta.
    assert cur2.execute.call_count == 2


@patch("handler._crear_alerta")
@patch("handler._consultar_riesgo")
def test_handler_no_cuenta_alerta_en_duplicado(mock_consultar, mock_crear):
    """Si _crear_alerta reporta duplicado (False), el handler no cuenta la alerta."""
    mock_consultar.return_value = {"nivel_riesgo": "critico", "puntaje_promedio": 5.0}
    mock_crear.return_value = False
    event = _make_event({"estudiante_id": "e-1", "curso_id": "c-1"})

    result = handle_event(event, None)

    assert result["alertas_creadas"] == 0


def test_event_id_ausente_genera_deterministico():
    """Sin event_id, se genera uno determinístico y no rompe el procesamiento."""
    from handler import _extraer_event_id

    detail = {"estudiante_id": "e-1", "curso_id": "c-1"}
    a = _extraer_event_id({"detail": detail}, detail)
    b = _extraer_event_id({"detail": detail}, detail)
    assert a == b
    assert a


def test_event_id_en_detail_tiene_prioridad():
    from handler import _extraer_event_id

    assert _extraer_event_id({"id": "env-1"}, {"event_id": "det-1"}) == "det-1"
    assert _extraer_event_id({"id": "env-1"}, {}) == "env-1"
