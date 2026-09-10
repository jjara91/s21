"""Vigencia de los privilegios y notas sugeridas por cambio de privilegio."""

from calendar import monthrange
from datetime import date

from sqlmodel import Session, select

from app.dominio import TIPOS_NOMBRAMIENTO, rango_anio_servicio
from app.models import Nombramiento

ETIQUETAS = {
    "anciano": "anciano",
    "siervo_ministerial": "siervo ministerial",
    "precursor_regular": "precursor regular",
    "precursor_especial": "precursor especial",
    "misionero_campo": "misionero que sirve en el campo",
}

FIN_ABIERTO = date(9999, 12, 31)


def se_cruza(desde: date, hasta: date | None, inicio: date, fin: date) -> bool:
    """¿El intervalo [desde, hasta] toca [inicio, fin] aunque sea un día?"""
    return desde <= fin and (hasta or FIN_ABIERTO) >= inicio


def crear(
    sesion: Session,
    publicador_id: int,
    tipo: str,
    desde: date,
    hasta: date | None = None,
) -> Nombramiento:
    if tipo not in TIPOS_NOMBRAMIENTO:
        raise ValueError(f"tipo de nombramiento desconocido: {tipo}")
    if hasta is not None and hasta < desde:
        raise ValueError("la fecha de término es anterior a la de inicio")
    nombramiento = Nombramiento(
        publicador_id=publicador_id, tipo=tipo, desde=desde, hasta=hasta
    )
    sesion.add(nombramiento)
    sesion.commit()
    sesion.refresh(nombramiento)
    return nombramiento


def cerrar(sesion: Session, nombramiento_id: int, hasta: date) -> Nombramiento:
    nombramiento = sesion.get(Nombramiento, nombramiento_id)
    if nombramiento is None:
        raise ValueError(f"no existe el nombramiento {nombramiento_id}")
    if hasta < nombramiento.desde:
        raise ValueError("la fecha de término es anterior a la de inicio")
    nombramiento.hasta = hasta
    sesion.add(nombramiento)
    sesion.commit()
    sesion.refresh(nombramiento)
    return nombramiento


def listar(sesion: Session, publicador_id: int) -> list[Nombramiento]:
    consulta = (
        select(Nombramiento)
        .where(Nombramiento.publicador_id == publicador_id)
        .order_by(Nombramiento.desde)
    )
    return list(sesion.exec(consulta).all())


def _tipos_en_rango(
    sesion: Session, publicador_id: int, inicio: date, fin: date
) -> set[str]:
    return {
        nombramiento.tipo
        for nombramiento in listar(sesion, publicador_id)
        if se_cruza(nombramiento.desde, nombramiento.hasta, inicio, fin)
    }


def tipos_en_anio(sesion: Session, publicador_id: int, anio_servicio: int) -> set[str]:
    """Privilegios que marcan la casilla de la tarjeta del año de servicio.

    Basta que el nombramiento haya estado vigente un solo mes del año.
    """
    inicio, fin = rango_anio_servicio(anio_servicio)
    return _tipos_en_rango(sesion, publicador_id, inicio, fin)


def tipos_en_mes(sesion: Session, publicador_id: int, anio: int, mes: int) -> set[str]:
    inicio = date(anio, mes, 1)
    fin = date(anio, mes, monthrange(anio, mes)[1])
    return _tipos_en_rango(sesion, publicador_id, inicio, fin)


def notas_sugeridas(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> dict[int, str]:
    """Texto propuesto para el mes en que un privilegio empieza o termina."""
    inicio, fin = rango_anio_servicio(anio_servicio)
    por_mes: dict[tuple[int, int], list[str]] = {}

    for nombramiento in listar(sesion, publicador_id):
        etiqueta = ETIQUETAS[nombramiento.tipo]
        if inicio <= nombramiento.desde <= fin:
            clave = (nombramiento.desde.year, nombramiento.desde.month)
            por_mes.setdefault(clave, []).append(f"nombrado {etiqueta}")
        if nombramiento.hasta is not None and inicio <= nombramiento.hasta <= fin:
            clave = (nombramiento.hasta.year, nombramiento.hasta.month)
            por_mes.setdefault(clave, []).append(f"deja de ser {etiqueta}")

    return {
        mes: " · ".join(textos) for (_anio, mes), textos in sorted(por_mes.items())
    }
