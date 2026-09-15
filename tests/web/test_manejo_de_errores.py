"""Nunca una traza al navegador: los manejadores globales de app.main."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import db
from app.services import publicadores as servicio_publicadores


def test_operational_error_da_una_pagina_en_espanol_no_una_traza(cliente, monkeypatch):
    def _reventar(*_args, **_kwargs):
        raise OperationalError("select 1", {}, Exception("database is locked"))

    monkeypatch.setattr(servicio_publicadores, "listar", _reventar)

    respuesta = cliente.get("/publicadores")

    assert respuesta.status_code == 503
    assert "ocupada" in respuesta.text.lower()
    assert "Traceback" not in respuesta.text
    assert "OperationalError" not in respuesta.text


@pytest.fixture
def cliente_sin_relanzar_errores(tmp_path, monkeypatch):
    """Como la fixture `cliente` de conftest, pero sin relanzar las
    excepciones de servidor. Starlette relanza deliberadamente cualquier
    excepción de tipo `Exception` después de que su manejador global ya
    generó la respuesta -es lo que le permite a un servidor real registrar el
    error y a la vez servir la página-, así que el TestClient por defecto
    (`raise_server_exceptions=True`) no deja ver esa respuesta y hay que
    pedir explícitamente lo contrario para probarla.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_USER", "prueba")
    monkeypatch.setenv("AUTH_PASS", "secreta")

    db.motor.cache_clear()
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as abierto:
        respuesta = abierto.post(
            "/entrar", data={"usuario": "prueba", "clave": "secreta"}, follow_redirects=False
        )
        assert respuesta.status_code == 303
        yield abierto

    db.motor.cache_clear()


def test_un_error_no_previsto_da_una_pagina_generica_no_una_traza(
    cliente_sin_relanzar_errores, monkeypatch
):
    def _reventar(*_args, **_kwargs):
        raise RuntimeError("bug interno inesperado")

    monkeypatch.setattr(servicio_publicadores, "listar", _reventar)

    respuesta = cliente_sin_relanzar_errores.get("/publicadores")

    assert respuesta.status_code == 500
    assert "error inesperado" in respuesta.text.lower()
    assert "Traceback" not in respuesta.text
    assert "RuntimeError" not in respuesta.text
    assert "bug interno inesperado" not in respuesta.text


def test_un_parametro_mal_formado_da_una_pagina_en_espanol_no_json(cliente):
    """FastAPI atiende RequestValidationError antes que los manejadores de
    app.main: sin uno propio, cualquier URL con un parámetro mal escrito
    devuelve el JSON de validación en inglés en vez de la página de error."""
    respuesta = cliente.get("/grilla", params={"anio": "abc", "mes": 1})

    assert respuesta.status_code == 400
    assert "Datos incorrectos" in respuesta.text
    assert "Traceback" not in respuesta.text
    texto = respuesta.text.lower()
    assert "value is not a valid integer" not in texto
    assert "unable to parse string" not in texto
