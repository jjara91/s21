"""Engine, migraciones y sesiones.

El esquema vive en `migrations/*.sql` y no se genera desde los modelos: así el
archivo SQL es la fuente de verdad y las migraciones futuras son explícitas.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import cargar_config

DIRECTORIO_MIGRACIONES = Path(__file__).resolve().parent.parent / "migrations"


def crear_engine(ruta: Path) -> Engine:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{ruta}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(conexion, _registro):  # pragma: no cover - callback
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _version_actual(conexion) -> int:
    conexion.execute(
        text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    )
    fila = conexion.execute(text("SELECT version FROM schema_version")).first()
    if fila is None:
        conexion.execute(text("INSERT INTO schema_version (version) VALUES (0)"))
        return 0
    return int(fila[0])


def aplicar_migraciones(engine: Engine) -> int:
    """Aplica los scripts pendientes en orden y devuelve la versión resultante."""
    scripts = sorted(DIRECTORIO_MIGRACIONES.glob("[0-9][0-9][0-9]_*.sql"))
    with engine.begin() as conexion:
        version = _version_actual(conexion)
        for script in scripts:
            numero = int(script.name.split("_", 1)[0])
            if numero <= version:
                continue
            for sentencia in script.read_text(encoding="utf-8").split(";"):
                if sentencia.strip():
                    conexion.execute(text(sentencia))
            version = numero
        conexion.execute(text("UPDATE schema_version SET version = :v"), {"v": version})
    return version


@lru_cache(maxsize=1)
def motor() -> Engine:
    engine = crear_engine(cargar_config().ruta_db)
    aplicar_migraciones(engine)
    return engine


@contextmanager
def sesion(engine: Engine | None = None) -> Iterator[Session]:
    with Session(engine or motor()) as abierta:
        yield abierta


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI."""
    with Session(motor()) as abierta:
        yield abierta
