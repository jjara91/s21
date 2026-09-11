"""Objetos que cruzan la frontera entre la capa PDF y la capa de servicios.

No dependen de SQLModel ni de FastAPI a propósito: `app/pdf/` los usa sin tocar
la base de datos.
"""

from dataclasses import dataclass, field
from datetime import date

from app.pdf.campos import MESES_ORDENADOS

TIPOS_NOMBRAMIENTO = (
    "anciano",
    "siervo_ministerial",
    "precursor_regular",
    "precursor_especial",
    "misionero_campo",
)

TIPOS_CON_HORAS = ("precursor_regular", "precursor_especial", "misionero_campo")

NOMBRE_MES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


def anio_servicio_de(anio: int, mes: int) -> int:
    """El año de servicio N va de septiembre de N-1 a agosto de N."""
    return anio + 1 if mes >= 9 else anio


def rango_anio_servicio(anio_servicio: int) -> tuple[date, date]:
    return date(anio_servicio - 1, 9, 1), date(anio_servicio, 8, 31)


def meses_del_anio(anio_servicio: int) -> list[tuple[int, int]]:
    """Los 12 pares (año calendario, mes) del año de servicio, de sep a ago."""
    return [
        (anio_servicio - 1 if mes >= 9 else anio_servicio, mes) for mes in MESES_ORDENADOS
    ]


@dataclass
class FilaMes:
    mes: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


@dataclass
class DatosTarjeta:
    nombre: str
    anio_servicio: int | None = None
    fecha_nacimiento: date | None = None
    fecha_bautismo: date | None = None
    # texto original cuando la fecha (o el año de servicio) del PDF no se
    # pudo interpretar, para poder mostrárselo al usuario en vez de un
    # simple "sin año"
    fecha_nacimiento_cruda: str | None = None
    fecha_bautismo_cruda: str | None = None
    anio_servicio_crudo: str | None = None
    sexo: str | None = None
    esperanza: str | None = None
    nombramientos: set[str] = field(default_factory=set)
    meses: list[FilaMes] = field(default_factory=list)

    @classmethod
    def vacia(cls, nombre: str, anio_servicio: int | None = None) -> "DatosTarjeta":
        return cls(
            nombre=nombre,
            anio_servicio=anio_servicio,
            meses=[FilaMes(mes=mes) for mes in MESES_ORDENADOS],
        )

    def mes(self, numero: int) -> FilaMes:
        for fila in self.meses:
            if fila.mes == numero:
                return fila
        raise KeyError(f"la tarjeta no tiene el mes {numero}")

    def total_horas(self) -> int | None:
        horas = [fila.horas for fila in self.meses if fila.horas is not None]
        return sum(horas) if horas else None
