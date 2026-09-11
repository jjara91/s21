from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.services import alertas
from app.services import tarjetas as servicio_tarjetas
from app.web.plantillas import plantillas

router = APIRouter()


@router.get("/")
def inicio(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    return plantillas.TemplateResponse(
        request,
        "inicio.html",
        {
            "anio_servicio": anio_servicio_de(hoy.year, hoy.month),
            "hoy": hoy,
            "alertas": alertas.calcular(sesion, hoy),
            "hay_plantilla": servicio_tarjetas.hay_plantilla(),
        },
    )
