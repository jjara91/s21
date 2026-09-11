import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from app.auth import requerir_sesion
from app.config import cargar_config
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.services import alertas, informe
from app.web.errores import anio_valido, mes_valido
from app.web.plantillas import plantillas

router = APIRouter()


@router.get("/informe")
def mensual(
    request: Request,
    anio: int | None = None,
    mes: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio = anio_valido(anio) if anio is not None else hoy.year
    mes = mes_valido(mes) if mes is not None else hoy.month
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
        anio_valido(anio_servicio)
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


def _copia_consistente(origen: Path) -> bytes:
    """Copia la base respetando el bloqueo de SQLite.

    Un read_bytes() del archivo vivo no toma ningún bloqueo y puede devolver
    páginas a medio escribir: la base no está en modo WAL, así que una
    escritura en curso modifica el archivo principal en el sitio. El respaldo
    resultante no abriría, o abriría con datos incoherentes, y eso no se
    descubre hasta el día que hace falta restaurarlo.

    Es el único punto del proyecto que usa sqlite3 directamente en vez de
    SQLAlchemy: aquí no hay una consulta que hacer, sino copiar el archivo de
    forma segura, y `Connection.backup` es la API que lo garantiza.
    """
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / "respaldo.db"
        origen_con = sqlite3.connect(origen)
        destino_con = sqlite3.connect(destino)
        try:
            origen_con.backup(destino_con)
        finally:
            destino_con.close()
            origen_con.close()
        return destino.read_bytes()


@router.get("/respaldo")
def respaldo(_usuario: str = Depends(requerir_sesion)):
    ruta = cargar_config().ruta_db
    return Response(
        content=_copia_consistente(ruta),
        media_type="application/octet-stream",
        headers={"content-disposition": 'attachment; filename="s21.db"'},
    )
