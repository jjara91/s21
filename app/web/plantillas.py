from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.dominio import NOMBRE_MES

DIRECTORIO = Path(__file__).resolve().parent / "templates"

plantillas = Jinja2Templates(directory=str(DIRECTORIO))
plantillas.env.filters["mes_nombre"] = lambda mes: NOMBRE_MES[mes].capitalize()
