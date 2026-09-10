from datetime import date, datetime

from sqlmodel import Field, SQLModel


class Grupo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre: str
    superintendente_id: int | None = Field(default=None, foreign_key="publicador.id")


class Publicador(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre_completo: str
    nombre_normalizado: str = Field(index=True)
    fecha_nacimiento: date | None = None
    fecha_bautismo: date | None = None
    sexo: str | None = None
    esperanza: str | None = None
    grupo_id: int | None = Field(default=None, foreign_key="grupo.id")
    fecha_baja: date | None = None
    motivo_baja: str | None = None

    @property
    def de_baja(self) -> bool:
        return self.fecha_baja is not None


class Nombramiento(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    publicador_id: int = Field(foreign_key="publicador.id", index=True)
    tipo: str
    desde: date
    hasta: date | None = None


class RegistroMensual(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    publicador_id: int = Field(foreign_key="publicador.id", index=True)
    anio: int
    mes: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


class Importacion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    archivo: str
    sha256: str = Field(index=True)
    fecha: datetime
    lote: str = Field(index=True)
    publicador_id: int | None = Field(default=None, foreign_key="publicador.id")
    anio_servicio: int | None = None
    accion: str
    # JSON con el estado anterior de lo que tocó esta importación, para deshacerla
    estado_previo: str | None = None
    deshecho: bool = False
