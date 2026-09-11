import os
import secrets
from dataclasses import dataclass
from pathlib import Path

# Los mismos valores que trae `.env.example`. Un despliegue que copia ese
# archivo tal cual y no lo edita corre con una clave de sesión publicada en el
# repositorio: ya pasó una vez.
AUTH_PASS_EJEMPLO = "cambia-esta-clave"
SECRET_KEY_EJEMPLO = "cadena-larga-y-aleatoria"


class ConfiguracionInvalida(Exception):
    """La aplicación no puede arrancar con la configuración actual."""

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


@dataclass(frozen=True)
class Config:
    auth_user: str
    auth_pass: str
    secret_key: str
    data_dir: Path

    @property
    def ruta_db(self) -> Path:
        return self.data_dir / "s21.db"

    @property
    def ruta_plantilla(self) -> Path:
        return self.data_dir / "plantilla_s21.pdf"


def _secret_key_persistida(data_dir: Path) -> str:
    """Genera una SECRET_KEY aleatoria la primera vez y la reutiliza después.

    Vive en `data/secret_key` en vez de en el entorno para que un despliegue
    que no fija SECRET_KEY (o deja el valor de ejemplo) no firme las sesiones
    con una clave publicada, sin que nadie tenga que generar nada a mano.

    Es la clave que firma las sesiones de un sistema con datos personales de
    la congregación, así que el archivo se crea con permisos `0600` (solo
    lectura/escritura del dueño) en vez de heredar el umask por defecto, que
    normalmente lo deja legible por cualquiera. Si el archivo ya existiera
    con permisos más abiertos —por ejemplo, escrito antes de este cambio—
    se corrigen también al leerlo.
    """
    ruta = data_dir / "secret_key"
    if ruta.exists():
        ruta.chmod(0o600)
        return ruta.read_text(encoding="utf-8").strip()
    clave = secrets.token_hex(32)
    ruta.write_text(clave, encoding="utf-8")
    ruta.chmod(0o600)
    return clave


def cargar_config() -> Config:
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key or secret_key == SECRET_KEY_EJEMPLO:
        secret_key = _secret_key_persistida(data_dir)

    return Config(
        auth_user=os.environ.get("AUTH_USER", "admin"),
        auth_pass=os.environ.get("AUTH_PASS", "cambiar"),
        secret_key=secret_key,
        data_dir=data_dir,
    )


def verificar_arranque() -> None:
    """Se llama solo al arrancar la aplicación (ver `app.main`), nunca desde
    `cargar_config`: muchos servicios llaman a `cargar_config` sin que les
    importe la autenticación (los tests, sobre todo), y no deben empezar a
    fallar por eso. Esto es, en cambio, la puerta de entrada real.
    """
    valor = os.environ.get("AUTH_PASS")
    if not valor or valor == AUTH_PASS_EJEMPLO:
        raise ConfiguracionInvalida(
            "AUTH_PASS no está definido o sigue con el valor de ejemplo de "
            ".env.example. Edita tu archivo .env y pon una contraseña propia "
            "en AUTH_PASS antes de arrancar la aplicación."
        )
