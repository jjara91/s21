import os
from dataclasses import dataclass
from pathlib import Path


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


def cargar_config() -> Config:
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        auth_user=os.environ.get("AUTH_USER", "admin"),
        auth_pass=os.environ.get("AUTH_PASS", "cambiar"),
        secret_key=os.environ.get("SECRET_KEY", "clave-de-desarrollo-no-usar-en-serio"),
        data_dir=data_dir,
    )
