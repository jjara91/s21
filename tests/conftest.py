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
