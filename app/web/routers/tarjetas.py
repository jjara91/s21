from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.pdf.plantilla import TarjetaInvalida
from app.services import grupos, registros
from app.services import publicadores as servicio_publicadores
from app.services import tarjetas as servicio
from app.web.errores import anio_de_servicio
from app.web.plantillas import plantillas

router = APIRouter()

# Un S-21 real pesa unos 100 KB; 20 MB es un límite holgado que igual evita
# que un archivo arbitrariamente grande cargue todo en memoria (pypdf además
# duplica el contenido al parsearlo).
LIMITE_SUBIDA = 20 * 1024 * 1024


def _adjunto(nombre: str, contenido: bytes, tipo: str) -> Response:
    # Las cabeceras HTTP se codifican en latin-1, así que un nombre con
    # comilla tipográfica o raya larga —lo normal al pegar desde un editor de
    # texto— reventaría la respuesta. Se manda un nombre ASCII de respaldo y,
    # en filename*, el nombre real en UTF-8, que es el que usan los navegadores.
    respaldo = nombre.encode("ascii", "ignore").decode().replace('"', "") or "tarjeta.pdf"
    disposicion = f"attachment; filename=\"{respaldo}\"; filename*=utf-8''{quote(nombre)}"
    return Response(
        content=contenido,
        media_type=tipo,
        headers={"content-disposition": disposicion},
    )


@router.get("/plantilla")
def formulario_plantilla(
    request: Request, _usuario: str = Depends(requerir_sesion), error: str | None = None
):
    return plantillas.TemplateResponse(
        request,
        "plantilla_falta.html",
        {"hay_plantilla": servicio.hay_plantilla(), "error": error},
    )


@router.post("/plantilla")
def subir_plantilla(
    request: Request,
    archivo: UploadFile = File(...),
    _usuario: str = Depends(requerir_sesion),
):
    # Se lee un byte de más que el límite para poder distinguir "cabe justo"
    # de "se pasó", sin necesidad de cargar un archivo arbitrariamente grande.
    contenido = archivo.file.read(LIMITE_SUBIDA + 1)
    if len(contenido) > LIMITE_SUBIDA:
        return plantillas.TemplateResponse(
            request,
            "plantilla_falta.html",
            {
                "hay_plantilla": False,
                "error": (
                    "El archivo supera el límite de "
                    f"{LIMITE_SUBIDA // (1024 * 1024)} MB."
                ),
            },
            status_code=400,
        )
    try:
        servicio.guardar_plantilla(contenido)
    except TarjetaInvalida as problema:
        return plantillas.TemplateResponse(
            request,
            "plantilla_falta.html",
            {"hay_plantilla": False, "error": str(problema)},
            status_code=400,
        )
    return RedirectResponse("/plantilla", status_code=303)


# Esta ruta va ANTES que la de la vista: Starlette resuelve por orden de
# declaración y `{anio_servicio}` casa cualquier cosa sin barra, así que la vista
# capturaría "2026.pdf" y fallaría al convertirlo a int.
@router.get("/publicadores/{publicador_id}/tarjeta/{anio_servicio}.pdf")
def descargar_tarjeta(
    publicador_id: int,
    anio_servicio: int,
    aplanado: bool = False,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    anio_servicio = anio_de_servicio(anio_servicio)
    try:
        nombre, contenido = servicio.pdf_de(
            sesion, publicador_id, anio_servicio, aplanado=aplanado
        )
    except servicio.PlantillaAusente:
        return RedirectResponse("/plantilla", status_code=303)
    return _adjunto(nombre, contenido, "application/pdf")


@router.get("/publicadores/{publicador_id}/tarjeta/{anio_servicio}")
def ver_tarjeta(
    publicador_id: int,
    anio_servicio: int,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    anio_servicio = anio_de_servicio(anio_servicio)
    registros.aplicar_notas_sugeridas(sesion, publicador_id, anio_servicio)
    return plantillas.TemplateResponse(
        request,
        "tarjeta.html",
        {
            "publicador": servicio_publicadores.obtener(sesion, publicador_id),
            "tarjeta": registros.tarjeta(sesion, publicador_id, anio_servicio),
            "anio_servicio": anio_servicio,
        },
    )


@router.get("/exportar")
def formulario_exportar(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    return plantillas.TemplateResponse(
        request,
        "exportar.html",
        {
            "anio_servicio": anio_servicio_de(hoy.year, hoy.month),
            "grupos": grupos.listar(sesion),
        },
    )


@router.post("/exportar")
def exportar_lote(
    anio_servicio: int = Form(...),
    formato: str = Form("zip"),
    grupo_id: int | None = Form(None),
    aplanado: bool = Form(False),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    anio_servicio = anio_de_servicio(anio_servicio)
    ids = [
        publicador.id
        for publicador in servicio_publicadores.listar(sesion, grupo_id=grupo_id)
    ]
    try:
        if formato == "combinado":
            contenido = servicio.pdf_combinado(
                sesion, ids, anio_servicio, aplanado=aplanado
            )
            return _adjunto(
                f"tarjetas {anio_servicio}.pdf", contenido, "application/pdf"
            )
        contenido = servicio.zip_de(sesion, ids, anio_servicio, aplanado=aplanado)
    except servicio.PlantillaAusente:
        return RedirectResponse("/plantilla", status_code=303)
    return _adjunto(f"tarjetas {anio_servicio}.zip", contenido, "application/zip")
