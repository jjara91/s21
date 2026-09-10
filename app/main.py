import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from app.auth import SinSesion, redirigir_al_login
from app.config import cargar_config
from app.db import motor
from app.services.grupos import GrupoNoEncontrado
from app.services.publicadores import PublicadorNoEncontrado
from app.web.errores import DatosInvalidos
from app.web.plantillas import DIRECTORIO, plantillas
from app.web.routers import grilla, grupos, inicio, publicadores, sesion


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    motor()  # aplica las migraciones pendientes al arrancar
    yield


app = FastAPI(title="Registros de predicación", lifespan=ciclo_de_vida)
# 12 horas en vez de los 14 días que trae Starlette por defecto: esto guarda
# datos personales de la congregación y puede correr en un equipo compartido.
app.add_middleware(
    SessionMiddleware,
    secret_key=cargar_config().secret_key,
    max_age=12 * 60 * 60,
)
app.mount("/static", StaticFiles(directory=str(DIRECTORIO.parent / "static")), name="static")


@app.exception_handler(SinSesion)
def sin_sesion(_request: Request, _error: SinSesion):
    return redirigir_al_login()


def _pagina_error(request: Request, titulo: str, mensaje: str, codigo: int):
    return plantillas.TemplateResponse(
        request, "error.html", {"titulo": titulo, "mensaje": mensaje}, status_code=codigo
    )


@app.exception_handler(DatosInvalidos)
def datos_invalidos(request: Request, error: DatosInvalidos):
    return _pagina_error(request, "Datos incorrectos", error.mensaje, 400)


@app.exception_handler(PublicadorNoEncontrado)
def publicador_no_encontrado(request: Request, error: PublicadorNoEncontrado):
    return _pagina_error(
        request, "No encontrado", "Ese publicador ya no existe.", 404
    )


@app.exception_handler(GrupoNoEncontrado)
def grupo_no_encontrado(request: Request, error: GrupoNoEncontrado):
    return _pagina_error(request, "No encontrado", "Ese grupo ya no existe.", 404)


@app.exception_handler(ValueError)
def valor_invalido(request: Request, error: ValueError):
    # Los servicios lanzan ValueError con el mensaje ya redactado en español.
    # Un ValueError de otra procedencia (un int() sobre basura, un bug) llegaría
    # aquí con texto en inglés y se mostraría tal cual, así que se registra
    # siempre: si no, un fallo de programación se disfraza de dato mal escrito
    # y desaparece sin dejar rastro.
    logging.getLogger("s21").exception("ValueError sin capturar: %s", error)
    return _pagina_error(request, "Datos incorrectos", str(error), 400)


@app.exception_handler(IntegrityError)
def integridad(request: Request, error: IntegrityError):
    return _pagina_error(
        request,
        "No se pudo guardar",
        "Algún dato relacionado ya no existe. Recarga la página y vuelve a intentarlo.",
        400,
    )


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


app.include_router(sesion.router)
app.include_router(inicio.router)
app.include_router(publicadores.router)
app.include_router(grupos.router)
app.include_router(grilla.router)
