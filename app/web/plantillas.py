from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.dominio import NOMBRE_MES

DIRECTORIO = Path(__file__).resolve().parent / "templates"

def _mes_nombre(mes: int) -> str:
    # Defensa en profundidad: las rutas ya validan el mes antes de llegar
    # aquí, pero si algo se cuela fuera de 1-12 (o un valor que no es ni
    # siquiera un mes), un KeyError sin capturar sería una traza cruda en
    # pantalla. Mejor mostrar el número tal cual que reventar la página.
    nombre = NOMBRE_MES.get(mes)
    return nombre.capitalize() if nombre else str(mes)


plantillas = Jinja2Templates(directory=str(DIRECTORIO))
plantillas.env.filters["mes_nombre"] = _mes_nombre
