from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from app.auth import requerir_sesion
from app.config import cargar_config
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.services import alertas, informe
from app.web.errores import DatosInvalidos, anio_de_servicio
from app.web.plantillas import plantillas

router = APIRouter()


def _mes_valido(mes: int) -> int:
    # `mes | mes_nombre` en la plantilla busca la clave en un diccionario de
    # 1 a 12: sin este control, un mes fuera de rango en la URL no cae en un
    # error de negocio legible sino en un KeyError sin capturar.
    if not 1 <= mes <= 12:
        raise DatosInvalidos(f"El mes {mes} no es válido. Debe estar entre 1 y 12.")
    return mes


@router.get("/informe")
def mensual(
    request: Request,
    anio: int | None = None,
    mes: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio = anio_de_servicio(anio) if anio is not None else hoy.year
    mes = _mes_valido(mes) if mes is not None else hoy.month
    return plantillas.TemplateResponse(
        request,
        "informe.html",
        {"informe": informe.informe_mensual(sesion, anio, mes), "anio": anio, "mes": mes},
    )


@router.get("/informe/anual")
def anual(
    request: Request,
    anio_servicio: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio_servicio = (
        anio_de_servicio(anio_servicio)
        if anio_servicio is not None
        else anio_servicio_de(hoy.year, hoy.month)
    )
    return plantillas.TemplateResponse(
        request,
        "informe.html",
        {
            "anual": informe.informe_anual(sesion, anio_servicio),
            "anio_servicio": anio_servicio,
        },
    )


@router.get("/alertas")
def ver_alertas(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request,
        "alertas.html",
        {"alertas": alertas.calcular(sesion, date.today())},
    )


@router.get("/respaldo")
def respaldo(_usuario: str = Depends(requerir_sesion)):
    ruta = cargar_config().ruta_db
    return Response(
        content=ruta.read_bytes(),
        media_type="application/octet-stream",
        headers={"content-disposition": 'attachment; filename="s21.db"'},
    )
