import pytest
from fastapi.testclient import TestClient

from app import config, db


def test_secret_key_se_genera_y_se_reutiliza(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)

    primera = config.cargar_config().secret_key
    segunda = config.cargar_config().secret_key

    assert primera == segunda
    assert (tmp_path / "secret_key").exists()


def test_secret_key_de_ejemplo_se_reemplaza_por_una_generada(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", config.SECRET_KEY_EJEMPLO)

    generada = config.cargar_config().secret_key

    assert generada != config.SECRET_KEY_EJEMPLO


def test_verificar_arranque_falla_si_falta_auth_pass(monkeypatch):
    monkeypatch.delenv("AUTH_PASS", raising=False)

    with pytest.raises(config.ConfiguracionInvalida):
        config.verificar_arranque()


def test_verificar_arranque_falla_con_el_valor_de_ejemplo(monkeypatch):
    monkeypatch.setenv("AUTH_PASS", config.AUTH_PASS_EJEMPLO)

    with pytest.raises(config.ConfiguracionInvalida) as info:
        config.verificar_arranque()

    assert "AUTH_PASS" in info.value.mensaje


def test_verificar_arranque_pasa_con_una_clave_propia(monkeypatch):
    monkeypatch.setenv("AUTH_PASS", "una-clave-real")

    config.verificar_arranque()  # no debe lanzar


def test_la_aplicacion_no_arranca_con_auth_pass_de_ejemplo(tmp_path, monkeypatch):
    """El caso real: `with TestClient(app)` dispara el ciclo de vida, y con
    AUTH_PASS igual al valor de .env.example debe negarse a arrancar."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_PASS", config.AUTH_PASS_EJEMPLO)

    db.motor.cache_clear()
    from app.main import app  # ya importado en la sesión de tests; se reusa el mismo app

    with pytest.raises(config.ConfiguracionInvalida):
        with TestClient(app):
            pass

    db.motor.cache_clear()
