from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import SinSesion, redirigir_al_login
from app.config import cargar_config
from app.db import motor
from app.web.plantillas import DIRECTORIO
from app.web.routers import grupos, inicio, publicadores, sesion


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


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


app.include_router(sesion.router)
app.include_router(inicio.router)
app.include_router(publicadores.router)
app.include_router(grupos.router)
