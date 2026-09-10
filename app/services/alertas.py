"""Detección de publicadores irregulares e inactivos."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.models import Publicador, RegistroMensual
from app.services import publicadores

MESES_VENTANA = 6


def ventana(hoy: date) -> list[tuple[int, int]]:
    """Los 6 meses calendario completos anteriores al mes en curso, en orden."""
    meses = []
    anio, mes = hoy.year, hoy.month
    for _ in range(MESES_VENTANA):
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
        meses.append((anio, mes))
    return list(reversed(meses))


@dataclass
class Alerta:
    publicador: Publicador
    estado: str
    meses_sin_informar: list[tuple[int, int]]


def calcular(sesion: Session, hoy: date) -> list[Alerta]:
    periodos = ventana(hoy)
    resultado: list[Alerta] = []

    for publicador in publicadores.listar(sesion):
        consulta = select(RegistroMensual).where(
            RegistroMensual.publicador_id == publicador.id,
            RegistroMensual.participo == True,  # noqa: E712 - SQLModel necesita ==
            # Acotado a la ventana. Sin esto la consulta arrastra el historial
            # completo del publicador para mirar solo seis meses, y ese
            # historial crece cada año que la aplicación esté en uso.
            or_(
                *(
                    and_(RegistroMensual.anio == anio, RegistroMensual.mes == mes)
                    for anio, mes in periodos
                )
            ),
        )
        informados = {
            (registro.anio, registro.mes) for registro in sesion.exec(consulta).all()
        }
        faltantes = [periodo for periodo in periodos if periodo not in informados]

        if not faltantes:
            continue
        estado = "inactivo" if len(faltantes) == MESES_VENTANA else "irregular"
        resultado.append(Alerta(publicador, estado, faltantes))

    # los inactivos primero, después por nombre
    return sorted(
        resultado,
        key=lambda alerta: (
            alerta.estado != "inactivo",
            alerta.publicador.nombre_normalizado,
        ),
    )
