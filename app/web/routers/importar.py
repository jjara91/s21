from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.pdf.plantilla import TarjetaInvalida
from app.services import importacion, nombramientos
from app.services import publicadores as servicio_publicadores
from app.web.plantillas import plantillas

router = APIRouter(prefix="/importar")

# Como en la subida de la plantilla (app/web/routers/tarjetas.py): un S-21 real
# pesa unos 100 KB, pero aquí se suben varios archivos a la vez, así que el
# mismo cuidado de no cargar un archivo arbitrariamente grande en memoria
# aplica con más razón todavía.
LIMITE_SUBIDA = 20 * 1024 * 1024


@router.get("")
def pantalla(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request, "importar.html", {"historial": importacion.historial(sesion), "errores": []}
    )


@router.post("")
def subir(
    request: Request,
    archivos: list[UploadFile] = File(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    errores = []
    contenidos = []
    for archivo in archivos:
        nombre = archivo.filename or "sin-nombre.pdf"
        # se lee un byte de más que el límite para poder distinguir "cabe
        # justo" de "se pasó", sin necesidad de cargar un archivo
        # arbitrariamente grande en memoria.
        contenido = archivo.file.read(LIMITE_SUBIDA + 1)
        if len(contenido) > LIMITE_SUBIDA:
            errores.append(
                f"{nombre}: supera el límite de {LIMITE_SUBIDA // (1024 * 1024)} MB."
            )
            continue
        contenidos.append((nombre, contenido))

    for nombre, contenido in contenidos:
        try:
            importacion.analizar(sesion, nombre, contenido)
        except TarjetaInvalida as problema:
            errores.append(f"{nombre}: {problema}")
    if errores:
        return plantillas.TemplateResponse(
            request,
            "importar.html",
            {"historial": importacion.historial(sesion), "errores": errores},
            status_code=400,
        )

    lote = importacion.guardar_lote(contenidos)
    return RedirectResponse(f"/importar/{lote}", status_code=303)


@router.get("/{lote}")
def revisar(
    lote: str,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    propuestas = [
        importacion.analizar(sesion, nombre, contenido)
        for nombre, contenido in importacion.archivos_del_lote(lote)
    ]
    if not propuestas:
        return RedirectResponse("/importar", status_code=303)
    return plantillas.TemplateResponse(
        request,
        "importar_revision.html",
        {
            "lote": lote,
            "propuestas": propuestas,
            "publicadores": servicio_publicadores.listar(sesion),
            "etiquetas": nombramientos.ETIQUETAS,
        },
    )


@router.post("/{lote}")
async def aplicar(
    lote: str,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    formulario = await request.form()
    ahora = datetime.now()

    for indice, (nombre, contenido) in enumerate(importacion.archivos_del_lote(lote)):
        destino = formulario.get(f"destino_{indice}", "omitir")
        if destino == "omitir":
            continue

        propuesta = importacion.analizar(sesion, nombre, contenido)
        aceptados = [
            propuesto
            for propuesto in propuesta.nombramientos
            if formulario.get(f"nombramiento_{indice}_{propuesto.tipo}") is not None
        ]
        aceptados = [
            importacion.NombramientoPropuesto(
                propuesto.tipo,
                date.fromisoformat(
                    formulario.get(f"desde_{indice}_{propuesto.tipo}")
                    or propuesto.desde.isoformat()
                ),
            )
            for propuesto in aceptados
        ]

        decision = importacion.Decision(
            propuesta=propuesta,
            publicador_id=None if destino == "nuevo" else int(destino),
            aceptar_campos={
                diferencia.campo
                for diferencia in propuesta.diferencias
                if formulario.get(f"campo_{indice}_{diferencia.campo}") is not None
            },
            aceptar_nombramientos=aceptados,
            aceptar_meses={
                fila.mes
                for fila in propuesta.datos.meses
                if formulario.get(f"mes_{indice}_{fila.mes}") is not None
            },
        )
        importacion.aplicar(sesion, decision, lote=lote, ahora=ahora)

    importacion.borrar_lote(lote)
    return RedirectResponse("/importar", status_code=303)


@router.post("/{lote}/deshacer")
def deshacer(
    lote: str,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    importacion.deshacer(sesion, lote)
    return RedirectResponse("/importar", status_code=303)
