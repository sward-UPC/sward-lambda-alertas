from unittest.mock import patch

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
