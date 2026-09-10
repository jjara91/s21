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

    @event.listens_for(engine, "connect")
    def _sin_autocommit_de_pysqlite(conexion, _registro):  # pragma: no cover - callback
        # pysqlite (el sqlite3 de la stdlib) solo abre transacción implícita
        # antes de una sentencia DML: un CREATE TABLE emitido sin transacción
        # abierta queda confirmado en autocommit aunque el resto del script
        # falle después. Con isolation_level=None el control del BEGIN pasa a
        # SQLAlchemy y el DDL entra en la misma transacción que el resto.
        conexion.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_explicito(conexion):  # pragma: no cover - callback
        conexion.exec_driver_sql("BEGIN")

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
            # Troceado simple por ";": solo admite sentencias que no tengan un
            # punto y coma dentro de literales, triggers o bloques BEGIN...END.
            # Una migración futura con eso necesitará un parser real, no este split.
            for sentencia in script.read_text(encoding="utf-8").split(";"):
                if sentencia.strip():
                    conexion.execute(text(sentencia))
            version = numero
        conexion.execute(text("UPDATE schema_version SET version = :v"), {"v": version})
    return version


@lru_cache(maxsize=1)
def motor() -> Engine:
    """Engine global perezoso, cacheado a propósito para reusar una sola conexión.

    La caché fija la ruta de la base (`cargar_config().ruta_db`) en la primera
    llamada y no la vuelve a leer. Quien cambie la configuración después de que
    `motor()` ya se haya invocado una vez en el proceso —los tests, sobre todo,
    que suelen variar `DATA_DIR` de un caso a otro— debe llamar antes a
    `motor.cache_clear()`, o seguirá recibiendo el engine (y la base) de la
    primera llamada.
    """
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
