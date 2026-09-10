from pathlib import Path

import pytest

from tests.fixtures.sintetico import crear_s21_sintetico


@pytest.fixture(scope="session")
def plantilla_sintetica(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("pdf") / "sintetico.pdf"
    return crear_s21_sintetico(destino)


@pytest.fixture(scope="session")
def plantilla_real() -> Path:
    ruta = Path("data/plantilla_s21.pdf")
    if not ruta.exists():
        pytest.skip("no hay plantilla real en data/; se corre solo donde exista")
    return ruta


from collections.abc import Iterator

from sqlmodel import Session

from app import db


@pytest.fixture
def engine(tmp_path):
    motor = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(motor)
    return motor


@pytest.fixture
def sesion(engine) -> Iterator[Session]:
    with Session(engine) as abierta:
        yield abierta


from fastapi.testclient import TestClient


@pytest.fixture
def cliente_anonimo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_USER", "prueba")
    monkeypatch.setenv("AUTH_PASS", "secreta")
    monkeypatch.setenv("SECRET_KEY", "clave-de-prueba")

    from app import db

    # el engine es perezoso y cacheado: se limpia para que tome el DATA_DIR nuevo
    db.motor.cache_clear()

    from app.main import app

    with TestClient(app) as abierto:
        yield abierto

    db.motor.cache_clear()


@pytest.fixture
def cliente(cliente_anonimo):
    cliente_anonimo.post("/entrar", data={"usuario": "prueba", "clave": "secreta"})
    return cliente_anonimo
