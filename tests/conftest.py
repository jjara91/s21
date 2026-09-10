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
