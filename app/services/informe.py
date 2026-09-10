"""Agregados del mes y del año de servicio, al estilo del informe S-1."""

from dataclasses import dataclass

from app.dominio import meses_del_anio
from app.services import nombramientos, registros

# clave, etiqueta, lleva columna de horas. El orden es el de presentación.
CATEGORIAS = (
    ("publicador", "Publicadores", False),
    ("precursor_auxiliar", "Precursores auxiliares", True),
    ("precursor_regular", "Precursores regulares", True),
    ("precursor_especial", "Precursores especiales", True),
    ("misionero_campo", "Misioneros en el campo", True),
)

# de mayor a menor prioridad: cada publicador cuenta en una sola categoría
PRECEDENCIA = (
    "misionero_campo",
    "precursor_especial",
    "precursor_regular",
    "precursor_auxiliar",
)


def categoria_de(tipos: set[str], precursor_auxiliar: bool) -> str:
    for clave in PRECEDENCIA:
        if clave == "precursor_auxiliar":
            if precursor_auxiliar:
                return clave
        elif clave in tipos:
            return clave
    return "publicador"


@dataclass
class FilaInforme:
    clave: str
    etiqueta: str
    informaron: int = 0
    cursos: int = 0
    horas: int | None = None


@dataclass
class InformeMensual:
    anio: int
    mes: int
    filas: list[FilaInforme]
    total_informaron: int
    total_cursos: int
    total_horas: int
    no_informaron: int
    promedio_horas_precursor_regular: int | None


def informe_mensual(sesion, anio: int, mes: int) -> InformeMensual:
    filas = {
        clave: FilaInforme(clave, etiqueta, horas=0 if lleva_horas else None)
        for clave, etiqueta, lleva_horas in CATEGORIAS
    }

    del_mes = registros.filas_del_mes(sesion, anio, mes)
    informaron = 0
    for publicador, registro, _habilitadas in del_mes:
        if registro is None or not registro.participo:
            continue
        informaron += 1
        tipos = nombramientos.tipos_en_mes(sesion, publicador.id, anio, mes)
        destino = filas[categoria_de(tipos, registro.precursor_auxiliar)]
        destino.informaron += 1
        destino.cursos += registro.cursos_biblicos or 0
        if destino.horas is not None:
            destino.horas += registro.horas or 0

    regulares = filas["precursor_regular"]
    promedio = (
        round((regulares.horas or 0) / regulares.informaron)
        if regulares.informaron
        else None
    )

    ordenadas = [filas[clave] for clave, _etiqueta, _horas in CATEGORIAS]
    return InformeMensual(
        anio=anio,
        mes=mes,
        filas=ordenadas,
        total_informaron=informaron,
        total_cursos=sum(fila.cursos for fila in ordenadas),
        total_horas=sum(fila.horas or 0 for fila in ordenadas),
        no_informaron=len(del_mes) - informaron,
        promedio_horas_precursor_regular=promedio,
    )


def informe_anual(sesion, anio_servicio: int) -> list[InformeMensual]:
    return [informe_mensual(sesion, anio, mes) for anio, mes in meses_del_anio(anio_servicio)]
