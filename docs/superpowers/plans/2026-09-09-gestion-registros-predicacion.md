# Gestión de registros de predicación (S-21) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicación web local en Docker que importa tarjetas S-21 en PDF, guarda publicadores, nombramientos y registros mensuales en SQLite, y vuelve a generar las tarjetas en PDF.

**Architecture:** FastAPI sirve HTML renderizado con Jinja2 y HTMX. Tres capas con límites estrictos: `app/pdf/` habla solo diccionarios y dataclasses (no conoce SQL ni HTTP), `app/services/` contiene la lógica de dominio sobre SQLModel (no conoce HTTP), `app/web/routers/` traduce petición a servicio y resultado a plantilla. El S-21 es un AcroForm de 75 campos, así que importar es leer campos y exportar es rellenar la plantilla oficial.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, SQLite, Jinja2, HTMX, pypdf. Pruebas con pytest, httpx y reportlab.

**Spec:** `docs/superpowers/specs/2026-09-09-gestion-registros-predicacion-design.md`

## Global Constraints

- Python 3.12. Dependencias de runtime: `fastapi`, `uvicorn[standard]`, `sqlmodel`, `jinja2`, `python-multipart`, `itsdangerous`, `pypdf>=5.1`. De desarrollo: `pytest`, `httpx`, `reportlab`.
- Sin build step de JavaScript y sin librerías de terceros en el navegador: las pantallas son formularios HTML normales. No se sirve ningún estático de terceros, ni local ni desde CDN.
- Interfaz, nombres de rutas y mensajes al usuario en español.
- La aplicación no hace ninguna llamada de red saliente, ni en runtime ni en las pruebas.
- `data/` está en `.gitignore`. Ninguna tarjeta con datos reales entra al repositorio, ni como fixture.
- El formulario oficial S-21 no se distribuye en el repositorio. Las pruebas usan un PDF sintético con los mismos nombres de campo.
- El puerto se publica solo en loopback: `127.0.0.1:8000:8000`.
- Dentro de `app/`, `app/pdf/campos.py` es el único archivo que puede mencionar nombres de campo como `900_1_Text_SanSerif`. Las pruebas de contrato sí escriben esos literales a propósito: son valores testigo frente al formulario real, y derivarlos de `campos.py` las volvería tautológicas.
- Año de servicio: del 1 de septiembre al 31 de agosto. El año N abarca `[01-09-(N-1), 31-08-N]`.
- Casillas marcadas: valor `/Yes`. Desmarcadas: `/Off`.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml` | Dependencias y configuración de pytest |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | Despliegue |
| `app/config.py` | Lectura de variables de entorno |
| `app/dominio.py` | Dataclasses compartidas entre `pdf/` y `services/` |
| `app/db.py` | Engine, sesión, aplicación de migraciones |
| `app/models.py` | Tablas SQLModel |
| `migrations/001_inicial.sql` | Esquema inicial |
| `app/pdf/campos.py` | Mapa de nombres de campo del S-21 |
| `app/pdf/plantilla.py` | Vaciar una tarjeta para obtener la plantilla |
| `app/pdf/importar.py` | PDF → `DatosTarjeta` |
| `app/pdf/exportar.py` | `DatosTarjeta` → PDF editable y aplanado |
| `app/services/publicadores.py` | CRUD, normalización y match de nombres |
| `app/services/nombramientos.py` | Vigencia por año y por mes, notas sugeridas |
| `app/services/registros.py` | Año de servicio, carga mensual, armado de tarjeta |
| `app/services/informe.py` | Categoría por mes y agregados |
| `app/services/alertas.py` | Irregulares e inactivos |
| `app/services/importacion.py` | Comparar tarjeta contra base, aplicar y deshacer |
| `app/auth.py` | Login por cookie firmada |
| `app/main.py` | Arranque y montaje de routers |
| `app/web/routers/*.py` | Un router por pantalla |
| `app/web/templates/` | Plantillas Jinja |
| `tests/fixtures/sintetico.py` | Generador del S-21 sintético |

---

## Task 1: Andamiaje del proyecto

**Files:**
- Create: `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `app/__init__.py`, `app/config.py`, `app/main.py`, `tests/__init__.py`, `tests/test_salud.py`

**Interfaces:**
- Consumes: nada
- Produces: `app.config.Config` con atributos `auth_user: str`, `auth_pass: str`, `secret_key: str`, `data_dir: Path`; `app.config.cargar_config() -> Config`. `app.main.app` es la instancia FastAPI. Ruta `GET /salud` devuelve `{"estado": "ok"}`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_salud.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_salud_responde_ok():
    cliente = TestClient(app)
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/test_salud.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Crear `pyproject.toml`**

```toml
[project]
name = "s21"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "sqlmodel",
    "jinja2",
    "python-multipart",
    "itsdangerous",
    "pypdf>=5.1",
]

[project.optional-dependencies]
dev = ["pytest", "httpx", "reportlab"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 4: Crear `app/config.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    auth_user: str
    auth_pass: str
    secret_key: str
    data_dir: Path

    @property
    def ruta_db(self) -> Path:
        return self.data_dir / "s21.db"

    @property
    def ruta_plantilla(self) -> Path:
        return self.data_dir / "plantilla_s21.pdf"


def cargar_config() -> Config:
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        auth_user=os.environ.get("AUTH_USER", "admin"),
        auth_pass=os.environ.get("AUTH_PASS", "cambiar"),
        secret_key=os.environ.get("SECRET_KEY", "clave-de-desarrollo-no-usar-en-serio"),
        data_dir=data_dir,
    )
```

- [ ] **Step 5: Crear `app/main.py` y `app/__init__.py`**

`app/__init__.py` queda vacío. `app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Registros de predicación")


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `pip install -e ".[dev]" && pytest tests/test_salud.py -v`
Expected: PASS

- [ ] **Step 7: Crear los archivos de despliegue**

`.gitignore`:

```
data/
__pycache__/
*.egg-info/
.venv/
.env
.pytest_cache/
```

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`:

```yaml
services:
  s21:
    build: .
    ports: ["127.0.0.1:8000:8000"]
    volumes: ["./data:/data"]
    env_file: .env
    restart: unless-stopped
```

`.env.example`:

```
AUTH_USER=secretario
AUTH_PASS=cambia-esta-clave
SECRET_KEY=cadena-larga-y-aleatoria
```

- [ ] **Step 8: Crear `migrations/.gitkeep` para que el Dockerfile no falle**

Run: `mkdir -p migrations && touch migrations/.gitkeep`

- [ ] **Step 9: Verificar que la imagen construye y responde**

Run: `docker compose build && docker compose up -d && sleep 3 && curl -s localhost:8000/salud && docker compose down`
Expected: `{"estado":"ok"}`

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml Dockerfile docker-compose.yml .env.example .gitignore app tests migrations
git commit -m "feat: andamiaje del proyecto con FastAPI y Docker"
```

---

## Task 2: Mapa de campos del S-21 y PDF sintético de pruebas

**Files:**
- Create: `app/pdf/__init__.py`, `app/pdf/campos.py`, `tests/fixtures/__init__.py`, `tests/fixtures/sintetico.py`, `tests/conftest.py`, `tests/pdf/__init__.py`, `tests/pdf/test_campos.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `app.pdf.campos`: `CABECERA_TEXTO: dict[str, str]`, `CABECERA_SEXO: dict[str, str]`, `CABECERA_ESPERANZA: dict[str, str]`, `CABECERA_NOMBRAMIENTOS: dict[str, str]`, `FILA: dict[str, str]`, `TOTAL: dict[str, str]`, `MES_A_FILA: dict[int, int]`, `MESES_ORDENADOS: list[int]`, `campo_fila(clave: str, mes: int) -> str`, `CAMPOS_TEXTO: frozenset[str]`, `CAMPOS_CASILLA: frozenset[str]`, `TODOS_LOS_CAMPOS: frozenset[str]` (75 nombres).
  - `tests.fixtures.sintetico.crear_s21_sintetico(destino: Path) -> Path` genera un PDF de una página con los 75 campos.
  - `tests/conftest.py` expone la fixture `plantilla_sintetica` (ruta a un PDF sintético en blanco, por sesión) y `plantilla_real` (ruta a `data/plantilla_s21.pdf`, o `pytest.skip` si no existe).

- [ ] **Step 1: Escribir el test que falla**

`tests/pdf/test_campos.py`:

```python
from pypdf import PdfReader

from app.pdf import campos


def test_hay_exactamente_75_campos():
    assert len(campos.TODOS_LOS_CAMPOS) == 75


def test_texto_y_casillas_no_se_solapan():
    assert campos.CAMPOS_TEXTO & campos.CAMPOS_CASILLA == frozenset()
    assert campos.CAMPOS_TEXTO | campos.CAMPOS_CASILLA == campos.TODOS_LOS_CAMPOS


def test_900_5_es_texto_no_casilla():
    # la fecha de bautismo va entre dos bloques de casillas; es fácil contarla mal
    assert "900_5_Text_SanSerif" in campos.CAMPOS_TEXTO


def test_septiembre_es_la_fila_20_y_agosto_la_31():
    assert campos.MES_A_FILA[9] == 20
    assert campos.MES_A_FILA[8] == 31
    assert campos.MESES_ORDENADOS == [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]


def test_campo_fila_arma_el_nombre():
    assert campos.campo_fila("notas", 7) == "905_30_Text_SanSerif"


def test_el_sintetico_expone_los_mismos_campos(plantilla_sintetica):
    presentes = set(PdfReader(plantilla_sintetica).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)


def test_el_formulario_real_expone_los_mismos_campos(plantilla_real):
    presentes = set(PdfReader(plantilla_real).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/pdf/test_campos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.pdf'`

- [ ] **Step 3: Crear `app/pdf/campos.py`**

```python
"""Único lugar del proyecto que conoce los nombres de campo del formulario S-21.

Formulario de referencia: S-21-S 11/23. Si aparece una versión nueva, se ajusta
este archivo y nada más.
"""

CABECERA_TEXTO = {
    "nombre": "900_1_Text_SanSerif",
    "fecha_nacimiento": "900_2_Text_SanSerif",
    "fecha_bautismo": "900_5_Text_SanSerif",
    "anio_servicio": "900_13_Text_C_SanSerif",
}

CABECERA_SEXO = {"H": "900_3_CheckBox", "M": "900_4_CheckBox"}

CABECERA_ESPERANZA = {
    "otras_ovejas": "900_6_CheckBox",
    "ungido": "900_7_CheckBox",
}

CABECERA_NOMBRAMIENTOS = {
    "anciano": "900_8_CheckBox",
    "siervo_ministerial": "900_9_CheckBox",
    "precursor_regular": "900_10_CheckBox",
    "precursor_especial": "900_11_CheckBox",
    "misionero_campo": "900_12_CheckBox",
}

FILA = {
    "participo": "901_{i}_CheckBox",
    "cursos_biblicos": "902_{i}_Text_C_SanSerif",
    "precursor_auxiliar": "903_{i}_CheckBox",
    "horas": "904_{i}_S21_Value",
    "notas": "905_{i}_Text_SanSerif",
}

TOTAL = {"horas": "904_32_S21_Value", "notas": "905_32_Text_SanSerif"}

# El año de servicio empieza en septiembre: la fila 20 es septiembre y la 31, agosto.
MESES_ORDENADOS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
MES_A_FILA = {mes: 20 + i for i, mes in enumerate(MESES_ORDENADOS)}

FILAS_DE_CASILLA = ("participo", "precursor_auxiliar")

MARCADA = "/Yes"
DESMARCADA = "/Off"


def campo_fila(clave: str, mes: int) -> str:
    """Nombre del campo `clave` para el mes calendario `mes` (1-12)."""
    return FILA[clave].format(i=MES_A_FILA[mes])


def _construir_conjuntos() -> tuple[frozenset[str], frozenset[str]]:
    texto = set(CABECERA_TEXTO.values()) | set(TOTAL.values())
    casilla = (
        set(CABECERA_SEXO.values())
        | set(CABECERA_ESPERANZA.values())
        | set(CABECERA_NOMBRAMIENTOS.values())
    )
    for mes in MESES_ORDENADOS:
        for clave in FILA:
            destino = casilla if clave in FILAS_DE_CASILLA else texto
            destino.add(campo_fila(clave, mes))
    return frozenset(texto), frozenset(casilla)


CAMPOS_TEXTO, CAMPOS_CASILLA = _construir_conjuntos()
TODOS_LOS_CAMPOS = CAMPOS_TEXTO | CAMPOS_CASILLA
```

- [ ] **Step 4: Crear el generador de PDF sintético**

`tests/fixtures/sintetico.py`:

```python
"""Genera un PDF con los mismos campos que el S-21 pero sin su contenido.

El formulario oficial no se distribuye en el repositorio. Las pruebas de la capa
PDF trabajan contra este sustituto, que tiene los 75 campos con los mismos
nombres y tipos.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.pdf import campos


def crear_s21_sintetico(destino: Path) -> Path:
    lienzo = canvas.Canvas(str(destino), pagesize=letter)
    formulario = lienzo.acroForm
    huecos = iter([(x, y) for x in (40, 210, 380) for y in range(760, 40, -14)])

    for nombre in sorted(campos.CAMPOS_TEXTO):
        x, y = next(huecos)
        formulario.textfield(
            name=nombre, x=x, y=y, width=150, height=11, fontSize=7, borderWidth=0
        )
    for nombre in sorted(campos.CAMPOS_CASILLA):
        x, y = next(huecos)
        formulario.checkbox(name=nombre, x=x, y=y, size=9)

    # showPage antes de save: sin esto reportlab deja la referencia a la página
    # sin resolver y falla con "forward reference to 'Page1'".
    lienzo.showPage()
    lienzo.save()
    return destino
```

`tests/fixtures/__init__.py` queda vacío.

- [ ] **Step 5: Crear `tests/conftest.py`**

```python
from pathlib import Path

import pytest

from tests.fixtures.sintetico import crear_s21_sintetico


@pytest.fixture(scope="session")
def plantilla_sintetica(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("pdf") / "sintetico.pdf"
    return crear_s21_sintetico(destino)


@pytest.fixture(scope="session")
def plantilla_real() -> Path:
    ruta = Path("data/plantilla_s21.pdf")
    if not ruta.exists():
        pytest.skip("no hay plantilla real en data/; se corre solo donde exista")
    return ruta
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `pytest tests/pdf/test_campos.py -v`
Expected: PASS, con `test_el_formulario_real_expone_los_mismos_campos` en SKIPPED mientras no exista `data/plantilla_s21.pdf`

- [ ] **Step 7: Commit**

```bash
git add app/pdf tests/fixtures tests/conftest.py tests/pdf
git commit -m "feat: mapa de campos del S-21 y generador de PDF sintético para pruebas"
```

---

## Task 3: Dataclasses de dominio

**Files:**
- Create: `app/dominio.py`, `tests/test_dominio.py`

**Interfaces:**
- Consumes: `app.pdf.campos.MESES_ORDENADOS`
- Produces: `app.dominio.FilaMes`, `app.dominio.DatosTarjeta`, `app.dominio.TIPOS_NOMBRAMIENTO`, `app.dominio.anio_servicio_de(anio: int, mes: int) -> int`, `app.dominio.rango_anio_servicio(anio_servicio: int) -> tuple[date, date]`, `app.dominio.meses_del_anio(anio_servicio: int) -> list[tuple[int, int]]`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_dominio.py`:

```python
from datetime import date

import pytest

from app import dominio


@pytest.mark.parametrize(
    "anio,mes,esperado",
    [(2025, 9, 2026), (2025, 12, 2026), (2026, 1, 2026), (2026, 8, 2026), (2026, 9, 2027)],
)
def test_anio_servicio_arranca_en_septiembre(anio, mes, esperado):
    assert dominio.anio_servicio_de(anio, mes) == esperado


def test_rango_del_anio_de_servicio():
    assert dominio.rango_anio_servicio(2026) == (date(2025, 9, 1), date(2026, 8, 31))


def test_meses_del_anio_van_de_septiembre_a_agosto():
    meses = dominio.meses_del_anio(2026)
    assert len(meses) == 12
    assert meses[0] == (2025, 9)
    assert meses[3] == (2025, 12)
    assert meses[4] == (2026, 1)
    assert meses[-1] == (2026, 8)


def test_tarjeta_vacia_tiene_doce_meses_en_orden():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    assert [fila.mes for fila in tarjeta.meses] == [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    assert all(fila.horas is None for fila in tarjeta.meses)


def test_total_horas_ignora_los_meses_sin_horas():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    tarjeta.meses[0].horas = 15
    tarjeta.meses[2].horas = 30
    assert tarjeta.total_horas() == 45


def test_total_horas_es_none_si_ningun_mes_tiene_horas():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    assert tarjeta.total_horas() is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/test_dominio.py -v`
Expected: FAIL con `ImportError: cannot import name 'dominio'`

- [ ] **Step 3: Crear `app/dominio.py`**

```python
"""Objetos que cruzan la frontera entre la capa PDF y la capa de servicios.

No dependen de SQLModel ni de FastAPI a propósito: `app/pdf/` los usa sin tocar
la base de datos.
"""

from dataclasses import dataclass, field
from datetime import date

from app.pdf.campos import MESES_ORDENADOS

TIPOS_NOMBRAMIENTO = (
    "anciano",
    "siervo_ministerial",
    "precursor_regular",
    "precursor_especial",
    "misionero_campo",
)

TIPOS_CON_HORAS = ("precursor_regular", "precursor_especial", "misionero_campo")

NOMBRE_MES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


def anio_servicio_de(anio: int, mes: int) -> int:
    """El año de servicio N va de septiembre de N-1 a agosto de N."""
    return anio + 1 if mes >= 9 else anio


def rango_anio_servicio(anio_servicio: int) -> tuple[date, date]:
    return date(anio_servicio - 1, 9, 1), date(anio_servicio, 8, 31)


def meses_del_anio(anio_servicio: int) -> list[tuple[int, int]]:
    """Los 12 pares (año calendario, mes) del año de servicio, de sep a ago."""
    return [
        (anio_servicio - 1 if mes >= 9 else anio_servicio, mes) for mes in MESES_ORDENADOS
    ]


@dataclass
class FilaMes:
    mes: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


@dataclass
class DatosTarjeta:
    nombre: str
    anio_servicio: int | None = None
    fecha_nacimiento: date | None = None
    fecha_bautismo: date | None = None
    # texto original cuando la fecha del PDF no se pudo interpretar
    fecha_nacimiento_cruda: str | None = None
    fecha_bautismo_cruda: str | None = None
    sexo: str | None = None
    esperanza: str | None = None
    nombramientos: set[str] = field(default_factory=set)
    meses: list[FilaMes] = field(default_factory=list)

    @classmethod
    def vacia(cls, nombre: str, anio_servicio: int | None = None) -> "DatosTarjeta":
        return cls(
            nombre=nombre,
            anio_servicio=anio_servicio,
            meses=[FilaMes(mes=mes) for mes in MESES_ORDENADOS],
        )

    def mes(self, numero: int) -> FilaMes:
        for fila in self.meses:
            if fila.mes == numero:
                return fila
        raise KeyError(f"la tarjeta no tiene el mes {numero}")

    def total_horas(self) -> int | None:
        horas = [fila.horas for fila in self.meses if fila.horas is not None]
        return sum(horas) if horas else None
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/test_dominio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/dominio.py tests/test_dominio.py
git commit -m "feat: dataclasses de dominio y cálculo del año de servicio"
```

---

## Task 4: Generar la plantilla en blanco

**Files:**
- Create: `app/pdf/plantilla.py`, `tests/pdf/test_plantilla.py`

**Interfaces:**
- Consumes: `app.pdf.campos`
- Produces: `app.pdf.plantilla.TarjetaInvalida` (excepción con atributo `faltantes: list[str]`), `app.pdf.plantilla.validar_es_s21(contenido: bytes) -> None`, `app.pdf.plantilla.crear_plantilla(contenido: bytes) -> bytes`.

- [ ] **Step 1: Escribir el test que falla**

`tests/pdf/test_plantilla.py`:

```python
import pytest
from pypdf import PdfReader, PdfWriter

from app.pdf import campos, plantilla
from io import BytesIO


def _con_valores(ruta) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(
        escritor.pages[0],
        {
            campos.CABECERA_TEXTO["nombre"]: "Rojas Vega Mauricio",
            campos.CABECERA_NOMBRAMIENTOS["anciano"]: campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
        auto_regenerate=False,
    )
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def test_validar_acepta_un_s21(plantilla_sintetica):
    plantilla.validar_es_s21(plantilla_sintetica.read_bytes())  # no lanza


def test_validar_rechaza_un_pdf_sin_formulario():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)
    with pytest.raises(plantilla.TarjetaInvalida) as error:
        plantilla.validar_es_s21(buffer.getvalue())
    assert len(error.value.faltantes) == 75


def test_validar_rechaza_un_archivo_que_no_abre_como_pdf():
    with pytest.raises(plantilla.TarjetaInvalida):
        plantilla.validar_es_s21(b"esto no es un PDF")


def test_crear_plantilla_borra_todos_los_valores(plantilla_sintetica):
    lleno = _con_valores(plantilla_sintetica)
    vacio = plantilla.crear_plantilla(lleno)

    quedan = {
        nombre: campo.get("/V")
        for nombre, campo in (PdfReader(BytesIO(vacio)).get_fields() or {}).items()
        if campo.get("/V") not in (None, "", campos.DESMARCADA)
    }
    assert quedan == {}


def test_crear_plantilla_conserva_los_75_campos(plantilla_sintetica):
    vacio = plantilla.crear_plantilla(_con_valores(plantilla_sintetica))
    presentes = set(PdfReader(BytesIO(vacio)).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/pdf/test_plantilla.py -v`
Expected: FAIL con `ImportError: cannot import name 'plantilla'`

- [ ] **Step 3: Crear `app/pdf/plantilla.py`**

```python
"""Validación de que un PDF es una tarjeta S-21 y vaciado a plantilla."""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from app.pdf import campos


class TarjetaInvalida(Exception):
    def __init__(self, mensaje: str, faltantes: list[str] | None = None) -> None:
        super().__init__(mensaje)
        self.faltantes = faltantes or []


def _leer(contenido: bytes) -> PdfReader:
    try:
        return PdfReader(BytesIO(contenido))
    except (PdfReadError, OSError, ValueError) as error:
        raise TarjetaInvalida(f"el archivo no se pudo abrir como PDF: {error}") from error


def validar_es_s21(contenido: bytes) -> None:
    """Lanza TarjetaInvalida si el PDF no trae los 75 campos del S-21."""
    lector = _leer(contenido)
    presentes = set(lector.get_fields() or {})
    faltantes = sorted(campos.TODOS_LOS_CAMPOS - presentes)
    if faltantes:
        raise TarjetaInvalida(
            "el PDF no es una tarjeta S-21 rellenable "
            f"(faltan {len(faltantes)} campos, por ejemplo {faltantes[0]}); "
            "si es una tarjeta escaneada no sirve, hace falta el formulario original",
            faltantes,
        )


def crear_plantilla(contenido: bytes) -> bytes:
    """Devuelve la misma tarjeta con los 75 campos en blanco."""
    validar_es_s21(contenido)
    escritor = PdfWriter(clone_from=BytesIO(contenido))
    escritor.set_need_appearances_writer(True)

    en_blanco: dict[str, str] = {nombre: "" for nombre in campos.CAMPOS_TEXTO}
    en_blanco.update({nombre: campos.DESMARCADA for nombre in campos.CAMPOS_CASILLA})
    for pagina in escritor.pages:
        escritor.update_page_form_field_values(pagina, en_blanco, auto_regenerate=False)

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/pdf/test_plantilla.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf/plantilla.py tests/pdf/test_plantilla.py
git commit -m "feat: validación de tarjeta S-21 y vaciado a plantilla"
```

---

## Task 5: Leer una tarjeta S-21

**Files:**
- Create: `app/pdf/importar.py`, `tests/pdf/test_importar.py`

**Interfaces:**
- Consumes: `app.pdf.campos`, `app.pdf.plantilla.validar_es_s21`, `app.pdf.plantilla.TarjetaInvalida`, `app.dominio.DatosTarjeta`, `app.dominio.FilaMes`
- Produces: `app.pdf.importar.parsear_fecha(texto: str | None) -> tuple[date | None, str | None]` (devuelve la fecha y, si no se pudo interpretar, el texto crudo), `app.pdf.importar.leer_tarjeta(contenido: bytes) -> DatosTarjeta`.

- [ ] **Step 1: Escribir el test que falla**

`tests/pdf/test_importar.py`:

```python
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.pdf import campos, importar


def _tarjeta(ruta, valores: dict[str, str]) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(escritor.pages[0], valores, auto_regenerate=False)
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("14.03.1985", date(1985, 3, 14)),
        ("14/03/1985", date(1985, 3, 14)),
        ("1985-03-14", date(1985, 3, 14)),
        ("  07.06.2002 ", date(2002, 6, 7)),
    ],
)
def test_parsear_fecha_acepta_los_tres_formatos(texto, esperado):
    assert importar.parsear_fecha(texto) == (esperado, None)


@pytest.mark.parametrize("texto", ["", None, "   "])
def test_parsear_fecha_vacia_devuelve_none_sin_texto_crudo(texto):
    assert importar.parsear_fecha(texto) == (None, None)


def test_parsear_fecha_ilegible_conserva_el_texto_crudo():
    assert importar.parsear_fecha("marzo de 1985") == (None, "marzo de 1985")


def test_lee_la_cabecera(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["fecha_nacimiento"]: "14.03.1985",
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025",
            campos.CABECERA_SEXO["H"]: campos.MARCADA,
            campos.CABECERA_ESPERANZA["otras_ovejas"]: campos.MARCADA,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.nombre == "Mauricio Andrés Rojas Vega"
    assert tarjeta.fecha_nacimiento == date(1985, 3, 14)
    assert tarjeta.fecha_bautismo == date(2002, 6, 7)
    assert tarjeta.anio_servicio == 2025
    assert tarjeta.sexo == "H"
    assert tarjeta.esperanza == "otras_ovejas"
    assert tarjeta.nombramientos == {"siervo_ministerial"}


def test_lee_las_filas_de_los_meses(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("precursor_auxiliar", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
            campos.campo_fila("notas", 9): "de 15 horas",
            campos.campo_fila("cursos_biblicos", 4): "1",
            campos.campo_fila("notas", 7): "nombrado siervo ministerial",
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    septiembre = tarjeta.mes(9)
    assert septiembre.participo is True
    assert septiembre.precursor_auxiliar is True
    assert septiembre.horas == 15
    assert septiembre.notas == "de 15 horas"
    assert tarjeta.mes(4).cursos_biblicos == 1
    assert tarjeta.mes(7).notas == "nombrado siervo ministerial"
    assert tarjeta.mes(10).participo is False
    assert tarjeta.mes(10).horas is None


def test_las_horas_no_numericas_no_abortan_la_lectura(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Perez Ana",
            campos.campo_fila("horas", 9): "quince",
            campos.campo_fila("horas", 10): "30",
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.mes(9).horas is None
    assert tarjeta.mes(9).notas == "quince"  # el texto no se pierde
    assert tarjeta.mes(10).horas == 30


def test_rechaza_un_pdf_que_no_es_s21():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)
    with pytest.raises(importar.TarjetaInvalida):
        importar.leer_tarjeta(buffer.getvalue())
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/pdf/test_importar.py -v`
Expected: FAIL con `ImportError: cannot import name 'importar'`

- [ ] **Step 3: Crear `app/pdf/importar.py`**

```python
"""Lectura de una tarjeta S-21 a objetos de dominio. No toca la base de datos."""

from datetime import date, datetime
from io import BytesIO

from pypdf import PdfReader

from app.dominio import DatosTarjeta, FilaMes
from app.pdf import campos
from app.pdf.plantilla import TarjetaInvalida, validar_es_s21

FORMATOS_FECHA = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d")


def parsear_fecha(texto: str | None) -> tuple[date | None, str | None]:
    """Devuelve (fecha, None) si se pudo interpretar, (None, texto) si no."""
    limpio = (texto or "").strip()
    if not limpio:
        return None, None
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(limpio, formato).date(), None
        except ValueError:
            continue
    return None, limpio


def _entero(texto: str | None) -> tuple[int | None, str | None]:
    """Devuelve (numero, None) o (None, texto) si el contenido no es numérico."""
    limpio = (texto or "").strip()
    if not limpio:
        return None, None
    try:
        return int(limpio), None
    except ValueError:
        return None, limpio


def _valores(contenido: bytes) -> dict[str, str]:
    lector = PdfReader(BytesIO(contenido))
    crudos = lector.get_fields() or {}
    return {nombre: campo.get("/V") for nombre, campo in crudos.items()}


def _marcada(valores: dict[str, str], nombre: str) -> bool:
    return str(valores.get(nombre) or "") == campos.MARCADA


def _texto(valores: dict[str, str], nombre: str) -> str:
    return str(valores.get(nombre) or "").strip()


def _unir_notas(*partes: str | None) -> str | None:
    presentes = [parte.strip() for parte in partes if parte and parte.strip()]
    return " · ".join(presentes) if presentes else None


def leer_tarjeta(contenido: bytes) -> DatosTarjeta:
    validar_es_s21(contenido)
    valores = _valores(contenido)

    nacimiento, nacimiento_crudo = parsear_fecha(
        _texto(valores, campos.CABECERA_TEXTO["fecha_nacimiento"])
    )
    bautismo, bautismo_crudo = parsear_fecha(
        _texto(valores, campos.CABECERA_TEXTO["fecha_bautismo"])
    )
    anio, _ = _entero(_texto(valores, campos.CABECERA_TEXTO["anio_servicio"]))

    sexo = next(
        (clave for clave, campo in campos.CABECERA_SEXO.items() if _marcada(valores, campo)),
        None,
    )
    esperanza = next(
        (
            clave
            for clave, campo in campos.CABECERA_ESPERANZA.items()
            if _marcada(valores, campo)
        ),
        None,
    )
    nombramientos = {
        clave
        for clave, campo in campos.CABECERA_NOMBRAMIENTOS.items()
        if _marcada(valores, campo)
    }

    meses = []
    for mes in campos.MESES_ORDENADOS:
        horas, horas_crudas = _entero(_texto(valores, campos.campo_fila("horas", mes)))
        cursos, cursos_crudos = _entero(
            _texto(valores, campos.campo_fila("cursos_biblicos", mes))
        )
        meses.append(
            FilaMes(
                mes=mes,
                participo=_marcada(valores, campos.campo_fila("participo", mes)),
                cursos_biblicos=cursos,
                precursor_auxiliar=_marcada(
                    valores, campos.campo_fila("precursor_auxiliar", mes)
                ),
                horas=horas,
                # un valor no numérico se conserva en las notas en vez de perderse
                notas=_unir_notas(
                    _texto(valores, campos.campo_fila("notas", mes)) or None,
                    horas_crudas,
                    cursos_crudos,
                ),
            )
        )

    return DatosTarjeta(
        nombre=_texto(valores, campos.CABECERA_TEXTO["nombre"]),
        anio_servicio=anio,
        fecha_nacimiento=nacimiento,
        fecha_bautismo=bautismo,
        fecha_nacimiento_cruda=nacimiento_crudo,
        fecha_bautismo_cruda=bautismo_crudo,
        sexo=sexo,
        esperanza=esperanza,
        nombramientos=nombramientos,
        meses=meses,
    )
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/pdf/test_importar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf/importar.py tests/pdf/test_importar.py
git commit -m "feat: lectura de tarjetas S-21 a objetos de dominio"
```

---

## Task 6: Exportar la tarjeta a PDF editable

**Files:**
- Create: `app/pdf/exportar.py`, `tests/pdf/test_exportar.py`

**Interfaces:**
- Consumes: `app.pdf.campos`, `app.dominio.DatosTarjeta`, `app.pdf.importar.leer_tarjeta`
- Produces: `app.pdf.exportar.rellenar(plantilla: bytes, datos: DatosTarjeta) -> bytes`, `app.pdf.exportar.nombre_archivo(nombre: str, anio_servicio: int) -> str`.

- [ ] **Step 1: Escribir el test que falla**

`tests/pdf/test_exportar.py`:

```python
from datetime import date

from app.dominio import DatosTarjeta
from app.pdf import exportar, importar


def _tarjeta_completa() -> DatosTarjeta:
    tarjeta = DatosTarjeta.vacia(nombre="Pérez Gómez Ana María", anio_servicio=2026)
    tarjeta.fecha_nacimiento = date(1988, 5, 12)
    tarjeta.fecha_bautismo = date(2010, 4, 3)
    tarjeta.sexo = "M"
    tarjeta.esperanza = "otras_ovejas"
    tarjeta.nombramientos = {"precursor_regular"}
    septiembre = tarjeta.mes(9)
    septiembre.participo = True
    septiembre.horas = 52
    septiembre.cursos_biblicos = 2
    octubre = tarjeta.mes(10)
    octubre.participo = True
    octubre.precursor_auxiliar = True
    octubre.horas = 30
    octubre.notas = "precursora auxiliar en marzo y abril"
    return tarjeta


def test_round_trip_devuelve_los_mismos_datos(plantilla_sintetica):
    original = _tarjeta_completa()

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), original)
    leida = importar.leer_tarjeta(pdf)

    assert leida.nombre == original.nombre
    assert leida.fecha_nacimiento == original.fecha_nacimiento
    assert leida.fecha_bautismo == original.fecha_bautismo
    assert leida.sexo == "M"
    assert leida.esperanza == "otras_ovejas"
    assert leida.nombramientos == {"precursor_regular"}
    assert leida.anio_servicio == 2026
    assert leida.mes(9).horas == 52
    assert leida.mes(9).cursos_biblicos == 2
    assert leida.mes(10).precursor_auxiliar is True
    assert leida.mes(10).notas == "precursora auxiliar en marzo y abril"


def test_los_meses_vacios_siguen_vacios(plantilla_sintetica):
    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    leida = importar.leer_tarjeta(pdf)

    assert leida.mes(1).participo is False
    assert leida.mes(1).horas is None
    assert leida.mes(1).cursos_biblicos is None
    assert leida.mes(1).notas is None


def test_cursos_en_cero_se_escribe_como_cero(plantilla_sintetica):
    tarjeta = DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    tarjeta.mes(9).cursos_biblicos = 0

    leida = importar.leer_tarjeta(
        exportar.rellenar(plantilla_sintetica.read_bytes(), tarjeta)
    )

    assert leida.mes(9).cursos_biblicos == 0


def test_escribe_el_total_de_horas(plantilla_sintetica):
    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())

    from pypdf import PdfReader
    from io import BytesIO
    from app.pdf import campos

    campos_leidos = PdfReader(BytesIO(pdf)).get_fields()
    assert campos_leidos[campos.TOTAL["horas"]].get("/V") == "82"
    assert (campos_leidos[campos.TOTAL["notas"]].get("/V") or "") == ""


def test_el_pdf_sigue_siendo_un_formulario(plantilla_sintetica):
    from pypdf import PdfReader
    from io import BytesIO

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    assert len(PdfReader(BytesIO(pdf)).get_fields() or {}) == 75


def test_nombre_de_archivo():
    assert exportar.nombre_archivo("Pérez Gómez Ana María", 2026) == (
        "Pérez Gómez Ana María - 2026.pdf"
    )


def test_nombre_de_archivo_sin_caracteres_de_ruta():
    assert exportar.nombre_archivo("Ana/María \\ Pérez", 2026) == (
        "Ana-María - Pérez - 2026.pdf"
    )
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/pdf/test_exportar.py -v`
Expected: FAIL con `ImportError: cannot import name 'exportar'`

- [ ] **Step 3: Crear `app/pdf/exportar.py`**

```python
"""Relleno de la plantilla S-21 con los datos de una tarjeta."""

import re
from datetime import date
from io import BytesIO

from pypdf import PdfWriter

from app.dominio import DatosTarjeta
from app.pdf import campos

FORMATO_FECHA = "%d.%m.%Y"


def _fecha(valor: date | None, crudo: str | None) -> str:
    if valor is not None:
        return valor.strftime(FORMATO_FECHA)
    return crudo or ""


def _numero(valor: int | None) -> str:
    return "" if valor is None else str(valor)


def _casilla(activa: bool) -> str:
    return campos.MARCADA if activa else campos.DESMARCADA


def valores_de(datos: DatosTarjeta) -> dict[str, str]:
    """Traduce la tarjeta al diccionario de campos del formulario."""
    valores: dict[str, str] = {
        campos.CABECERA_TEXTO["nombre"]: datos.nombre or "",
        campos.CABECERA_TEXTO["fecha_nacimiento"]: _fecha(
            datos.fecha_nacimiento, datos.fecha_nacimiento_cruda
        ),
        campos.CABECERA_TEXTO["fecha_bautismo"]: _fecha(
            datos.fecha_bautismo, datos.fecha_bautismo_cruda
        ),
        campos.CABECERA_TEXTO["anio_servicio"]: _numero(datos.anio_servicio),
        campos.TOTAL["horas"]: _numero(datos.total_horas()),
        # el formulario tiene una nota junto al total; no hay dato que la alimente
        campos.TOTAL["notas"]: "",
    }

    for clave, campo in campos.CABECERA_SEXO.items():
        valores[campo] = _casilla(datos.sexo == clave)
    for clave, campo in campos.CABECERA_ESPERANZA.items():
        valores[campo] = _casilla(datos.esperanza == clave)
    for clave, campo in campos.CABECERA_NOMBRAMIENTOS.items():
        valores[campo] = _casilla(clave in datos.nombramientos)

    for fila in datos.meses:
        valores[campos.campo_fila("participo", fila.mes)] = _casilla(fila.participo)
        valores[campos.campo_fila("cursos_biblicos", fila.mes)] = _numero(
            fila.cursos_biblicos
        )
        valores[campos.campo_fila("precursor_auxiliar", fila.mes)] = _casilla(
            fila.precursor_auxiliar
        )
        valores[campos.campo_fila("horas", fila.mes)] = _numero(fila.horas)
        valores[campos.campo_fila("notas", fila.mes)] = fila.notas or ""

    return valores


def rellenar(plantilla: bytes, datos: DatosTarjeta) -> bytes:
    escritor = PdfWriter(clone_from=BytesIO(plantilla))
    escritor.set_need_appearances_writer(True)
    for pagina in escritor.pages:
        escritor.update_page_form_field_values(
            pagina, valores_de(datos), auto_regenerate=True
        )
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def nombre_archivo(nombre: str, anio_servicio: int) -> str:
    limpio = re.sub(r"[/\\:]", "-", nombre).strip()
    return f"{limpio} - {anio_servicio}.pdf"
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/pdf/test_exportar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf/exportar.py tests/pdf/test_exportar.py
git commit -m "feat: exportación de tarjetas S-21 a PDF editable"
```

---

## Task 7: Aplanar el PDF exportado

**Files:**
- Modify: `app/pdf/exportar.py` (añadir `aplanar`)
- Modify: `tests/pdf/test_exportar.py` (añadir los tests de aplanado)

**Interfaces:**
- Consumes: `app.pdf.exportar.rellenar`
- Produces: `app.pdf.exportar.aplanar(pdf: bytes) -> bytes`.

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `tests/pdf/test_exportar.py`:

```python
def test_aplanar_deja_el_pdf_sin_campos_de_formulario(plantilla_sintetica):
    from io import BytesIO

    from pypdf import PdfReader

    editable = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    aplanado = exportar.aplanar(editable)

    assert PdfReader(BytesIO(aplanado)).get_fields() in (None, {})


def test_aplanar_conserva_los_valores_en_el_texto_de_la_pagina(plantilla_sintetica):
    from io import BytesIO

    from pypdf import PdfReader

    editable = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    aplanado = exportar.aplanar(editable)

    texto = PdfReader(BytesIO(aplanado)).pages[0].extract_text()
    for esperado in ("Pérez Gómez Ana María", "12.05.1988", "2026", "52", "82"):
        assert esperado in texto


def test_aplanar_no_altera_el_pdf_de_entrada(plantilla_sintetica):
    from io import BytesIO

    from pypdf import PdfReader

    editable = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    exportar.aplanar(editable)

    assert len(PdfReader(BytesIO(editable)).get_fields() or {}) == 75
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/pdf/test_exportar.py -k aplanar -v`
Expected: FAIL con `AttributeError: module 'app.pdf.exportar' has no attribute 'aplanar'`

- [ ] **Step 3: Añadir `aplanar` a `app/pdf/exportar.py`**

Añadir el import al inicio del archivo:

```python
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
```

Y al final del archivo:

```python
def _apariencia(widget: DictionaryObject) -> DictionaryObject | None:
    """Stream de apariencia normal del widget, resolviendo el estado de una casilla."""
    apariencias = widget.get("/AP")
    if not apariencias or "/N" not in apariencias.get_object():
        return None
    normal = apariencias.get_object()["/N"].get_object()
    if "/BBox" in normal:
        return normal
    estado = widget.get("/AS")
    if estado is None or estado not in normal:
        return None
    candidato = normal[estado].get_object()
    return candidato if "/BBox" in candidato else None


def aplanar(pdf: bytes) -> bytes:
    """Quema los valores en el contenido de la página y elimina el formulario.

    pypdf no trae aplanado: se estampa la apariencia de cada widget como XObject
    en el contenido de la página y luego se descartan las anotaciones.
    """
    escritor = PdfWriter(clone_from=BytesIO(pdf))

    for pagina in escritor.pages:
        recursos = pagina["/Resources"].get_object()
        if "/XObject" not in recursos:
            recursos[NameObject("/XObject")] = DictionaryObject()
        xobjects = recursos["/XObject"].get_object()

        operaciones: list[str] = []
        for indice, anotacion in enumerate(pagina.get("/Annots") or []):
            widget = anotacion.get_object()
            apariencia = _apariencia(widget)
            if apariencia is None:
                continue

            nombre = NameObject(f"/Plano{indice}")
            xobjects[nombre] = apariencia.indirect_reference or escritor._add_object(
                apariencia
            )

            rect = [float(valor) for valor in widget["/Rect"]]
            x0, y0 = min(rect[0], rect[2]), min(rect[1], rect[3])
            x1, y1 = max(rect[0], rect[2]), max(rect[1], rect[3])
            caja = [float(valor) for valor in apariencia["/BBox"]]
            ancho = (caja[2] - caja[0]) or 1.0
            alto = (caja[3] - caja[1]) or 1.0
            escala_x, escala_y = (x1 - x0) / ancho, (y1 - y0) / alto
            operaciones.append(
                f"q {escala_x:.5f} 0 0 {escala_y:.5f} "
                f"{x0 - caja[0] * escala_x:.3f} {y0 - caja[1] * escala_y:.3f} cm "
                f"{nombre} Do Q"
            )

        if operaciones:
            extra = DecodedStreamObject()
            # el "q Q" inicial cierra cualquier estado gráfico abierto en el contenido
            extra.set_data(("\nq Q\n" + "\n".join(operaciones)).encode())
            referencia = escritor._add_object(extra)
            actual = pagina.raw_get("/Contents")
            contenido = actual.get_object()
            pagina[NameObject("/Contents")] = (
                ArrayObject(list(contenido) + [referencia])
                if isinstance(contenido, ArrayObject)
                else ArrayObject([actual, referencia])
            )

        pagina[NameObject("/Annots")] = ArrayObject()

    if "/AcroForm" in escritor._root_object:
        del escritor._root_object[NameObject("/AcroForm")]

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
```

- [ ] **Step 4: Correr toda la suite de PDF y verificar que pasa**

Run: `pytest tests/pdf -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf/exportar.py tests/pdf/test_exportar.py
git commit -m "feat: exportación de tarjetas S-21 aplanadas"
```

---

## Task 8: Base de datos, modelos y migraciones

**Files:**
- Create: `app/models.py`, `app/db.py`, `migrations/001_inicial.sql`, `tests/test_db.py`
- Delete: `migrations/.gitkeep`

**Interfaces:**
- Consumes: `app.config.Config`
- Produces:
  - `app.models`: clases SQLModel `Publicador`, `Grupo`, `Nombramiento`, `RegistroMensual`, `Importacion`.
  - `app.db.crear_engine(ruta: Path)`, `app.db.aplicar_migraciones(engine) -> int` (devuelve la versión final), `app.db.sesion(engine) -> Iterator[Session]`, `app.db.motor()` (engine global perezoso construido desde `cargar_config()`), `app.db.obtener_sesion()` (dependencia de FastAPI).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_db.py`:

```python
from datetime import date

from sqlmodel import Session, select

from app import db, models


def test_aplicar_migraciones_deja_la_version_en_uno(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    assert db.aplicar_migraciones(engine) == 1


def test_aplicar_migraciones_es_idempotente(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)
    assert db.aplicar_migraciones(engine) == 1


def test_se_puede_guardar_y_leer_un_publicador_con_registros(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        grupo = models.Grupo(nombre="Centro")
        sesion.add(grupo)
        sesion.commit()
        sesion.refresh(grupo)

        publicador = models.Publicador(
            nombre_completo="Rojas Vega Mauricio",
            nombre_normalizado="rojas vega mauricio",
            fecha_bautismo=date(2002, 6, 7),
            sexo="H",
            esperanza="otras_ovejas",
            grupo_id=grupo.id,
        )
        sesion.add(publicador)
        sesion.commit()
        sesion.refresh(publicador)

        sesion.add(
            models.Nombramiento(
                publicador_id=publicador.id,
                tipo="siervo_ministerial",
                desde=date(2025, 7, 1),
            )
        )
        sesion.add(
            models.RegistroMensual(
                publicador_id=publicador.id,
                anio=2025,
                mes=9,
                participo=True,
                precursor_auxiliar=True,
                horas=15,
            )
        )
        sesion.commit()

    with Session(engine) as sesion:
        leido = sesion.exec(select(models.Publicador)).one()
        assert leido.nombre_completo == "Rojas Vega Mauricio"
        registros = sesion.exec(select(models.RegistroMensual)).all()
        assert len(registros) == 1
        assert registros[0].horas == 15


def test_un_publicador_no_puede_tener_dos_registros_del_mismo_mes(tmp_path):
    import sqlalchemy.exc
    import pytest

    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        publicador = models.Publicador(
            nombre_completo="Perez Ana", nombre_normalizado="perez ana"
        )
        sesion.add(publicador)
        sesion.commit()
        sesion.refresh(publicador)

        sesion.add(
            models.RegistroMensual(publicador_id=publicador.id, anio=2025, mes=9)
        )
        sesion.commit()
        sesion.add(
            models.RegistroMensual(publicador_id=publicador.id, anio=2025, mes=9)
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            sesion.commit()


def test_las_claves_foraneas_estan_activas(tmp_path):
    import sqlalchemy.exc
    import pytest

    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        sesion.add(models.RegistroMensual(publicador_id=999, anio=2025, mes=9))
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            sesion.commit()
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/test_db.py -v`
Expected: FAIL con `ImportError: cannot import name 'db'`

- [ ] **Step 3: Crear `migrations/001_inicial.sql`**

```sql
CREATE TABLE grupo (
    id                  INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL,
    superintendente_id  INTEGER REFERENCES publicador(id) ON DELETE SET NULL
);

CREATE TABLE publicador (
    id                  INTEGER PRIMARY KEY,
    nombre_completo     TEXT NOT NULL,
    nombre_normalizado  TEXT NOT NULL,
    fecha_nacimiento    DATE,
    fecha_bautismo      DATE,
    sexo                TEXT CHECK (sexo IN ('H', 'M')),
    esperanza           TEXT CHECK (esperanza IN ('otras_ovejas', 'ungido')),
    grupo_id            INTEGER REFERENCES grupo(id) ON DELETE SET NULL,
    fecha_baja          DATE,
    motivo_baja         TEXT
);

CREATE INDEX ix_publicador_nombre_normalizado ON publicador (nombre_normalizado);

CREATE TABLE nombramiento (
    id             INTEGER PRIMARY KEY,
    publicador_id  INTEGER NOT NULL REFERENCES publicador(id) ON DELETE CASCADE,
    tipo           TEXT NOT NULL CHECK (tipo IN (
                       'anciano', 'siervo_ministerial', 'precursor_regular',
                       'precursor_especial', 'misionero_campo')),
    desde          DATE NOT NULL,
    hasta          DATE
);

CREATE INDEX ix_nombramiento_publicador ON nombramiento (publicador_id);

CREATE TABLE registromensual (
    id                  INTEGER PRIMARY KEY,
    publicador_id       INTEGER NOT NULL REFERENCES publicador(id) ON DELETE CASCADE,
    anio                INTEGER NOT NULL,
    mes                 INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    participo           BOOLEAN NOT NULL DEFAULT 0,
    cursos_biblicos     INTEGER,
    precursor_auxiliar  BOOLEAN NOT NULL DEFAULT 0,
    horas               INTEGER,
    notas               TEXT,
    UNIQUE (publicador_id, anio, mes)
);

CREATE INDEX ix_registromensual_periodo ON registromensual (anio, mes);

CREATE TABLE importacion (
    id             INTEGER PRIMARY KEY,
    archivo        TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    fecha          DATETIME NOT NULL,
    lote           TEXT NOT NULL,
    publicador_id  INTEGER REFERENCES publicador(id) ON DELETE SET NULL,
    anio_servicio  INTEGER,
    accion         TEXT NOT NULL CHECK (accion IN ('creado', 'actualizado', 'descartado')),
    estado_previo  TEXT,
    deshecho       BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX ix_importacion_sha256 ON importacion (sha256);
CREATE INDEX ix_importacion_lote ON importacion (lote);
```

Nota: SQLite permite la referencia adelantada de `grupo.superintendente_id` a `publicador` porque no valida las claves foráneas al crear la tabla.

- [ ] **Step 4: Crear `app/models.py`**

```python
from datetime import date, datetime

from sqlmodel import Field, SQLModel


class Grupo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre: str
    superintendente_id: int | None = Field(default=None, foreign_key="publicador.id")


class Publicador(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre_completo: str
    nombre_normalizado: str = Field(index=True)
    fecha_nacimiento: date | None = None
    fecha_bautismo: date | None = None
    sexo: str | None = None
    esperanza: str | None = None
    grupo_id: int | None = Field(default=None, foreign_key="grupo.id")
    fecha_baja: date | None = None
    motivo_baja: str | None = None

    @property
    def de_baja(self) -> bool:
        return self.fecha_baja is not None


class Nombramiento(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    publicador_id: int = Field(foreign_key="publicador.id", index=True)
    tipo: str
    desde: date
    hasta: date | None = None


class RegistroMensual(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    publicador_id: int = Field(foreign_key="publicador.id", index=True)
    anio: int
    mes: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


class Importacion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    archivo: str
    sha256: str = Field(index=True)
    fecha: datetime
    lote: str = Field(index=True)
    publicador_id: int | None = Field(default=None, foreign_key="publicador.id")
    anio_servicio: int | None = None
    accion: str
    # JSON con el estado anterior de lo que tocó esta importación, para deshacerla
    estado_previo: str | None = None
    deshecho: bool = False
```

- [ ] **Step 5: Crear `app/db.py`**

```python
"""Engine, migraciones y sesiones.

El esquema vive en `migrations/*.sql` y no se genera desde los modelos: así el
archivo SQL es la fuente de verdad y las migraciones futuras son explícitas.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import cargar_config

DIRECTORIO_MIGRACIONES = Path(__file__).resolve().parent.parent / "migrations"


def crear_engine(ruta: Path) -> Engine:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{ruta}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(conexion, _registro):  # pragma: no cover - callback
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _version_actual(conexion) -> int:
    conexion.execute(
        text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    )
    fila = conexion.execute(text("SELECT version FROM schema_version")).first()
    if fila is None:
        conexion.execute(text("INSERT INTO schema_version (version) VALUES (0)"))
        return 0
    return int(fila[0])


def aplicar_migraciones(engine: Engine) -> int:
    """Aplica los scripts pendientes en orden y devuelve la versión resultante."""
    scripts = sorted(DIRECTORIO_MIGRACIONES.glob("[0-9][0-9][0-9]_*.sql"))
    with engine.begin() as conexion:
        version = _version_actual(conexion)
        for script in scripts:
            numero = int(script.name.split("_", 1)[0])
            if numero <= version:
                continue
            for sentencia in script.read_text(encoding="utf-8").split(";"):
                if sentencia.strip():
                    conexion.execute(text(sentencia))
            version = numero
        conexion.execute(text("UPDATE schema_version SET version = :v"), {"v": version})
    return version


@lru_cache(maxsize=1)
def motor() -> Engine:
    engine = crear_engine(cargar_config().ruta_db)
    aplicar_migraciones(engine)
    return engine


@contextmanager
def sesion(engine: Engine | None = None) -> Iterator[Session]:
    with Session(engine or motor()) as abierta:
        yield abierta


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI."""
    with Session(motor()) as abierta:
        yield abierta
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `rm -f migrations/.gitkeep && pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/db.py migrations tests/test_db.py
git rm --cached migrations/.gitkeep --ignore-unmatch
git commit -m "feat: esquema SQLite, modelos y migraciones numeradas"
```

---

## Task 9: Servicio de publicadores

**Files:**
- Create: `app/services/__init__.py`, `app/services/publicadores.py`, `tests/services/__init__.py`, `tests/services/test_publicadores.py`
- Modify: `tests/conftest.py` (añadir la fixture `sesion`)

**Interfaces:**
- Consumes: `app.db`, `app.models`
- Produces:
  - `app.services.publicadores.normalizar(nombre: str) -> str`
  - `app.services.publicadores.crear(sesion, nombre_completo, **campos) -> Publicador`
  - `app.services.publicadores.actualizar(sesion, publicador_id, **campos) -> Publicador`
  - `app.services.publicadores.obtener(sesion, publicador_id) -> Publicador`
  - `app.services.publicadores.buscar_por_nombre(sesion, nombre) -> Publicador | None`
  - `app.services.publicadores.listar(sesion, *, grupo_id=None, incluir_bajas=False, texto=None) -> list[Publicador]`
  - `app.services.publicadores.dar_de_baja(sesion, publicador_id, fecha, motivo) -> Publicador`
  - `tests/conftest.py` expone la fixture `sesion` (base SQLite temporal ya migrada, por test).

- [ ] **Step 1: Añadir la fixture de sesión a `tests/conftest.py`**

```python
from collections.abc import Iterator

from sqlmodel import Session

from app import db


@pytest.fixture
def engine(tmp_path):
    motor = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(motor)
    return motor


@pytest.fixture
def sesion(engine) -> Iterator[Session]:
    with Session(engine) as abierta:
        yield abierta
```

- [ ] **Step 2: Escribir el test que falla**

`tests/services/test_publicadores.py`:

```python
from datetime import date

import pytest

from app.models import Grupo
from app.services import publicadores


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Rojas Vega Mauricio", "rojas vega mauricio"),
        ("ROJAS  VEGA   MAURICIO", "rojas vega mauricio"),
        ("Pérez Gómez Ana María", "perez gomez ana maria"),
        ("  Núñez Muñoz José  ", "nunez munoz jose"),
    ],
)
def test_normalizar_quita_tildes_mayusculas_y_espacios(entrada, esperado):
    assert publicadores.normalizar(entrada) == esperado


def test_crear_guarda_el_nombre_normalizado(sesion):
    creado = publicadores.crear(sesion, "Pérez Gómez Ana María", sexo="M")

    assert creado.id is not None
    assert creado.nombre_completo == "Pérez Gómez Ana María"
    assert creado.nombre_normalizado == "perez gomez ana maria"


def test_buscar_por_nombre_ignora_tildes_y_mayusculas(sesion):
    creado = publicadores.crear(sesion, "Pérez Gómez Ana María")

    assert publicadores.buscar_por_nombre(sesion, "PEREZ GOMEZ ANA MARIA").id == creado.id


def test_buscar_por_nombre_devuelve_none_si_no_hay(sesion):
    assert publicadores.buscar_por_nombre(sesion, "Nadie Aqui") is None


def test_actualizar_recalcula_el_nombre_normalizado(sesion):
    creado = publicadores.crear(sesion, "Perez Ana")

    actualizado = publicadores.actualizar(
        sesion, creado.id, nombre_completo="Pérez Soto Ana"
    )

    assert actualizado.nombre_normalizado == "perez soto ana"


def test_listar_excluye_las_bajas_por_defecto(sesion):
    activo = publicadores.crear(sesion, "Activo Uno")
    baja = publicadores.crear(sesion, "Baja Dos")
    publicadores.dar_de_baja(sesion, baja.id, date(2026, 1, 15), "mudado")

    assert [p.id for p in publicadores.listar(sesion)] == [activo.id]
    assert len(publicadores.listar(sesion, incluir_bajas=True)) == 2


def test_listar_filtra_por_grupo(sesion):
    grupo = Grupo(nombre="Centro")
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    dentro = publicadores.crear(sesion, "Dentro Uno", grupo_id=grupo.id)
    publicadores.crear(sesion, "Fuera Dos")

    assert [p.id for p in publicadores.listar(sesion, grupo_id=grupo.id)] == [dentro.id]


def test_listar_busca_por_texto_sin_tildes(sesion):
    encontrado = publicadores.crear(sesion, "Núñez Muñoz José")
    publicadores.crear(sesion, "Otro Distinto")

    assert [p.id for p in publicadores.listar(sesion, texto="nunez")] == [encontrado.id]


def test_listar_ordena_alfabeticamente(sesion):
    publicadores.crear(sesion, "Zapata Luis")
    publicadores.crear(sesion, "Alvarez Ana")

    assert [p.nombre_completo for p in publicadores.listar(sesion)] == [
        "Alvarez Ana",
        "Zapata Luis",
    ]


def test_obtener_lanza_si_no_existe(sesion):
    with pytest.raises(publicadores.PublicadorNoEncontrado):
        publicadores.obtener(sesion, 999)
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `pytest tests/services/test_publicadores.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 4: Crear `app/services/publicadores.py`**

`app/services/__init__.py` y `tests/services/__init__.py` quedan vacíos.

```python
"""Alta, búsqueda y baja de publicadores."""

import unicodedata
from datetime import date

from sqlmodel import Session, select

from app.models import Publicador


class PublicadorNoEncontrado(Exception):
    pass


def normalizar(nombre: str) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados.

    Se usa solo para comparar nombres al importar; nunca se muestra en pantalla.
    """
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", nombre)
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def crear(sesion: Session, nombre_completo: str, **campos) -> Publicador:
    publicador = Publicador(
        nombre_completo=nombre_completo.strip(),
        nombre_normalizado=normalizar(nombre_completo),
        **campos,
    )
    sesion.add(publicador)
    sesion.commit()
    sesion.refresh(publicador)
    return publicador


def obtener(sesion: Session, publicador_id: int) -> Publicador:
    publicador = sesion.get(Publicador, publicador_id)
    if publicador is None:
        raise PublicadorNoEncontrado(f"no existe el publicador {publicador_id}")
    return publicador


def actualizar(sesion: Session, publicador_id: int, **campos) -> Publicador:
    publicador = obtener(sesion, publicador_id)
    for nombre, valor in campos.items():
        setattr(publicador, nombre, valor)
    if "nombre_completo" in campos:
        publicador.nombre_completo = campos["nombre_completo"].strip()
        publicador.nombre_normalizado = normalizar(campos["nombre_completo"])
    sesion.add(publicador)
    sesion.commit()
    sesion.refresh(publicador)
    return publicador


def buscar_por_nombre(sesion: Session, nombre: str) -> Publicador | None:
    consulta = select(Publicador).where(
        Publicador.nombre_normalizado == normalizar(nombre)
    )
    return sesion.exec(consulta).first()


def listar(
    sesion: Session,
    *,
    grupo_id: int | None = None,
    incluir_bajas: bool = False,
    texto: str | None = None,
) -> list[Publicador]:
    consulta = select(Publicador)
    if not incluir_bajas:
        consulta = consulta.where(Publicador.fecha_baja.is_(None))
    if grupo_id is not None:
        consulta = consulta.where(Publicador.grupo_id == grupo_id)
    if texto:
        consulta = consulta.where(
            Publicador.nombre_normalizado.contains(normalizar(texto))
        )
    consulta = consulta.order_by(Publicador.nombre_normalizado)
    return list(sesion.exec(consulta).all())


def dar_de_baja(
    sesion: Session, publicador_id: int, fecha: date, motivo: str
) -> Publicador:
    return actualizar(sesion, publicador_id, fecha_baja=fecha, motivo_baja=motivo)
```

En la tarea 16 este módulo gana además el filtro por privilegio. Se añade
entonces, no ahora.

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_publicadores.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services tests/services tests/conftest.py
git commit -m "feat: servicio de publicadores con normalización de nombres"
```

---

## Task 10: Servicio de nombramientos

**Files:**
- Create: `app/services/nombramientos.py`, `tests/services/test_nombramientos.py`

**Interfaces:**
- Consumes: `app.models.Nombramiento`, `app.dominio.rango_anio_servicio`, `app.dominio.TIPOS_NOMBRAMIENTO`
- Produces:
  - `app.services.nombramientos.ETIQUETAS: dict[str, str]`
  - `app.services.nombramientos.se_cruza(desde, hasta, inicio, fin) -> bool`
  - `app.services.nombramientos.crear(sesion, publicador_id, tipo, desde, hasta=None) -> Nombramiento`
  - `app.services.nombramientos.cerrar(sesion, nombramiento_id, hasta) -> Nombramiento`
  - `app.services.nombramientos.listar(sesion, publicador_id) -> list[Nombramiento]`
  - `app.services.nombramientos.tipos_en_anio(sesion, publicador_id, anio_servicio) -> set[str]`
  - `app.services.nombramientos.tipos_en_mes(sesion, publicador_id, anio, mes) -> set[str]`
  - `app.services.nombramientos.notas_sugeridas(sesion, publicador_id, anio_servicio) -> dict[int, str]` (clave: mes calendario)

- [ ] **Step 1: Escribir el test que falla**

`tests/services/test_nombramientos.py`:

```python
from datetime import date

import pytest

from app.services import nombramientos, publicadores


@pytest.fixture
def javier(sesion):
    return publicadores.crear(sesion, "Rojas Vega Mauricio")


def test_un_nombramiento_que_empieza_en_septiembre_marca_el_anio_siguiente(sesion, javier):
    nombramientos.crear(sesion, javier.id, "precursor_regular", date(2025, 9, 1))

    assert nombramientos.tipos_en_anio(sesion, javier.id, 2025) == set()
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2026) == {"precursor_regular"}


def test_un_nombramiento_cerrado_el_31_de_agosto_marca_ese_anio_y_no_el_siguiente(
    sesion, javier
):
    nombramientos.crear(
        sesion, javier.id, "anciano", date(2020, 1, 1), hasta=date(2025, 8, 31)
    )

    assert nombramientos.tipos_en_anio(sesion, javier.id, 2025) == {"anciano"}
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2026) == set()


def test_un_nombramiento_a_caballo_marca_los_dos_anios(sesion, javier):
    nombramientos.crear(
        sesion, javier.id, "precursor_regular", date(2025, 7, 15), hasta=date(2025, 9, 20)
    )

    assert nombramientos.tipos_en_anio(sesion, javier.id, 2025) == {"precursor_regular"}
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2026) == {"precursor_regular"}


def test_un_nombramiento_vigente_marca_todos_los_anios_desde_su_inicio(sesion, javier):
    nombramientos.crear(sesion, javier.id, "siervo_ministerial", date(2025, 7, 1))

    assert nombramientos.tipos_en_anio(sesion, javier.id, 2024) == set()
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2025) == {"siervo_ministerial"}
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2030) == {"siervo_ministerial"}


def test_tipos_en_mes_usa_el_mes_completo(sesion, javier):
    # termina el 5 de marzo: marzo sigue contando, abril ya no
    nombramientos.crear(
        sesion, javier.id, "precursor_regular", date(2026, 1, 1), hasta=date(2026, 3, 5)
    )

    assert nombramientos.tipos_en_mes(sesion, javier.id, 2026, 3) == {"precursor_regular"}
    assert nombramientos.tipos_en_mes(sesion, javier.id, 2026, 4) == set()


def test_nota_sugerida_al_ser_nombrado(sesion, javier):
    nombramientos.crear(sesion, javier.id, "siervo_ministerial", date(2025, 7, 10))

    assert nombramientos.notas_sugeridas(sesion, javier.id, 2025) == {
        7: "nombrado siervo ministerial"
    }


def test_nota_sugerida_al_dejar_el_privilegio(sesion, javier):
    nombramientos.crear(
        sesion, javier.id, "precursor_regular", date(2024, 1, 1), hasta=date(2026, 2, 28)
    )

    assert nombramientos.notas_sugeridas(sesion, javier.id, 2026) == {
        2: "deja de ser precursor regular"
    }


def test_no_sugiere_nada_fuera_del_anio_de_servicio(sesion, javier):
    nombramientos.crear(sesion, javier.id, "anciano", date(2020, 3, 1))

    assert nombramientos.notas_sugeridas(sesion, javier.id, 2026) == {}


def test_dos_cambios_en_el_mismo_mes_se_unen(sesion, javier):
    nombramientos.crear(
        sesion, javier.id, "precursor_regular", date(2024, 1, 1), hasta=date(2026, 5, 31)
    )
    nombramientos.crear(sesion, javier.id, "siervo_ministerial", date(2026, 5, 12))

    sugeridas = nombramientos.notas_sugeridas(sesion, javier.id, 2026)

    assert sugeridas[5] == (
        "deja de ser precursor regular · nombrado siervo ministerial"
    )


def test_cerrar_pone_la_fecha_de_termino(sesion, javier):
    creado = nombramientos.crear(sesion, javier.id, "anciano", date(2020, 1, 1))

    cerrado = nombramientos.cerrar(sesion, creado.id, date(2026, 4, 30))

    assert cerrado.hasta == date(2026, 4, 30)


def test_crear_rechaza_un_tipo_desconocido(sesion, javier):
    with pytest.raises(ValueError):
        nombramientos.crear(sesion, javier.id, "capitan", date(2026, 1, 1))


def test_crear_rechaza_un_rango_invertido(sesion, javier):
    with pytest.raises(ValueError):
        nombramientos.crear(
            sesion, javier.id, "anciano", date(2026, 5, 1), hasta=date(2026, 4, 1)
        )
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_nombramientos.py -v`
Expected: FAIL con `ImportError: cannot import name 'nombramientos'`

- [ ] **Step 3: Crear `app/services/nombramientos.py`**

```python
"""Vigencia de los privilegios y notas sugeridas por cambio de privilegio."""

from calendar import monthrange
from datetime import date

from sqlmodel import Session, select

from app.dominio import TIPOS_NOMBRAMIENTO, rango_anio_servicio
from app.models import Nombramiento

ETIQUETAS = {
    "anciano": "anciano",
    "siervo_ministerial": "siervo ministerial",
    "precursor_regular": "precursor regular",
    "precursor_especial": "precursor especial",
    "misionero_campo": "misionero que sirve en el campo",
}

FIN_ABIERTO = date(9999, 12, 31)


def se_cruza(desde: date, hasta: date | None, inicio: date, fin: date) -> bool:
    """¿El intervalo [desde, hasta] toca [inicio, fin] aunque sea un día?"""
    return desde <= fin and (hasta or FIN_ABIERTO) >= inicio


def crear(
    sesion: Session,
    publicador_id: int,
    tipo: str,
    desde: date,
    hasta: date | None = None,
) -> Nombramiento:
    if tipo not in TIPOS_NOMBRAMIENTO:
        raise ValueError(f"tipo de nombramiento desconocido: {tipo}")
    if hasta is not None and hasta < desde:
        raise ValueError("la fecha de término es anterior a la de inicio")
    nombramiento = Nombramiento(
        publicador_id=publicador_id, tipo=tipo, desde=desde, hasta=hasta
    )
    sesion.add(nombramiento)
    sesion.commit()
    sesion.refresh(nombramiento)
    return nombramiento


def cerrar(sesion: Session, nombramiento_id: int, hasta: date) -> Nombramiento:
    nombramiento = sesion.get(Nombramiento, nombramiento_id)
    if nombramiento is None:
        raise ValueError(f"no existe el nombramiento {nombramiento_id}")
    if hasta < nombramiento.desde:
        raise ValueError("la fecha de término es anterior a la de inicio")
    nombramiento.hasta = hasta
    sesion.add(nombramiento)
    sesion.commit()
    sesion.refresh(nombramiento)
    return nombramiento


def listar(sesion: Session, publicador_id: int) -> list[Nombramiento]:
    consulta = (
        select(Nombramiento)
        .where(Nombramiento.publicador_id == publicador_id)
        .order_by(Nombramiento.desde)
    )
    return list(sesion.exec(consulta).all())


def _tipos_en_rango(
    sesion: Session, publicador_id: int, inicio: date, fin: date
) -> set[str]:
    return {
        nombramiento.tipo
        for nombramiento in listar(sesion, publicador_id)
        if se_cruza(nombramiento.desde, nombramiento.hasta, inicio, fin)
    }


def tipos_en_anio(sesion: Session, publicador_id: int, anio_servicio: int) -> set[str]:
    """Privilegios que marcan la casilla de la tarjeta del año de servicio.

    Basta que el nombramiento haya estado vigente un solo mes del año.
    """
    inicio, fin = rango_anio_servicio(anio_servicio)
    return _tipos_en_rango(sesion, publicador_id, inicio, fin)


def tipos_en_mes(sesion: Session, publicador_id: int, anio: int, mes: int) -> set[str]:
    inicio = date(anio, mes, 1)
    fin = date(anio, mes, monthrange(anio, mes)[1])
    return _tipos_en_rango(sesion, publicador_id, inicio, fin)


def notas_sugeridas(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> dict[int, str]:
    """Texto propuesto para el mes en que un privilegio empieza o termina."""
    inicio, fin = rango_anio_servicio(anio_servicio)
    por_mes: dict[tuple[int, int], list[str]] = {}

    for nombramiento in listar(sesion, publicador_id):
        etiqueta = ETIQUETAS[nombramiento.tipo]
        if inicio <= nombramiento.desde <= fin:
            clave = (nombramiento.desde.year, nombramiento.desde.month)
            por_mes.setdefault(clave, []).append(f"nombrado {etiqueta}")
        if nombramiento.hasta is not None and inicio <= nombramiento.hasta <= fin:
            clave = (nombramiento.hasta.year, nombramiento.hasta.month)
            por_mes.setdefault(clave, []).append(f"deja de ser {etiqueta}")

    return {
        mes: " · ".join(textos) for (_anio, mes), textos in sorted(por_mes.items())
    }
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_nombramientos.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/nombramientos.py tests/services/test_nombramientos.py
git commit -m "feat: vigencia de nombramientos y notas de cambio de privilegio"
```

---

## Task 11: Servicio de registros mensuales y armado de la tarjeta

**Files:**
- Create: `app/services/registros.py`, `tests/services/test_registros.py`

**Interfaces:**
- Consumes: `app.models.RegistroMensual`, `app.services.publicadores`, `app.services.nombramientos`, `app.dominio`
- Produces:
  - `app.services.registros.EntradaMes` (dataclass: `publicador_id`, `participo`, `cursos_biblicos`, `precursor_auxiliar`, `horas`, `notas`)
  - `app.services.registros.guardar_mes(sesion, anio, mes, entradas: list[EntradaMes]) -> int` (devuelve cuántas filas quedaron guardadas)
  - `app.services.registros.filas_del_mes(sesion, anio, mes, *, grupo_id=None) -> list[tuple[Publicador, RegistroMensual | None, bool]]` (el bool indica si las horas están habilitadas)
  - `app.services.registros.registros_del_anio(sesion, publicador_id, anio_servicio) -> dict[int, RegistroMensual]`
  - `app.services.registros.tarjeta(sesion, publicador_id, anio_servicio) -> DatosTarjeta`
  - `app.services.registros.aplicar_notas_sugeridas(sesion, publicador_id, anio_servicio) -> int`

- [ ] **Step 1: Escribir el test que falla**

`tests/services/test_registros.py`:

```python
from datetime import date

from app.services import nombramientos, publicadores, registros


def _ana(sesion):
    return publicadores.crear(
        sesion,
        "Pérez Gómez Ana María",
        sexo="M",
        esperanza="otras_ovejas",
        fecha_bautismo=date(2010, 4, 3),
    )


def test_guardar_mes_crea_las_filas(sesion):
    ana = _ana(sesion)

    guardadas = registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)],
    )

    assert guardadas == 1
    assert registros.registros_del_anio(sesion, ana.id, 2026)[9].horas == 52


def test_guardar_mes_actualiza_en_vez_de_duplicar(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, horas=52)]
    )

    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, horas=60)]
    )

    del_anio = registros.registros_del_anio(sesion, ana.id, 2026)
    assert len(del_anio) == 1
    assert del_anio[9].horas == 60


def test_filas_del_mes_incluye_a_quien_no_tiene_registro(sesion):
    ana = _ana(sesion)

    filas = registros.filas_del_mes(sesion, 2025, 9)

    assert len(filas) == 1
    publicador, registro, horas_habilitadas = filas[0]
    assert publicador.id == ana.id
    assert registro is None
    assert horas_habilitadas is False


def test_las_horas_se_habilitan_para_un_precursor_regular(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 9, 1))

    _publicador, _registro, horas_habilitadas = registros.filas_del_mes(sesion, 2025, 9)[0]

    assert horas_habilitadas is True


def test_las_horas_se_habilitan_si_ese_mes_fue_precursor_auxiliar(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, precursor_auxiliar=True)],
    )

    _publicador, _registro, horas_habilitadas = registros.filas_del_mes(sesion, 2025, 9)[0]

    assert horas_habilitadas is True


def test_tarjeta_reune_cabecera_nombramientos_y_meses(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 1))
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, cursos_biblicos=2)],
    )
    registros.guardar_mes(
        sesion,
        2025,
        10,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)],
    )

    tarjeta = registros.tarjeta(sesion, ana.id, 2026)

    assert tarjeta.nombre == "Pérez Gómez Ana María"
    assert tarjeta.anio_servicio == 2026
    assert tarjeta.sexo == "M"
    assert tarjeta.fecha_bautismo == date(2010, 4, 3)
    assert tarjeta.nombramientos == {"precursor_regular"}
    assert tarjeta.mes(9).cursos_biblicos == 2
    assert tarjeta.mes(10).horas == 52
    assert tarjeta.mes(1).participo is False
    assert tarjeta.total_horas() == 52


def test_aplicar_notas_sugeridas_llena_solo_las_notas_vacias(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 5))
    nombramientos.crear(sesion, ana.id, "siervo_ministerial", date(2026, 3, 1))
    registros.guardar_mes(
        sesion,
        2026,
        3,
        [registros.EntradaMes(publicador_id=ana.id, notas="ya escrito a mano")],
    )

    escritas = registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)

    del_anio = registros.registros_del_anio(sesion, ana.id, 2026)
    assert escritas == 1
    assert del_anio[10].notas == "nombrado precursor regular"
    assert del_anio[3].notas == "ya escrito a mano"


def test_aplicar_notas_sugeridas_es_idempotente(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 5))

    registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)
    segunda = registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)

    assert segunda == 0
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_registros.py -v`
Expected: FAIL con `ImportError: cannot import name 'registros'`

- [ ] **Step 3: Crear `app/services/registros.py`**

```python
"""Carga de los informes mensuales y armado de la tarjeta de un año."""

from dataclasses import dataclass

from sqlmodel import Session, select

from app.dominio import DatosTarjeta, FilaMes, TIPOS_CON_HORAS, meses_del_anio
from app.models import Publicador, RegistroMensual
from app.services import nombramientos, publicadores


@dataclass
class EntradaMes:
    publicador_id: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


def _registro(
    sesion: Session, publicador_id: int, anio: int, mes: int
) -> RegistroMensual | None:
    consulta = select(RegistroMensual).where(
        RegistroMensual.publicador_id == publicador_id,
        RegistroMensual.anio == anio,
        RegistroMensual.mes == mes,
    )
    return sesion.exec(consulta).first()


def guardar_mes(
    sesion: Session, anio: int, mes: int, entradas: list[EntradaMes]
) -> int:
    """Crea o actualiza la fila de cada publicador para ese mes calendario."""
    for entrada in entradas:
        fila = _registro(sesion, entrada.publicador_id, anio, mes) or RegistroMensual(
            publicador_id=entrada.publicador_id, anio=anio, mes=mes
        )
        fila.participo = entrada.participo
        fila.cursos_biblicos = entrada.cursos_biblicos
        fila.precursor_auxiliar = entrada.precursor_auxiliar
        fila.horas = entrada.horas
        fila.notas = entrada.notas
        sesion.add(fila)
    sesion.commit()
    return len(entradas)


def filas_del_mes(
    sesion: Session, anio: int, mes: int, *, grupo_id: int | None = None
) -> list[tuple[Publicador, RegistroMensual | None, bool]]:
    """Una fila por publicador activo, con su registro del mes si existe.

    El tercer elemento indica si el campo de horas corresponde: hay nombramiento
    de precursor o misionero vigente ese mes, o la fila está marcada como
    precursor auxiliar.
    """
    filas = []
    for publicador in publicadores.listar(sesion, grupo_id=grupo_id):
        registro = _registro(sesion, publicador.id, anio, mes)
        tipos = nombramientos.tipos_en_mes(sesion, publicador.id, anio, mes)
        con_horas = bool(tipos & set(TIPOS_CON_HORAS)) or bool(
            registro and registro.precursor_auxiliar
        )
        filas.append((publicador, registro, con_horas))
    return filas


def registros_del_anio(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> dict[int, RegistroMensual]:
    """Registros del año de servicio, indexados por mes calendario."""
    encontrados = {}
    for anio, mes in meses_del_anio(anio_servicio):
        fila = _registro(sesion, publicador_id, anio, mes)
        if fila is not None:
            encontrados[mes] = fila
    return encontrados


def tarjeta(sesion: Session, publicador_id: int, anio_servicio: int) -> DatosTarjeta:
    publicador = publicadores.obtener(sesion, publicador_id)
    del_anio = registros_del_anio(sesion, publicador_id, anio_servicio)

    datos = DatosTarjeta.vacia(publicador.nombre_completo, anio_servicio)
    datos.fecha_nacimiento = publicador.fecha_nacimiento
    datos.fecha_bautismo = publicador.fecha_bautismo
    datos.sexo = publicador.sexo
    datos.esperanza = publicador.esperanza
    datos.nombramientos = nombramientos.tipos_en_anio(
        sesion, publicador_id, anio_servicio
    )

    for fila in datos.meses:
        registro = del_anio.get(fila.mes)
        if registro is None:
            continue
        fila.participo = registro.participo
        fila.cursos_biblicos = registro.cursos_biblicos
        fila.precursor_auxiliar = registro.precursor_auxiliar
        fila.horas = registro.horas
        fila.notas = registro.notas

    return datos


def aplicar_notas_sugeridas(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> int:
    """Escribe la nota de cambio de privilegio donde la nota esté vacía.

    Nunca pisa un texto escrito por el usuario. Devuelve cuántas notas escribió.
    """
    sugeridas = nombramientos.notas_sugeridas(sesion, publicador_id, anio_servicio)
    escritas = 0
    for anio, mes in meses_del_anio(anio_servicio):
        propuesta = sugeridas.get(mes)
        if not propuesta:
            continue
        fila = _registro(sesion, publicador_id, anio, mes) or RegistroMensual(
            publicador_id=publicador_id, anio=anio, mes=mes
        )
        if (fila.notas or "").strip():
            continue
        fila.notas = propuesta
        sesion.add(fila)
        escritas += 1
    sesion.commit()
    return escritas
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_registros.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/registros.py tests/services/test_registros.py
git commit -m "feat: carga de registros mensuales y armado de la tarjeta del año"
```

---

## Task 12: Informe mensual y anual

**Files:**
- Create: `app/services/informe.py`, `tests/services/test_informe.py`

**Interfaces:**
- Consumes: `app.services.publicadores`, `app.services.nombramientos`, `app.services.registros`, `app.dominio.meses_del_anio`
- Produces:
  - `app.services.informe.CATEGORIAS: tuple[tuple[str, str, bool], ...]` (clave, etiqueta, lleva horas), en orden de presentación
  - `app.services.informe.categoria_de(tipos: set[str], precursor_auxiliar: bool) -> str`
  - `app.services.informe.FilaInforme` (dataclass: `clave`, `etiqueta`, `informaron`, `cursos`, `horas: int | None`)
  - `app.services.informe.InformeMensual` (dataclass: `anio`, `mes`, `filas`, `total_informaron`, `total_cursos`, `total_horas`, `no_informaron`, `promedio_horas_precursor_regular`)
  - `app.services.informe.informe_mensual(sesion, anio, mes) -> InformeMensual`
  - `app.services.informe.informe_anual(sesion, anio_servicio) -> list[InformeMensual]`

- [ ] **Step 1: Escribir el test que falla**

`tests/services/test_informe.py`:

```python
from datetime import date

import pytest

from app.services import informe, nombramientos, publicadores, registros


@pytest.mark.parametrize(
    "tipos,auxiliar,esperado",
    [
        (set(), False, "publicador"),
        (set(), True, "precursor_auxiliar"),
        ({"precursor_regular"}, False, "precursor_regular"),
        # el regular que además fue auxiliar cuenta una sola vez, como regular
        ({"precursor_regular"}, True, "precursor_regular"),
        ({"precursor_especial", "precursor_regular"}, True, "precursor_especial"),
        ({"misionero_campo", "precursor_especial"}, True, "misionero_campo"),
        # anciano y siervo ministerial no son categorías de informe
        ({"anciano"}, False, "publicador"),
        ({"siervo_ministerial"}, True, "precursor_auxiliar"),
    ],
)
def test_precedencia_de_categorias(tipos, auxiliar, esperado):
    assert informe.categoria_de(tipos, auxiliar) == esperado


def test_informe_cuenta_solo_a_quienes_informaron(sesion):
    informo = publicadores.crear(sesion, "Informo Uno")
    callado = publicadores.crear(sesion, "Callado Dos")
    registros.guardar_mes(
        sesion,
        2026,
        1,
        [
            registros.EntradaMes(publicador_id=informo.id, participo=True, cursos_biblicos=3),
            registros.EntradaMes(publicador_id=callado.id, participo=False),
        ],
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 1
    assert resultado.no_informaron == 1
    assert resultado.total_cursos == 3


def test_un_mes_sin_fila_cuenta_como_no_informado(sesion):
    publicadores.crear(sesion, "Sin Fila")

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 0
    assert resultado.no_informaron == 1


def test_las_bajas_no_entran_en_el_informe(sesion):
    baja = publicadores.crear(sesion, "Baja Uno")
    publicadores.dar_de_baja(sesion, baja.id, date(2025, 12, 1), "mudado")

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 0
    assert resultado.no_informaron == 0


def test_la_fila_de_publicadores_no_lleva_horas(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    registros.guardar_mes(
        sesion, 2026, 1, [registros.EntradaMes(publicador_id=ana.id, participo=True)]
    )

    fila = next(f for f in informe.informe_mensual(sesion, 2026, 1).filas if f.clave == "publicador")

    assert fila.informaron == 1
    assert fila.horas is None


def test_suma_horas_por_categoria_y_promedio_de_regulares(sesion):
    regular_uno = publicadores.crear(sesion, "Regular Uno")
    regular_dos = publicadores.crear(sesion, "Regular Dos")
    auxiliar = publicadores.crear(sesion, "Auxiliar Tres")
    nombramientos.crear(sesion, regular_uno.id, "precursor_regular", date(2025, 9, 1))
    nombramientos.crear(sesion, regular_dos.id, "precursor_regular", date(2025, 9, 1))
    registros.guardar_mes(
        sesion,
        2026,
        1,
        [
            registros.EntradaMes(publicador_id=regular_uno.id, participo=True, horas=70),
            registros.EntradaMes(publicador_id=regular_dos.id, participo=True, horas=64),
            registros.EntradaMes(
                publicador_id=auxiliar.id, participo=True, precursor_auxiliar=True, horas=30
            ),
        ],
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)
    por_clave = {fila.clave: fila for fila in resultado.filas}

    assert por_clave["precursor_regular"].informaron == 2
    assert por_clave["precursor_regular"].horas == 134
    assert por_clave["precursor_auxiliar"].horas == 30
    assert resultado.total_horas == 164
    assert resultado.promedio_horas_precursor_regular == 67


def test_promedio_es_none_sin_precursores_regulares(sesion):
    assert informe.informe_mensual(sesion, 2026, 1).promedio_horas_precursor_regular is None


def test_las_filas_salen_siempre_en_el_mismo_orden(sesion):
    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert [fila.clave for fila in resultado.filas] == [
        "publicador",
        "precursor_auxiliar",
        "precursor_regular",
        "precursor_especial",
        "misionero_campo",
    ]


def test_informe_anual_trae_doce_meses_de_septiembre_a_agosto(sesion):
    anual = informe.informe_anual(sesion, 2026)

    assert len(anual) == 12
    assert (anual[0].anio, anual[0].mes) == (2025, 9)
    assert (anual[-1].anio, anual[-1].mes) == (2026, 8)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_informe.py -v`
Expected: FAIL con `ImportError: cannot import name 'informe'`

- [ ] **Step 3: Crear `app/services/informe.py`**

```python
"""Agregados del mes y del año de servicio, al estilo del informe S-1."""

from dataclasses import dataclass

from app.dominio import meses_del_anio
from app.services import nombramientos, registros

# clave, etiqueta, lleva columna de horas. El orden es el de presentación.
CATEGORIAS = (
    ("publicador", "Publicadores", False),
    ("precursor_auxiliar", "Precursores auxiliares", True),
    ("precursor_regular", "Precursores regulares", True),
    ("precursor_especial", "Precursores especiales", True),
    ("misionero_campo", "Misioneros en el campo", True),
)

# de mayor a menor prioridad: cada publicador cuenta en una sola categoría
PRECEDENCIA = (
    "misionero_campo",
    "precursor_especial",
    "precursor_regular",
    "precursor_auxiliar",
)


def categoria_de(tipos: set[str], precursor_auxiliar: bool) -> str:
    for clave in PRECEDENCIA:
        if clave == "precursor_auxiliar":
            if precursor_auxiliar:
                return clave
        elif clave in tipos:
            return clave
    return "publicador"


@dataclass
class FilaInforme:
    clave: str
    etiqueta: str
    informaron: int = 0
    cursos: int = 0
    horas: int | None = None


@dataclass
class InformeMensual:
    anio: int
    mes: int
    filas: list[FilaInforme]
    total_informaron: int
    total_cursos: int
    total_horas: int
    no_informaron: int
    promedio_horas_precursor_regular: int | None


def informe_mensual(sesion, anio: int, mes: int) -> InformeMensual:
    filas = {
        clave: FilaInforme(clave, etiqueta, horas=0 if lleva_horas else None)
        for clave, etiqueta, lleva_horas in CATEGORIAS
    }

    del_mes = registros.filas_del_mes(sesion, anio, mes)
    informaron = 0
    for publicador, registro, _habilitadas in del_mes:
        if registro is None or not registro.participo:
            continue
        informaron += 1
        tipos = nombramientos.tipos_en_mes(sesion, publicador.id, anio, mes)
        destino = filas[categoria_de(tipos, registro.precursor_auxiliar)]
        destino.informaron += 1
        destino.cursos += registro.cursos_biblicos or 0
        if destino.horas is not None:
            destino.horas += registro.horas or 0

    regulares = filas["precursor_regular"]
    promedio = (
        round((regulares.horas or 0) / regulares.informaron)
        if regulares.informaron
        else None
    )

    ordenadas = [filas[clave] for clave, _etiqueta, _horas in CATEGORIAS]
    return InformeMensual(
        anio=anio,
        mes=mes,
        filas=ordenadas,
        total_informaron=informaron,
        total_cursos=sum(fila.cursos for fila in ordenadas),
        total_horas=sum(fila.horas or 0 for fila in ordenadas),
        no_informaron=len(del_mes) - informaron,
        promedio_horas_precursor_regular=promedio,
    )


def informe_anual(sesion, anio_servicio: int) -> list[InformeMensual]:
    return [informe_mensual(sesion, anio, mes) for anio, mes in meses_del_anio(anio_servicio)]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_informe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/informe.py tests/services/test_informe.py
git commit -m "feat: informe mensual y anual con precedencia de categorías"
```

---

## Task 13: Alertas de irregulares e inactivos

**Files:**
- Create: `app/services/alertas.py`, `tests/services/test_alertas.py`

**Interfaces:**
- Consumes: `app.services.publicadores`, `app.models.RegistroMensual`
- Produces:
  - `app.services.alertas.MESES_VENTANA = 6`
  - `app.services.alertas.ventana(hoy: date) -> list[tuple[int, int]]`
  - `app.services.alertas.Alerta` (dataclass: `publicador`, `estado`, `meses_sin_informar: list[tuple[int, int]]`)
  - `app.services.alertas.calcular(sesion, hoy: date) -> list[Alerta]`

- [ ] **Step 1: Escribir el test que falla**

`tests/services/test_alertas.py`:

```python
from datetime import date

from app.services import alertas, publicadores, registros


def test_la_ventana_son_los_seis_meses_completos_anteriores():
    assert alertas.ventana(date(2026, 3, 15)) == [
        (2025, 9),
        (2025, 10),
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    ]


def test_la_ventana_cruza_bien_el_cambio_de_anio():
    assert alertas.ventana(date(2026, 1, 5))[0] == (2025, 7)
    assert alertas.ventana(date(2026, 1, 5))[-1] == (2025, 12)


def _informar(sesion, publicador_id, meses):
    for anio, mes in meses:
        registros.guardar_mes(
            sesion,
            anio,
            mes,
            [registros.EntradaMes(publicador_id=publicador_id, participo=True)],
        )


def test_quien_informo_los_seis_meses_no_genera_alerta(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15)))

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []


def test_quien_falto_un_mes_es_irregular(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15))[:-1])

    resultado = alertas.calcular(sesion, date(2026, 3, 15))

    assert len(resultado) == 1
    assert resultado[0].estado == "irregular"
    assert resultado[0].meses_sin_informar == [(2026, 2)]


def test_quien_no_informo_ninguno_de_los_seis_es_inactivo(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")

    resultado = alertas.calcular(sesion, date(2026, 3, 15))

    assert resultado[0].estado == "inactivo"
    assert len(resultado[0].meses_sin_informar) == 6


def test_una_fila_con_participo_false_cuenta_como_no_informado(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    for anio, mes in alertas.ventana(date(2026, 3, 15)):
        registros.guardar_mes(
            sesion,
            anio,
            mes,
            [registros.EntradaMes(publicador_id=ana.id, participo=False)],
        )

    assert alertas.calcular(sesion, date(2026, 3, 15))[0].estado == "inactivo"


def test_informar_solo_el_mes_mas_antiguo_deja_irregular_no_inactivo(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15))[:1])

    assert alertas.calcular(sesion, date(2026, 3, 15))[0].estado == "irregular"


def test_el_mes_en_curso_no_entra_en_la_ventana(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15)))
    # informar marzo no cambia nada: marzo aún no termina
    _informar(sesion, ana.id, [(2026, 3)])

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []


def test_las_bajas_no_generan_alertas(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    publicadores.dar_de_baja(sesion, ana.id, date(2026, 1, 10), "mudado")

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_alertas.py -v`
Expected: FAIL con `ImportError: cannot import name 'alertas'`

- [ ] **Step 3: Crear `app/services/alertas.py`**

```python
"""Detección de publicadores irregulares e inactivos."""

from dataclasses import dataclass
from datetime import date

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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_alertas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/alertas.py tests/services/test_alertas.py
git commit -m "feat: alertas de publicadores irregulares e inactivos"
```

---

## Task 14: Servicio de importación con revisión y deshacer

**Files:**
- Create: `app/services/importacion.py`, `tests/services/test_importacion.py`

**Interfaces:**
- Consumes: `app.pdf.importar.leer_tarjeta`, `app.services.publicadores`, `app.services.nombramientos`, `app.services.registros`, `app.models.Importacion`, `app.dominio`
- Produces:
  - `app.services.importacion.Diferencia` (dataclass: `campo`, `etiqueta`, `valor_actual`, `valor_tarjeta`)
  - `app.services.importacion.NombramientoPropuesto` (dataclass: `tipo`, `desde`)
  - `app.services.importacion.Propuesta` (dataclass: `archivo`, `sha256`, `datos`, `publicador_id`, `diferencias`, `nombramientos`, `meses_en_conflicto`, `ya_importado`)
  - `app.services.importacion.Decision` (dataclass: `propuesta`, `publicador_id`, `aceptar_campos`, `aceptar_nombramientos`, `aceptar_meses`)
  - `app.services.importacion.analizar(sesion, archivo: str, contenido: bytes) -> Propuesta`
  - `app.services.importacion.aplicar(sesion, decision: Decision, lote: str, ahora: datetime) -> Importacion`
  - `app.services.importacion.deshacer(sesion, lote: str) -> int`
  - `app.services.importacion.historial(sesion) -> list[tuple[str, datetime, int]]` (lote, fecha, cantidad de archivos)

- [ ] **Step 1: Escribir el test que falla**

`tests/services/test_importacion.py`:

```python
from datetime import date, datetime
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.pdf import campos
from app.services import importacion, nombramientos, publicadores, registros

AHORA = datetime(2026, 9, 9, 12, 0, 0)


def _pdf(ruta, valores: dict[str, str]) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(escritor.pages[0], valores, auto_regenerate=False)
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def tarjeta_mauricio(plantilla_sintetica):
    return _pdf(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["fecha_nacimiento"]: "14.03.1985",
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025",
            campos.CABECERA_SEXO["H"]: campos.MARCADA,
            campos.CABECERA_ESPERANZA["otras_ovejas"]: campos.MARCADA,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("precursor_auxiliar", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
    )


def _decision_total(propuesta, publicador_id=None):
    return importacion.Decision(
        propuesta=propuesta,
        publicador_id=publicador_id if publicador_id is not None else propuesta.publicador_id,
        aceptar_campos={d.campo for d in propuesta.diferencias},
        aceptar_nombramientos=list(propuesta.nombramientos),
        aceptar_meses={fila.mes for fila in propuesta.datos.meses},
    )


def test_analizar_no_escribe_nada_en_la_base(sesion, tarjeta_mauricio):
    importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert publicadores.listar(sesion) == []


def test_analizar_encuentra_al_publicador_existente(sesion, tarjeta_mauricio):
    existente = publicadores.crear(sesion, "MAURICIO ANDRÉS ROJAS VEGA")

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.publicador_id == existente.id


def test_analizar_propone_crear_si_no_hay_coincidencia(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.publicador_id is None
    assert propuesta.datos.nombre == "Mauricio Andrés Rojas Vega"


def test_diferencias_solo_lista_los_campos_que_cambian(sesion, tarjeta_mauricio):
    publicadores.crear(
        sesion,
        "Mauricio Andrés Rojas Vega",
        sexo="H",
        fecha_bautismo=date(2002, 6, 7),
    )

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    campos_distintos = {d.campo for d in propuesta.diferencias}
    assert "fecha_nacimiento" in campos_distintos
    assert "sexo" not in campos_distintos
    assert "fecha_bautismo" not in campos_distintos


def test_propone_el_nombramiento_desde_el_inicio_del_anio_de_servicio(
    sesion, tarjeta_mauricio
):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.nombramientos == [
        importacion.NombramientoPropuesto("siervo_ministerial", date(2024, 9, 1))
    ]


def test_no_propone_un_nombramiento_que_ya_existe(sesion, tarjeta_mauricio):
    javier = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    nombramientos.crear(sesion, javier.id, "siervo_ministerial", date(2024, 7, 1))

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.nombramientos == []


def test_marca_los_meses_que_pisarian_un_valor_distinto(sesion, tarjeta_mauricio):
    javier = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=javier.id, horas=99)]
    )

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.meses_en_conflicto == [9]


def test_avisa_si_el_archivo_ya_se_importo(sesion, tarjeta_mauricio):
    primera = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(primera), lote="L1", ahora=AHORA)

    segunda = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert segunda.ya_importado == AHORA


def test_aplicar_crea_publicador_nombramientos_y_registros(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    javier = publicadores.buscar_por_nombre(sesion, "Mauricio Andrés Rojas Vega")
    assert javier is not None
    assert javier.fecha_bautismo == date(2002, 6, 7)
    assert nombramientos.tipos_en_anio(sesion, javier.id, 2025) == {"siervo_ministerial"}
    del_anio = registros.registros_del_anio(sesion, javier.id, 2025)
    assert del_anio[9].horas == 15
    assert del_anio[9].precursor_auxiliar is True


def test_aplicar_respeta_los_campos_no_aceptados(sesion, tarjeta_mauricio):
    javier = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    decision = importacion.Decision(
        propuesta=propuesta,
        publicador_id=javier.id,
        aceptar_campos={"fecha_bautismo"},
        aceptar_nombramientos=[],
        aceptar_meses=set(),
    )

    importacion.aplicar(sesion, decision, lote="L1", ahora=AHORA)

    actualizado = publicadores.obtener(sesion, javier.id)
    assert actualizado.fecha_bautismo == date(2002, 6, 7)
    assert actualizado.fecha_nacimiento is None


def test_aplicar_solo_escribe_los_meses_aceptados(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    decision = importacion.Decision(
        propuesta=propuesta,
        publicador_id=None,
        aceptar_campos=set(),
        aceptar_nombramientos=[],
        aceptar_meses={10},
    )

    importacion.aplicar(sesion, decision, lote="L1", ahora=AHORA)

    javier = publicadores.buscar_por_nombre(sesion, "Mauricio Andrés Rojas Vega")
    assert registros.registros_del_anio(sesion, javier.id, 2025).keys() == {10}


def test_deshacer_borra_el_publicador_creado_por_el_lote(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    deshechos = importacion.deshacer(sesion, "L1")

    assert deshechos == 1
    assert publicadores.listar(sesion) == []


def test_deshacer_devuelve_los_registros_a_su_valor_anterior(sesion, tarjeta_mauricio):
    javier = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=javier.id, horas=99)]
    )
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta, javier.id), lote="L1", ahora=AHORA)
    assert registros.registros_del_anio(sesion, javier.id, 2025)[9].horas == 15

    importacion.deshacer(sesion, "L1")

    assert publicadores.obtener(sesion, javier.id) is not None
    assert registros.registros_del_anio(sesion, javier.id, 2025)[9].horas == 99


def test_deshacer_dos_veces_no_hace_nada_la_segunda(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    importacion.deshacer(sesion, "L1")

    assert importacion.deshacer(sesion, "L1") == 0


def test_historial_agrupa_por_lote(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    assert importacion.historial(sesion) == [("L1", AHORA, 1)]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_importacion.py -v`
Expected: FAIL con `ImportError: cannot import name 'importacion'`

- [ ] **Step 3: Crear `app/services/importacion.py`**

```python
"""Comparación de una tarjeta contra la base, aplicación y deshacer.

`analizar` no escribe nada: devuelve una propuesta que la pantalla de revisión
muestra al usuario. Solo `aplicar` toca la base, y guarda el estado anterior de
todo lo que modifica para que `deshacer` pueda restaurarlo con exactitud.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlmodel import Session, select

from app.dominio import DatosTarjeta, rango_anio_servicio
from app.models import Importacion, Nombramiento, Publicador, RegistroMensual
from app.pdf.importar import leer_tarjeta
from app.services import nombramientos, publicadores, registros

CAMPOS_CABECERA = (
    ("fecha_nacimiento", "Fecha de nacimiento"),
    ("fecha_bautismo", "Fecha de bautismo"),
    ("sexo", "Sexo"),
    ("esperanza", "Esperanza"),
)


@dataclass
class Diferencia:
    campo: str
    etiqueta: str
    valor_actual: object
    valor_tarjeta: object


@dataclass(frozen=True)
class NombramientoPropuesto:
    tipo: str
    desde: date


@dataclass
class Propuesta:
    archivo: str
    sha256: str
    datos: DatosTarjeta
    publicador_id: int | None
    diferencias: list[Diferencia] = field(default_factory=list)
    nombramientos: list[NombramientoPropuesto] = field(default_factory=list)
    meses_en_conflicto: list[int] = field(default_factory=list)
    ya_importado: datetime | None = None


@dataclass
class Decision:
    propuesta: Propuesta
    publicador_id: int | None
    aceptar_campos: set[str]
    aceptar_nombramientos: list[NombramientoPropuesto]
    aceptar_meses: set[int]


def _anio_calendario(anio_servicio: int, mes: int) -> int:
    return anio_servicio - 1 if mes >= 9 else anio_servicio


def analizar(sesion: Session, archivo: str, contenido: bytes) -> Propuesta:
    datos = leer_tarjeta(contenido)
    sha = hashlib.sha256(contenido).hexdigest()

    previa = sesion.exec(
        select(Importacion)
        .where(Importacion.sha256 == sha, Importacion.deshecho == False)  # noqa: E712
        .order_by(Importacion.fecha.desc())
    ).first()

    existente = publicadores.buscar_por_nombre(sesion, datos.nombre) if datos.nombre else None
    propuesta = Propuesta(
        archivo=archivo,
        sha256=sha,
        datos=datos,
        publicador_id=existente.id if existente else None,
        ya_importado=previa.fecha if previa else None,
    )

    if existente is not None:
        for campo, etiqueta in CAMPOS_CABECERA:
            actual = getattr(existente, campo)
            nuevo = getattr(datos, campo)
            if nuevo is not None and nuevo != actual:
                propuesta.diferencias.append(Diferencia(campo, etiqueta, actual, nuevo))

    if datos.anio_servicio is not None:
        inicio, fin = rango_anio_servicio(datos.anio_servicio)
        vigentes = (
            nombramientos.tipos_en_anio(sesion, existente.id, datos.anio_servicio)
            if existente
            else set()
        )
        propuesta.nombramientos = [
            NombramientoPropuesto(tipo, inicio)
            for tipo in sorted(datos.nombramientos - vigentes)
        ]

        if existente is not None:
            guardados = registros.registros_del_anio(
                sesion, existente.id, datos.anio_servicio
            )
            for fila in datos.meses:
                previo = guardados.get(fila.mes)
                if previo is None:
                    continue
                distinto = (
                    previo.participo != fila.participo
                    or previo.cursos_biblicos != fila.cursos_biblicos
                    or previo.precursor_auxiliar != fila.precursor_auxiliar
                    or previo.horas != fila.horas
                    or (previo.notas or "") != (fila.notas or "")
                )
                if distinto:
                    propuesta.meses_en_conflicto.append(fila.mes)

    return propuesta


def _snapshot_publicador(publicador: Publicador) -> dict:
    return {
        "nombre_completo": publicador.nombre_completo,
        "fecha_nacimiento": publicador.fecha_nacimiento.isoformat()
        if publicador.fecha_nacimiento
        else None,
        "fecha_bautismo": publicador.fecha_bautismo.isoformat()
        if publicador.fecha_bautismo
        else None,
        "sexo": publicador.sexo,
        "esperanza": publicador.esperanza,
    }


def _snapshot_registro(registro: RegistroMensual | None) -> dict | None:
    if registro is None:
        return None
    return {
        "participo": registro.participo,
        "cursos_biblicos": registro.cursos_biblicos,
        "precursor_auxiliar": registro.precursor_auxiliar,
        "horas": registro.horas,
        "notas": registro.notas,
    }


def aplicar(
    sesion: Session, decision: Decision, lote: str, ahora: datetime
) -> Importacion:
    datos = decision.propuesta.datos
    anio_servicio = datos.anio_servicio

    if decision.publicador_id is None:
        publicador = publicadores.crear(sesion, datos.nombre)
        accion = "creado"
        previo_publicador = None
    else:
        publicador = publicadores.obtener(sesion, decision.publicador_id)
        accion = "actualizado"
        previo_publicador = _snapshot_publicador(publicador)

    cambios = {
        campo: getattr(datos, campo)
        for campo, _etiqueta in CAMPOS_CABECERA
        if campo in decision.aceptar_campos
    }
    if cambios:
        publicador = publicadores.actualizar(sesion, publicador.id, **cambios)

    nombramientos_creados = []
    for propuesto in decision.aceptar_nombramientos:
        creado = nombramientos.crear(
            sesion, publicador.id, propuesto.tipo, propuesto.desde
        )
        nombramientos_creados.append(creado.id)

    registros_tocados = []
    if anio_servicio is not None:
        for fila in datos.meses:
            if fila.mes not in decision.aceptar_meses:
                continue
            anio = _anio_calendario(anio_servicio, fila.mes)
            actual = sesion.exec(
                select(RegistroMensual).where(
                    RegistroMensual.publicador_id == publicador.id,
                    RegistroMensual.anio == anio,
                    RegistroMensual.mes == fila.mes,
                )
            ).first()
            registros_tocados.append(
                {"anio": anio, "mes": fila.mes, "previo": _snapshot_registro(actual)}
            )
            registros.guardar_mes(
                sesion,
                anio,
                fila.mes,
                [
                    registros.EntradaMes(
                        publicador_id=publicador.id,
                        participo=fila.participo,
                        cursos_biblicos=fila.cursos_biblicos,
                        precursor_auxiliar=fila.precursor_auxiliar,
                        horas=fila.horas,
                        notas=fila.notas,
                    )
                ],
            )

    registro = Importacion(
        archivo=decision.propuesta.archivo,
        sha256=decision.propuesta.sha256,
        fecha=ahora,
        lote=lote,
        publicador_id=publicador.id,
        anio_servicio=anio_servicio,
        accion=accion,
        estado_previo=json.dumps(
            {
                "publicador_creado": previo_publicador is None,
                "publicador": previo_publicador,
                "nombramientos_creados": nombramientos_creados,
                "registros": registros_tocados,
            }
        ),
    )
    sesion.add(registro)
    sesion.commit()
    sesion.refresh(registro)
    return registro


def _restaurar(sesion: Session, registro: Importacion) -> None:
    estado = json.loads(registro.estado_previo or "{}")

    for nombramiento_id in estado.get("nombramientos_creados", []):
        nombramiento = sesion.get(Nombramiento, nombramiento_id)
        if nombramiento is not None:
            sesion.delete(nombramiento)

    for tocado in estado.get("registros", []):
        fila = sesion.exec(
            select(RegistroMensual).where(
                RegistroMensual.publicador_id == registro.publicador_id,
                RegistroMensual.anio == tocado["anio"],
                RegistroMensual.mes == tocado["mes"],
            )
        ).first()
        if fila is None:
            continue
        if tocado["previo"] is None:
            sesion.delete(fila)
            continue
        for nombre, valor in tocado["previo"].items():
            setattr(fila, nombre, valor)
        sesion.add(fila)

    publicador = (
        sesion.get(Publicador, registro.publicador_id) if registro.publicador_id else None
    )
    if publicador is None:
        return
    if estado.get("publicador_creado"):
        registro.publicador_id = None
        sesion.add(registro)
        sesion.flush()
        sesion.delete(publicador)
    elif estado.get("publicador"):
        previo = estado["publicador"]
        publicadores.actualizar(
            sesion,
            publicador.id,
            nombre_completo=previo["nombre_completo"],
            fecha_nacimiento=date.fromisoformat(previo["fecha_nacimiento"])
            if previo["fecha_nacimiento"]
            else None,
            fecha_bautismo=date.fromisoformat(previo["fecha_bautismo"])
            if previo["fecha_bautismo"]
            else None,
            sexo=previo["sexo"],
            esperanza=previo["esperanza"],
        )


def deshacer(sesion: Session, lote: str) -> int:
    pendientes = sesion.exec(
        select(Importacion).where(
            Importacion.lote == lote,
            Importacion.deshecho == False,  # noqa: E712
        )
    ).all()

    for registro in pendientes:
        _restaurar(sesion, registro)
        registro.deshecho = True
        sesion.add(registro)
    sesion.commit()
    return len(pendientes)


def historial(sesion: Session) -> list[tuple[str, datetime, int]]:
    """(lote, fecha, archivos) de las importaciones no deshechas, la más nueva primero."""
    filas = sesion.exec(
        select(Importacion)
        .where(Importacion.deshecho == False)  # noqa: E712
        .order_by(Importacion.fecha.desc())
    ).all()
    por_lote: dict[str, tuple[datetime, int]] = {}
    for fila in filas:
        fecha, cantidad = por_lote.get(fila.lote, (fila.fecha, 0))
        por_lote[fila.lote] = (min(fecha, fila.fecha), cantidad + 1)
    return [(lote, fecha, cantidad) for lote, (fecha, cantidad) in por_lote.items()]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_importacion.py -v`
Expected: PASS

- [ ] **Step 5: Correr toda la suite**

Run: `pytest -v`
Expected: PASS (con el test de la plantilla real en SKIPPED)

- [ ] **Step 6: Commit**

```bash
git add app/services/importacion.py tests/services/test_importacion.py
git commit -m "feat: importación con pantalla de revisión y deshacer por lote"
```

---

## Nota sobre HTMX

El spec menciona HTMX para la grilla y la revisión de importación. Al desglosar
las pantallas, las dos funcionan como formularios normales con un único POST, que
es justamente lo que el spec pide de la grilla ("guardado del mes completo en un
POST"). Las tareas 15 a 20 no usan HTMX y no vendorizan ningún archivo estático
de terceros. Si más adelante hace falta guardado parcial o validación en vivo, se
agrega entonces con el archivo servido desde `app/web/static/`.

---

## Task 15: Autenticación, layout y página de inicio

**Files:**
- Create: `app/auth.py`, `app/web/__init__.py`, `app/web/plantillas.py`, `app/web/routers/__init__.py`, `app/web/routers/sesion.py`, `app/web/routers/inicio.py`, `app/web/templates/base.html`, `app/web/templates/login.html`, `app/web/templates/inicio.html`, `app/web/static/estilos.css`, `tests/web/__init__.py`, `tests/web/test_sesion.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `app.config.cargar_config`, `app.db.obtener_sesion`, `app.services.alertas`, `app.dominio`
- Produces:
  - `app.auth.requerir_sesion(request) -> str` (dependencia de FastAPI; redirige a `/entrar` si no hay sesión)
  - `app.auth.credenciales_validas(usuario, clave) -> bool`
  - `app.web.plantillas.plantillas` (instancia `Jinja2Templates` con el filtro `mes_nombre`)
  - Rutas: `GET /entrar`, `POST /entrar`, `POST /salir`, `GET /` (inicio)
  - `tests/conftest.py` gana la fixture `cliente` (TestClient autenticado sobre una base temporal)

- [ ] **Step 1: Escribir el test que falla**

`tests/web/test_sesion.py`:

```python
def test_sin_sesion_la_raiz_redirige_al_login(cliente_anonimo):
    respuesta = cliente_anonimo.get("/", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/entrar"


def test_el_login_muestra_el_formulario(cliente_anonimo):
    respuesta = cliente_anonimo.get("/entrar")

    assert respuesta.status_code == 200
    assert "Iniciar sesión" in respuesta.text


def test_credenciales_correctas_entran(cliente_anonimo):
    respuesta = cliente_anonimo.post(
        "/entrar",
        data={"usuario": "prueba", "clave": "secreta"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"


def test_credenciales_incorrectas_no_entran(cliente_anonimo):
    respuesta = cliente_anonimo.post(
        "/entrar", data={"usuario": "prueba", "clave": "equivocada"}
    )

    assert respuesta.status_code == 401
    assert "Usuario o clave incorrectos" in respuesta.text


def test_con_sesion_la_raiz_responde(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "Año de servicio" in respuesta.text


def test_salir_cierra_la_sesion(cliente):
    cliente.post("/salir", follow_redirects=False)

    assert cliente.get("/", follow_redirects=False).status_code == 303


def test_la_salud_no_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/salud").status_code == 200
```

- [ ] **Step 2: Añadir las fixtures web a `tests/conftest.py`**

```python
from fastapi.testclient import TestClient


@pytest.fixture
def cliente_anonimo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_USER", "prueba")
    monkeypatch.setenv("AUTH_PASS", "secreta")
    monkeypatch.setenv("SECRET_KEY", "clave-de-prueba")

    from app import db

    # el engine es perezoso y cacheado: se limpia para que tome el DATA_DIR nuevo
    db.motor.cache_clear()

    from app.main import app

    with TestClient(app) as abierto:
        yield abierto

    db.motor.cache_clear()


@pytest.fixture
def cliente(cliente_anonimo):
    cliente_anonimo.post("/entrar", data={"usuario": "prueba", "clave": "secreta"})
    return cliente_anonimo
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `pytest tests/web/test_sesion.py -v`
Expected: FAIL — la raíz devuelve 404 porque todavía no existe

- [ ] **Step 4: Crear `app/auth.py`**

```python
"""Sesión de un solo usuario, con las credenciales en variables de entorno."""

import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import cargar_config

CLAVE_SESION = "usuario"


class SinSesion(Exception):
    """Se convierte en redirección al login en el manejador de app.main."""


def credenciales_validas(usuario: str, clave: str) -> bool:
    config = cargar_config()
    # compare_digest evita filtrar la longitud por tiempo de respuesta
    return secrets.compare_digest(usuario, config.auth_user) and secrets.compare_digest(
        clave, config.auth_pass
    )


def iniciar_sesion(request: Request, usuario: str) -> None:
    request.session[CLAVE_SESION] = usuario


def cerrar_sesion(request: Request) -> None:
    request.session.pop(CLAVE_SESION, None)


def requerir_sesion(request: Request) -> str:
    usuario = request.session.get(CLAVE_SESION)
    if not usuario:
        raise SinSesion()
    return usuario


def redirigir_al_login() -> RedirectResponse:
    return RedirectResponse("/entrar", status_code=303)
```

- [ ] **Step 5: Crear `app/web/plantillas.py`**

```python
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.dominio import NOMBRE_MES

DIRECTORIO = Path(__file__).resolve().parent / "templates"

plantillas = Jinja2Templates(directory=str(DIRECTORIO))
plantillas.env.filters["mes_nombre"] = lambda mes: NOMBRE_MES[mes].capitalize()
```

- [ ] **Step 6: Crear los routers**

`app/web/routers/sesion.py`:

```python
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app import auth
from app.web.plantillas import plantillas

router = APIRouter()


@router.get("/entrar")
def formulario(request: Request):
    return plantillas.TemplateResponse(request, "login.html", {"error": None})


@router.post("/entrar")
def entrar(request: Request, usuario: str = Form(...), clave: str = Form(...)):
    if not auth.credenciales_validas(usuario, clave):
        return plantillas.TemplateResponse(
            request,
            "login.html",
            {"error": "Usuario o clave incorrectos"},
            status_code=401,
        )
    auth.iniciar_sesion(request, usuario)
    return RedirectResponse("/", status_code=303)


@router.post("/salir")
def salir(request: Request):
    auth.cerrar_sesion(request)
    return RedirectResponse("/entrar", status_code=303)
```

`app/web/routers/inicio.py`:

```python
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.services import alertas
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
        },
    )
```

`app/web/__init__.py` y `app/web/routers/__init__.py` quedan vacíos.

- [ ] **Step 7: Crear las plantillas**

`app/web/templates/base.html`:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}Registros de predicación{% endblock %}</title>
  <link rel="stylesheet" href="/static/estilos.css">
</head>
<body>
  {% if request.session.get('usuario') %}
  <nav>
    <a href="/">Inicio</a>
    <a href="/grilla">Carga mensual</a>
    <a href="/publicadores">Publicadores</a>
    <a href="/grupos">Grupos</a>
    <a href="/importar">Importar</a>
    <a href="/informe">Informe</a>
    <a href="/alertas">Alertas</a>
    <form method="post" action="/salir" class="derecha">
      <button type="submit">Salir</button>
    </form>
  </nav>
  {% endif %}
  <main>
    {% block contenido %}{% endblock %}
  </main>
</body>
</html>
```

`app/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Iniciar sesión</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/entrar">
  <label>Usuario <input name="usuario" autofocus required></label>
  <label>Clave <input name="clave" type="password" required></label>
  <button type="submit">Entrar</button>
</form>
{% endblock %}
```

`app/web/templates/inicio.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Año de servicio {{ anio_servicio }}</h1>
<p><a href="/grilla?anio={{ hoy.year }}&amp;mes={{ hoy.month }}">
  Cargar {{ hoy.month | mes_nombre }} de {{ hoy.year }}</a></p>

<h2>Alertas ({{ alertas | length }})</h2>
{% if alertas %}
<ul>
  {% for alerta in alertas %}
  <li>
    <a href="/publicadores/{{ alerta.publicador.id }}">{{ alerta.publicador.nombre_completo }}</a>
    — {{ alerta.estado }} ({{ alerta.meses_sin_informar | length }} meses sin informar)
  </li>
  {% endfor %}
</ul>
{% else %}
<p>Sin publicadores irregulares ni inactivos.</p>
{% endif %}
{% endblock %}
```

`app/web/static/estilos.css`:

```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; color: #1c1c1c; background: #fbfbfa; }
nav { display: flex; gap: 1rem; align-items: center; padding: .75rem 1rem;
      background: #23405a; }
nav a { color: #fff; text-decoration: none; }
nav a:hover { text-decoration: underline; }
nav .derecha { margin-left: auto; }
main { padding: 1rem; max-width: 72rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #d6d6d0; padding: .3rem .5rem; text-align: left; }
th { background: #eeeeea; }
tr.conflicto td { background: #fff1f0; }
input[type="number"] { width: 5rem; }
label { display: block; margin: .4rem 0; }
.error { color: #a11; }
.numero { text-align: right; }
```

- [ ] **Step 8: Reescribir `app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import SinSesion, redirigir_al_login
from app.config import cargar_config
from app.db import motor
from app.web.plantillas import DIRECTORIO
from app.web.routers import inicio, sesion


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    motor()  # aplica las migraciones pendientes al arrancar
    yield


app = FastAPI(title="Registros de predicación", lifespan=ciclo_de_vida)
app.add_middleware(SessionMiddleware, secret_key=cargar_config().secret_key)
app.mount("/static", StaticFiles(directory=str(DIRECTORIO.parent / "static")), name="static")


@app.exception_handler(SinSesion)
def sin_sesion(_request: Request, _error: SinSesion):
    return redirigir_al_login()


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


app.include_router(sesion.router)
app.include_router(inicio.router)
```

- [ ] **Step 9: Correr los tests y verificar que pasan**

Run: `pytest tests/web/test_sesion.py tests/test_salud.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add app/auth.py app/web app/main.py tests/web tests/conftest.py
git commit -m "feat: login por cookie, layout base y página de inicio"
```

---

## Task 16: Mantenedor de publicadores y grupos

**Files:**
- Modify: `app/services/publicadores.py` (añadir el filtro por privilegio)
- Create: `app/services/grupos.py`, `app/web/routers/publicadores.py`, `app/web/routers/grupos.py`, `app/web/templates/publicadores_lista.html`, `app/web/templates/publicador_detalle.html`, `app/web/templates/grupos.html`, `tests/services/test_grupos.py`, `tests/web/test_publicadores.py`
- Modify: `app/main.py` (montar los routers)

**Interfaces:**
- Consumes: `app.services.publicadores`, `app.services.nombramientos`, `app.models.Grupo`
- Produces:
  - `app.services.publicadores.con_privilegio(sesion, lista, privilegio, hoy) -> list[Publicador]`
  - `app.services.grupos.crear(sesion, nombre, superintendente_id=None) -> Grupo`, `listar(sesion) -> list[Grupo]`, `obtener(sesion, grupo_id) -> Grupo`, `actualizar(sesion, grupo_id, **campos) -> Grupo`, `eliminar(sesion, grupo_id) -> None`
  - Rutas: `GET /publicadores`, `POST /publicadores`, `GET /publicadores/{id}`, `POST /publicadores/{id}`, `POST /publicadores/{id}/baja`, `POST /publicadores/{id}/nombramientos`, `POST /publicadores/{id}/nombramientos/{nid}/cerrar`, `GET /grupos`, `POST /grupos`, `POST /grupos/{id}`, `POST /grupos/{id}/eliminar`

- [ ] **Step 1: Escribir el test de servicio que falla**

`tests/services/test_grupos.py`:

```python
import pytest

from app.services import grupos, publicadores


def test_crear_y_listar(sesion):
    grupos.crear(sesion, "Sur")
    grupos.crear(sesion, "Centro")

    assert [g.nombre for g in grupos.listar(sesion)] == ["Centro", "Sur"]


def test_asignar_superintendente(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    grupo = grupos.crear(sesion, "Centro")

    actualizado = grupos.actualizar(sesion, grupo.id, superintendente_id=ana.id)

    assert actualizado.superintendente_id == ana.id


def test_eliminar_un_grupo_deja_a_sus_publicadores_sin_grupo(sesion):
    grupo = grupos.crear(sesion, "Centro")
    ana = publicadores.crear(sesion, "Perez Ana", grupo_id=grupo.id)

    grupos.eliminar(sesion, grupo.id)

    assert publicadores.obtener(sesion, ana.id).grupo_id is None


def test_obtener_lanza_si_no_existe(sesion):
    with pytest.raises(grupos.GrupoNoEncontrado):
        grupos.obtener(sesion, 999)
```

Y en `tests/services/test_publicadores.py`, añadir al final:

```python
def test_con_privilegio_filtra_por_nombramiento_vigente_hoy(sesion):
    from datetime import date

    from app.services import nombramientos

    precursora = publicadores.crear(sesion, "Precursora Una")
    publicadores.crear(sesion, "Comun Dos")
    nombramientos.crear(sesion, precursora.id, "precursor_regular", date(2025, 9, 1))

    lista = publicadores.listar(sesion)
    filtrada = publicadores.con_privilegio(
        sesion, lista, "precursor_regular", date(2026, 1, 15)
    )

    assert [p.id for p in filtrada] == [precursora.id]


def test_con_privilegio_sin_valor_devuelve_la_lista_entera(sesion):
    from datetime import date

    publicadores.crear(sesion, "Comun Dos")
    lista = publicadores.listar(sesion)

    assert publicadores.con_privilegio(sesion, lista, None, date(2026, 1, 15)) == lista
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_grupos.py -v`
Expected: FAIL con `ImportError: cannot import name 'grupos'`

- [ ] **Step 3: Crear `app/services/grupos.py`**

```python
"""CRUD de grupos de predicación."""

from sqlmodel import Session, select

from app.models import Grupo, Publicador


class GrupoNoEncontrado(Exception):
    pass


def crear(sesion: Session, nombre: str, superintendente_id: int | None = None) -> Grupo:
    grupo = Grupo(nombre=nombre.strip(), superintendente_id=superintendente_id)
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    return grupo


def obtener(sesion: Session, grupo_id: int) -> Grupo:
    grupo = sesion.get(Grupo, grupo_id)
    if grupo is None:
        raise GrupoNoEncontrado(f"no existe el grupo {grupo_id}")
    return grupo


def listar(sesion: Session) -> list[Grupo]:
    return list(sesion.exec(select(Grupo).order_by(Grupo.nombre)).all())


def actualizar(sesion: Session, grupo_id: int, **campos) -> Grupo:
    grupo = obtener(sesion, grupo_id)
    for nombre, valor in campos.items():
        setattr(grupo, nombre, valor)
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    return grupo


def eliminar(sesion: Session, grupo_id: int) -> None:
    grupo = obtener(sesion, grupo_id)
    integrantes = sesion.exec(
        select(Publicador).where(Publicador.grupo_id == grupo_id)
    ).all()
    for publicador in integrantes:
        publicador.grupo_id = None
        sesion.add(publicador)
    sesion.delete(grupo)
    sesion.commit()
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_grupos.py -v`
Expected: PASS

- [ ] **Step 4b: Añadir el filtro por privilegio a `app/services/publicadores.py`**

El filtro necesita saber qué nombramientos están vigentes, así que se resuelve
sobre una lista ya obtenida en vez de dentro de la consulta. `nombramientos` no
importa `publicadores`, de modo que la dependencia queda en un solo sentido.

```python
def con_privilegio(
    sesion: Session,
    lista: list[Publicador],
    privilegio: str | None,
    hoy: date,
) -> list[Publicador]:
    """Filtra la lista dejando a quienes tienen ese nombramiento vigente hoy."""
    if not privilegio:
        return lista
    from app.services import nombramientos

    return [
        publicador
        for publicador in lista
        if privilegio
        in nombramientos.tipos_en_mes(sesion, publicador.id, hoy.year, hoy.month)
    ]
```

Correr `pytest tests/services/test_publicadores.py -v` y verificar que pasa.

- [ ] **Step 5: Escribir el test web que falla**

`tests/web/test_publicadores.py`:

```python
def test_la_lista_esta_vacia_al_principio(cliente):
    respuesta = cliente.get("/publicadores")

    assert respuesta.status_code == 200
    assert "No hay publicadores" in respuesta.text


def test_crear_un_publicador_desde_el_formulario(cliente):
    cliente.post(
        "/publicadores",
        data={
            "nombre_completo": "Pérez Gómez Ana María",
            "sexo": "M",
            "esperanza": "otras_ovejas",
            "fecha_bautismo": "2010-04-03",
        },
        follow_redirects=True,
    )

    assert "Pérez Gómez Ana María" in cliente.get("/publicadores").text


def test_el_buscador_filtra(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Núñez José"})
    cliente.post("/publicadores", data={"nombre_completo": "Otro Distinto"})

    respuesta = cliente.get("/publicadores", params={"texto": "nunez"})

    assert "Núñez José" in respuesta.text
    assert "Otro Distinto" not in respuesta.text


def test_el_detalle_muestra_los_nombramientos(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )

    respuesta = cliente.get("/publicadores/1")

    assert "precursor regular" in respuesta.text
    assert "2025-09-01" in respuesta.text


def test_cerrar_un_nombramiento(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "anciano", "desde": "2020-01-01"},
    )

    cliente.post("/publicadores/1/nombramientos/1/cerrar", data={"hasta": "2026-04-30"})

    assert "2026-04-30" in cliente.get("/publicadores/1").text


def test_dar_de_baja_saca_al_publicador_de_la_lista(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    cliente.post("/publicadores/1/baja", data={"fecha_baja": "2026-05-01", "motivo_baja": "mudado"})

    assert "Perez Ana" not in cliente.get("/publicadores").text
    assert "Perez Ana" in cliente.get("/publicadores", params={"incluir_bajas": "1"}).text


def test_los_grupos_se_crean_y_se_asignan(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana", "grupo_id": "1"})

    assert "Centro" in cliente.get("/publicadores").text


def test_filtrar_la_lista_por_privilegio(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Precursora Una"})
    cliente.post("/publicadores", data={"nombre_completo": "Comun Dos"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2020-01-01"},
    )

    respuesta = cliente.get("/publicadores", params={"privilegio": "precursor_regular"})

    assert "Precursora Una" in respuesta.text
    assert "Comun Dos" not in respuesta.text


def test_publicadores_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/publicadores", follow_redirects=False).status_code == 303
```

- [ ] **Step 6: Correr el test y verificar que falla**

Run: `pytest tests/web/test_publicadores.py -v`
Expected: FAIL con 404 en `/publicadores`

- [ ] **Step 7: Crear `app/web/routers/publicadores.py`**

```python
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.dominio import TIPOS_NOMBRAMIENTO
from app.services import grupos, nombramientos
from app.services import publicadores as servicio
from app.web.plantillas import plantillas

router = APIRouter(prefix="/publicadores")


def _fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _vacio_a_none(valor: str | None) -> str | None:
    return valor or None


@router.get("")
def lista(
    request: Request,
    texto: str | None = None,
    grupo_id: int | None = None,
    privilegio: str | None = None,
    incluir_bajas: bool = False,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    encontrados = servicio.listar(
        sesion, texto=texto, grupo_id=grupo_id, incluir_bajas=incluir_bajas
    )
    encontrados = servicio.con_privilegio(sesion, encontrados, privilegio, date.today())
    todos_los_grupos = grupos.listar(sesion)
    return plantillas.TemplateResponse(
        request,
        "publicadores_lista.html",
        {
            "publicadores": encontrados,
            "grupos": {grupo.id: grupo for grupo in todos_los_grupos},
            "todos_los_grupos": todos_los_grupos,
            "etiquetas": nombramientos.ETIQUETAS,
            "tipos": TIPOS_NOMBRAMIENTO,
            "texto": texto or "",
            "grupo_id": grupo_id,
            "privilegio": privilegio or "",
            "incluir_bajas": incluir_bajas,
        },
    )


@router.post("")
def crear(
    nombre_completo: str = Form(...),
    sexo: str | None = Form(None),
    esperanza: str | None = Form(None),
    fecha_nacimiento: str | None = Form(None),
    fecha_bautismo: str | None = Form(None),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.crear(
        sesion,
        nombre_completo,
        sexo=_vacio_a_none(sexo),
        esperanza=_vacio_a_none(esperanza),
        fecha_nacimiento=_fecha(fecha_nacimiento),
        fecha_bautismo=_fecha(fecha_bautismo),
        grupo_id=grupo_id,
    )
    return RedirectResponse("/publicadores", status_code=303)


@router.get("/{publicador_id}")
def detalle(
    publicador_id: int,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request,
        "publicador_detalle.html",
        {
            "publicador": servicio.obtener(sesion, publicador_id),
            "nombramientos": nombramientos.listar(sesion, publicador_id),
            "etiquetas": nombramientos.ETIQUETAS,
            "tipos": TIPOS_NOMBRAMIENTO,
            "grupos": grupos.listar(sesion),
        },
    )


@router.post("/{publicador_id}")
def editar(
    publicador_id: int,
    nombre_completo: str = Form(...),
    sexo: str | None = Form(None),
    esperanza: str | None = Form(None),
    fecha_nacimiento: str | None = Form(None),
    fecha_bautismo: str | None = Form(None),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.actualizar(
        sesion,
        publicador_id,
        nombre_completo=nombre_completo,
        sexo=_vacio_a_none(sexo),
        esperanza=_vacio_a_none(esperanza),
        fecha_nacimiento=_fecha(fecha_nacimiento),
        fecha_bautismo=_fecha(fecha_bautismo),
        grupo_id=grupo_id,
    )
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)


@router.post("/{publicador_id}/baja")
def baja(
    publicador_id: int,
    fecha_baja: str = Form(...),
    motivo_baja: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.dar_de_baja(sesion, publicador_id, date.fromisoformat(fecha_baja), motivo_baja)
    return RedirectResponse("/publicadores", status_code=303)


@router.post("/{publicador_id}/nombramientos")
def agregar_nombramiento(
    publicador_id: int,
    tipo: str = Form(...),
    desde: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    nombramientos.crear(sesion, publicador_id, tipo, date.fromisoformat(desde))
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)


@router.post("/{publicador_id}/nombramientos/{nombramiento_id}/cerrar")
def cerrar_nombramiento(
    publicador_id: int,
    nombramiento_id: int,
    hasta: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    nombramientos.cerrar(sesion, nombramiento_id, date.fromisoformat(hasta))
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)
```

- [ ] **Step 8: Crear `app/web/routers/grupos.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.services import grupos as servicio
from app.services import publicadores
from app.web.plantillas import plantillas

router = APIRouter(prefix="/grupos")


@router.get("")
def lista(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request,
        "grupos.html",
        {
            "grupos": servicio.listar(sesion),
            "publicadores": publicadores.listar(sesion),
        },
    )


@router.post("")
def crear(
    nombre: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.crear(sesion, nombre)
    return RedirectResponse("/grupos", status_code=303)


@router.post("/{grupo_id}")
def editar(
    grupo_id: int,
    nombre: str = Form(...),
    superintendente_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.actualizar(
        sesion, grupo_id, nombre=nombre, superintendente_id=superintendente_id
    )
    return RedirectResponse("/grupos", status_code=303)


@router.post("/{grupo_id}/eliminar")
def eliminar(
    grupo_id: int,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.eliminar(sesion, grupo_id)
    return RedirectResponse("/grupos", status_code=303)
```

- [ ] **Step 9: Crear las plantillas**

`app/web/templates/publicadores_lista.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Publicadores</h1>

<form method="get" action="/publicadores">
  <input name="texto" value="{{ texto }}" placeholder="Buscar por nombre">
  <label>Grupo
    <select name="grupo_id"><option value="">Todos</option>
      {% for grupo in todos_los_grupos %}
      <option value="{{ grupo.id }}" {% if grupo.id == grupo_id %}selected{% endif %}>{{ grupo.nombre }}</option>
      {% endfor %}</select></label>
  <label>Privilegio
    <select name="privilegio"><option value="">Todos</option>
      {% for tipo in tipos %}
      <option value="{{ tipo }}" {% if tipo == privilegio %}selected{% endif %}>{{ etiquetas[tipo] }}</option>
      {% endfor %}</select></label>
  <label><input type="checkbox" name="incluir_bajas" value="1"
    {% if incluir_bajas %}checked{% endif %}> Incluir bajas</label>
  <button type="submit">Buscar</button>
</form>

{% if publicadores %}
<table>
  <tr><th>Nombre</th><th>Grupo</th><th>Bautismo</th><th>Estado</th></tr>
  {% for p in publicadores %}
  <tr>
    <td><a href="/publicadores/{{ p.id }}">{{ p.nombre_completo }}</a></td>
    <td>{{ grupos[p.grupo_id].nombre if p.grupo_id else '' }}</td>
    <td>{{ p.fecha_bautismo or '' }}</td>
    <td>{{ 'baja: ' ~ p.motivo_baja if p.fecha_baja else 'activo' }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>No hay publicadores que mostrar.</p>
{% endif %}

<h2>Agregar publicador</h2>
<form method="post" action="/publicadores">
  <label>Nombre completo <input name="nombre_completo" required></label>
  <label>Sexo
    <select name="sexo"><option value="">—</option>
      <option value="H">Hombre</option><option value="M">Mujer</option></select></label>
  <label>Esperanza
    <select name="esperanza"><option value="">—</option>
      <option value="otras_ovejas">Otras ovejas</option>
      <option value="ungido">Ungido</option></select></label>
  <label>Fecha de nacimiento <input type="date" name="fecha_nacimiento"></label>
  <label>Fecha de bautismo <input type="date" name="fecha_bautismo"></label>
  <label>Grupo
    <select name="grupo_id"><option value="">—</option>
      {% for id, grupo in grupos.items() %}
      <option value="{{ id }}">{{ grupo.nombre }}</option>{% endfor %}</select></label>
  <button type="submit">Guardar</button>
</form>
{% endblock %}
```

`app/web/templates/publicador_detalle.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>{{ publicador.nombre_completo }}</h1>

<form method="post" action="/publicadores/{{ publicador.id }}">
  <label>Nombre completo
    <input name="nombre_completo" value="{{ publicador.nombre_completo }}" required></label>
  <label>Sexo
    <select name="sexo"><option value="">—</option>
      <option value="H" {% if publicador.sexo == 'H' %}selected{% endif %}>Hombre</option>
      <option value="M" {% if publicador.sexo == 'M' %}selected{% endif %}>Mujer</option>
    </select></label>
  <label>Esperanza
    <select name="esperanza"><option value="">—</option>
      <option value="otras_ovejas" {% if publicador.esperanza == 'otras_ovejas' %}selected{% endif %}>Otras ovejas</option>
      <option value="ungido" {% if publicador.esperanza == 'ungido' %}selected{% endif %}>Ungido</option>
    </select></label>
  <label>Fecha de nacimiento
    <input type="date" name="fecha_nacimiento" value="{{ publicador.fecha_nacimiento or '' }}"></label>
  <label>Fecha de bautismo
    <input type="date" name="fecha_bautismo" value="{{ publicador.fecha_bautismo or '' }}"></label>
  <label>Grupo
    <select name="grupo_id"><option value="">—</option>
      {% for grupo in grupos %}
      <option value="{{ grupo.id }}" {% if publicador.grupo_id == grupo.id %}selected{% endif %}>{{ grupo.nombre }}</option>
      {% endfor %}</select></label>
  <button type="submit">Guardar</button>
</form>

<h2>Nombramientos</h2>
<table>
  <tr><th>Tipo</th><th>Desde</th><th>Hasta</th><th></th></tr>
  {% for n in nombramientos %}
  <tr>
    <td>{{ etiquetas[n.tipo] }}</td>
    <td>{{ n.desde }}</td>
    <td>{{ n.hasta or 'vigente' }}</td>
    <td>
      {% if not n.hasta %}
      <form method="post" action="/publicadores/{{ publicador.id }}/nombramientos/{{ n.id }}/cerrar">
        <input type="date" name="hasta" required>
        <button type="submit">Cerrar</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>

<form method="post" action="/publicadores/{{ publicador.id }}/nombramientos">
  <select name="tipo">
    {% for tipo in tipos %}<option value="{{ tipo }}">{{ etiquetas[tipo] }}</option>{% endfor %}
  </select>
  <input type="date" name="desde" required>
  <button type="submit">Agregar nombramiento</button>
</form>

<h2>Dar de baja</h2>
<form method="post" action="/publicadores/{{ publicador.id }}/baja">
  <input type="date" name="fecha_baja" required>
  <select name="motivo_baja">
    <option value="fallecido">Fallecido</option>
    <option value="mudado">Mudado</option>
    <option value="otro">Otro</option>
  </select>
  <button type="submit">Dar de baja</button>
</form>
{% endblock %}
```

`app/web/templates/grupos.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Grupos de predicación</h1>

<table>
  <tr><th>Nombre</th><th>Superintendente</th><th></th></tr>
  {% for grupo in grupos %}
  <tr>
    <td colspan="2">
      <form method="post" action="/grupos/{{ grupo.id }}">
        <input name="nombre" value="{{ grupo.nombre }}" required>
        <select name="superintendente_id">
          <option value="">—</option>
          {% for p in publicadores %}
          <option value="{{ p.id }}" {% if grupo.superintendente_id == p.id %}selected{% endif %}>{{ p.nombre_completo }}</option>
          {% endfor %}
        </select>
        <button type="submit">Guardar</button>
      </form>
    </td>
    <td>
      <form method="post" action="/grupos/{{ grupo.id }}/eliminar">
        <button type="submit">Eliminar</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>

<h2>Agregar grupo</h2>
<form method="post" action="/grupos">
  <input name="nombre" required>
  <button type="submit">Crear</button>
</form>
{% endblock %}
```

- [ ] **Step 10: Montar los routers en `app/main.py`**

```python
from app.web.routers import grupos, inicio, publicadores, sesion

app.include_router(sesion.router)
app.include_router(inicio.router)
app.include_router(publicadores.router)
app.include_router(grupos.router)
```

- [ ] **Step 11: Correr los tests y verificar que pasan**

Run: `pytest tests/web tests/services/test_grupos.py -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add app/services/grupos.py app/web tests/services/test_grupos.py tests/web/test_publicadores.py app/main.py
git commit -m "feat: mantenedor de publicadores, nombramientos y grupos"
```

---

## Task 17: Grilla de carga mensual

**Files:**
- Create: `app/web/routers/grilla.py`, `app/web/templates/grilla.html`, `tests/web/test_grilla.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `app.services.registros`, `app.services.grupos`
- Produces: rutas `GET /grilla` (parámetros `anio`, `mes`, `grupo_id`; por omisión el mes actual) y `POST /grilla`.

Los campos del formulario se nombran con el id del publicador como sufijo:
`participo_{id}`, `cursos_{id}`, `auxiliar_{id}`, `horas_{id}`, `notas_{id}`, y un
`publicadores` repetido con los ids que vienen en la grilla.

- [ ] **Step 1: Escribir el test que falla**

`tests/web/test_grilla.py`:

```python
def _crear_publicador(cliente, nombre: str) -> None:
    cliente.post("/publicadores", data={"nombre_completo": nombre})


def test_la_grilla_lista_a_los_publicadores_activos(cliente):
    _crear_publicador(cliente, "Perez Ana")
    _crear_publicador(cliente, "Soto Luis")

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert respuesta.status_code == 200
    assert "Perez Ana" in respuesta.text
    assert "Soto Luis" in respuesta.text
    assert "Enero de 2026" in respuesta.text


def test_guardar_el_mes_completo(cliente):
    _crear_publicador(cliente, "Perez Ana")
    _crear_publicador(cliente, "Soto Luis")

    cliente.post(
        "/grilla",
        data={
            "anio": "2026",
            "mes": "1",
            "publicadores": ["1", "2"],
            "participo_1": "1",
            "cursos_1": "3",
            "notas_1": "visita del superintendente",
            # Soto Luis no informó: no manda participo_2
        },
        follow_redirects=True,
    )

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})
    assert 'name="cursos_1" value="3"' in respuesta.text
    assert "visita del superintendente" in respuesta.text


def _etiqueta_horas(texto: str, publicador_id: int) -> str:
    """El resto de la etiqueta <input> de horas, desde su atributo name."""
    return texto.split(f'name="horas_{publicador_id}"')[1].split(">")[0]


def test_las_horas_vienen_deshabilitadas_para_un_publicador_comun(cliente):
    _crear_publicador(cliente, "Perez Ana")

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert "disabled" in _etiqueta_horas(respuesta.text, 1)


def test_las_horas_se_habilitan_para_un_precursor_regular(cliente):
    _crear_publicador(cliente, "Perez Ana")
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert "disabled" not in _etiqueta_horas(respuesta.text, 1)


def test_guardar_dos_veces_no_duplica(cliente):
    _crear_publicador(cliente, "Perez Ana")
    datos = {"anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
             "cursos_1": "2"}

    cliente.post("/grilla", data=datos, follow_redirects=True)
    cliente.post("/grilla", data=datos, follow_redirects=True)

    texto = cliente.get("/grilla", params={"anio": 2026, "mes": 1}).text
    assert texto.count('name="cursos_1"') == 1


def test_filtrar_por_grupo(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})
    cliente.post("/publicadores", data={"nombre_completo": "Dentro Uno", "grupo_id": "1"})
    cliente.post("/publicadores", data={"nombre_completo": "Fuera Dos"})

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1, "grupo_id": 1})

    assert "Dentro Uno" in respuesta.text
    assert "Fuera Dos" not in respuesta.text


def test_la_grilla_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/grilla", follow_redirects=False).status_code == 303
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/web/test_grilla.py -v`
Expected: FAIL con 404 en `/grilla`

- [ ] **Step 3: Crear `app/web/routers/grilla.py`**

```python
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.services import grupos, registros
from app.web.plantillas import plantillas

router = APIRouter(prefix="/grilla")


def _entero(valor: str | None) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


@router.get("")
def ver(
    request: Request,
    anio: int | None = None,
    mes: int | None = None,
    grupo_id: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    return plantillas.TemplateResponse(
        request,
        "grilla.html",
        {
            "anio": anio,
            "mes": mes,
            "grupo_id": grupo_id,
            "grupos": grupos.listar(sesion),
            "filas": registros.filas_del_mes(sesion, anio, mes, grupo_id=grupo_id),
        },
    )


@router.post("")
async def guardar(
    request: Request,
    anio: int = Form(...),
    mes: int = Form(...),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    formulario = await request.form()
    entradas = []
    for crudo in formulario.getlist("publicadores"):
        publicador_id = int(crudo)
        entradas.append(
            registros.EntradaMes(
                publicador_id=publicador_id,
                participo=formulario.get(f"participo_{publicador_id}") is not None,
                cursos_biblicos=_entero(formulario.get(f"cursos_{publicador_id}")),
                precursor_auxiliar=formulario.get(f"auxiliar_{publicador_id}") is not None,
                horas=_entero(formulario.get(f"horas_{publicador_id}")),
                notas=(formulario.get(f"notas_{publicador_id}") or "").strip() or None,
            )
        )
    registros.guardar_mes(sesion, anio, mes, entradas)

    destino = f"/grilla?anio={anio}&mes={mes}"
    if grupo_id:
        destino += f"&grupo_id={grupo_id}"
    return RedirectResponse(destino, status_code=303)
```

- [ ] **Step 4: Crear `app/web/templates/grilla.html`**

```html
{% extends "base.html" %}
{% block contenido %}
<h1>{{ mes | mes_nombre }} de {{ anio }}</h1>

<form method="get" action="/grilla">
  <label>Mes
    <select name="mes">
      {% for m in [1,2,3,4,5,6,7,8,9,10,11,12] %}
      <option value="{{ m }}" {% if m == mes %}selected{% endif %}>{{ m | mes_nombre }}</option>
      {% endfor %}
    </select></label>
  <label>Año <input type="number" name="anio" value="{{ anio }}"></label>
  <label>Grupo
    <select name="grupo_id">
      <option value="">Todos</option>
      {% for grupo in grupos %}
      <option value="{{ grupo.id }}" {% if grupo.id == grupo_id %}selected{% endif %}>{{ grupo.nombre }}</option>
      {% endfor %}
    </select></label>
  <button type="submit">Ver</button>
</form>

<form method="post" action="/grilla">
  <input type="hidden" name="anio" value="{{ anio }}">
  <input type="hidden" name="mes" value="{{ mes }}">
  {% if grupo_id %}<input type="hidden" name="grupo_id" value="{{ grupo_id }}">{% endif %}

  <table>
    <tr>
      <th>Publicador</th><th>Participó</th><th>Cursos</th>
      <th>Prec. auxiliar</th><th>Horas</th><th>Notas</th>
    </tr>
    {% for publicador, registro, horas_habilitadas in filas %}
    <tr>
      <td>
        <input type="hidden" name="publicadores" value="{{ publicador.id }}">
        <a href="/publicadores/{{ publicador.id }}">{{ publicador.nombre_completo }}</a>
      </td>
      <td><input type="checkbox" name="participo_{{ publicador.id }}" value="1"
            {% if registro and registro.participo %}checked{% endif %}></td>
      <td><input type="number" min="0" name="cursos_{{ publicador.id }}"
            value="{{ registro.cursos_biblicos if registro and registro.cursos_biblicos is not none else '' }}"></td>
      <td><input type="checkbox" name="auxiliar_{{ publicador.id }}" value="1"
            {% if registro and registro.precursor_auxiliar %}checked{% endif %}></td>
      <td><input type="number" min="0" name="horas_{{ publicador.id }}"
            value="{{ registro.horas if registro and registro.horas is not none else '' }}"
            {% if not horas_habilitadas %}disabled{% endif %}></td>
      <td><input name="notas_{{ publicador.id }}" value="{{ registro.notas or '' if registro else '' }}"></td>
    </tr>
    {% else %}
    <tr><td colspan="6">No hay publicadores que mostrar.</td></tr>
    {% endfor %}
  </table>

  <button type="submit">Guardar mes</button>
</form>

<p>Las horas se habilitan al guardar el mes si marcas precursor auxiliar, o si el
publicador tiene un nombramiento de precursor o misionero vigente.</p>
{% endblock %}
```

- [ ] **Step 5: Montar el router en `app/main.py`**

```python
from app.web.routers import grilla, grupos, inicio, publicadores, sesion
...
app.include_router(grilla.router)
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `pytest tests/web/test_grilla.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/web/routers/grilla.py app/web/templates/grilla.html tests/web/test_grilla.py app/main.py
git commit -m "feat: grilla de carga mensual con guardado en un solo POST"
```

---

## Task 18: Plantilla, tarjeta y exportación a PDF

**Files:**
- Create: `app/services/tarjetas.py`, `app/web/routers/tarjetas.py`, `app/web/templates/plantilla_falta.html`, `app/web/templates/tarjeta.html`, `app/web/templates/exportar.html`, `tests/services/test_tarjetas.py`, `tests/web/test_exportar_web.py`
- Modify: `app/main.py`, `app/web/templates/publicador_detalle.html` (enlace a la tarjeta)

**Interfaces:**
- Consumes: `app.pdf.plantilla`, `app.pdf.exportar`, `app.services.registros`, `app.config.Config.ruta_plantilla`
- Produces:
  - `app.services.tarjetas.PlantillaAusente` (excepción)
  - `app.services.tarjetas.hay_plantilla() -> bool`
  - `app.services.tarjetas.guardar_plantilla(contenido: bytes) -> None`
  - `app.services.tarjetas.pdf_de(sesion, publicador_id, anio_servicio, *, aplanado=False) -> tuple[str, bytes]` (escribe antes las notas sugeridas de cambio de privilegio)
  - `app.services.tarjetas.zip_de(sesion, publicador_ids, anio_servicio, *, aplanado=False) -> bytes`
  - `app.services.tarjetas.pdf_combinado(sesion, publicador_ids, anio_servicio, *, aplanado=False) -> bytes`
  - Rutas: `GET /plantilla`, `POST /plantilla`, `GET /publicadores/{id}/tarjeta/{anio}`, `GET /publicadores/{id}/tarjeta/{anio}.pdf`, `GET /exportar`, `POST /exportar`

- [ ] **Step 1: Escribir el test de servicio que falla**

`tests/services/test_tarjetas.py`:

```python
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfReader

from app.pdf import importar
from app.services import nombramientos, publicadores, registros, tarjetas


@pytest.fixture(autouse=True)
def plantilla_en_data(tmp_path, monkeypatch, plantilla_sintetica):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import cargar_config

    (tmp_path / "plantilla_s21.pdf").write_bytes(plantilla_sintetica.read_bytes())
    return cargar_config()


def _ana(sesion):
    ana = publicadores.crear(
        sesion, "Pérez Gómez Ana María", sexo="M", fecha_bautismo=date(2010, 4, 3)
    )
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 9, 1))
    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)]
    )
    return ana


def test_hay_plantilla(plantilla_en_data):
    assert tarjetas.hay_plantilla() is True


def test_pdf_de_devuelve_nombre_y_contenido(sesion):
    ana = _ana(sesion)

    nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert nombre == "Pérez Gómez Ana María - 2026.pdf"
    leida = importar.leer_tarjeta(contenido)
    assert leida.nombre == "Pérez Gómez Ana María"
    assert leida.mes(9).horas == 52
    assert leida.nombramientos == {"precursor_regular"}


def test_pdf_aplanado_no_tiene_formulario(sesion):
    ana = _ana(sesion)

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026, aplanado=True)

    assert PdfReader(BytesIO(contenido)).get_fields() in (None, {})


def test_zip_trae_un_pdf_por_publicador(sesion):
    ana = _ana(sesion)
    luis = publicadores.crear(sesion, "Soto Luis")

    contenido = tarjetas.zip_de(sesion, [ana.id, luis.id], 2026)

    with ZipFile(BytesIO(contenido)) as archivo:
        assert sorted(archivo.namelist()) == [
            "Pérez Gómez Ana María - 2026.pdf",
            "Soto Luis - 2026.pdf",
        ]


def test_pdf_combinado_tiene_una_pagina_por_publicador(sesion):
    ana = _ana(sesion)
    luis = publicadores.crear(sesion, "Soto Luis")

    contenido = tarjetas.pdf_combinado(sesion, [ana.id, luis.id], 2026)

    assert len(PdfReader(BytesIO(contenido)).pages) == 2


def test_exportar_escribe_la_nota_de_cambio_de_privilegio(sesion):
    ana = _ana(sesion)  # nombrada precursora regular el 01.09.2025

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert importar.leer_tarjeta(contenido).mes(9).notas == "nombrado precursor regular"


def test_exportar_no_pisa_una_nota_escrita_a_mano(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52,
                              notas="escrito a mano")],
    )

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert importar.leer_tarjeta(contenido).mes(9).notas == "escrito a mano"


def test_sin_plantilla_lanza(sesion, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "vacio"))
    ana = _ana(sesion)

    with pytest.raises(tarjetas.PlantillaAusente):
        tarjetas.pdf_de(sesion, ana.id, 2026)


def test_guardar_plantilla_la_deja_en_blanco(tmp_path, monkeypatch, plantilla_sintetica):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "nueva"))

    tarjetas.guardar_plantilla(plantilla_sintetica.read_bytes())

    assert tarjetas.hay_plantilla() is True
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/services/test_tarjetas.py -v`
Expected: FAIL con `ImportError: cannot import name 'tarjetas'`

- [ ] **Step 3: Crear `app/services/tarjetas.py`**

```python
"""Puente entre la base de datos y la capa PDF."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from pypdf import PdfWriter
from sqlmodel import Session

from app.config import cargar_config
from app.pdf import exportar, plantilla
from app.services import registros


class PlantillaAusente(Exception):
    pass


def hay_plantilla() -> bool:
    return cargar_config().ruta_plantilla.exists()


def guardar_plantilla(contenido: bytes) -> None:
    """Vacía la tarjeta recibida y la deja como plantilla en el volumen de datos."""
    ruta = cargar_config().ruta_plantilla
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(plantilla.crear_plantilla(contenido))


def _plantilla() -> bytes:
    ruta = cargar_config().ruta_plantilla
    if not ruta.exists():
        raise PlantillaAusente(
            "todavía no hay plantilla; sube una tarjeta S-21 en /plantilla"
        )
    return ruta.read_bytes()


def pdf_de(
    sesion: Session, publicador_id: int, anio_servicio: int, *, aplanado: bool = False
) -> tuple[str, bytes]:
    base = _plantilla()
    # deja escrita la nota de cambio de privilegio donde la nota esté vacía
    registros.aplicar_notas_sugeridas(sesion, publicador_id, anio_servicio)
    datos = registros.tarjeta(sesion, publicador_id, anio_servicio)
    contenido = exportar.rellenar(base, datos)
    if aplanado:
        contenido = exportar.aplanar(contenido)
    return exportar.nombre_archivo(datos.nombre, anio_servicio), contenido


def zip_de(
    sesion: Session,
    publicador_ids: list[int],
    anio_servicio: int,
    *,
    aplanado: bool = False,
) -> bytes:
    salida = BytesIO()
    with ZipFile(salida, "w", ZIP_DEFLATED) as archivo:
        for publicador_id in publicador_ids:
            nombre, contenido = pdf_de(
                sesion, publicador_id, anio_servicio, aplanado=aplanado
            )
            archivo.writestr(nombre, contenido)
    return salida.getvalue()


def pdf_combinado(
    sesion: Session,
    publicador_ids: list[int],
    anio_servicio: int,
    *,
    aplanado: bool = False,
) -> bytes:
    escritor = PdfWriter()
    for publicador_id in publicador_ids:
        _nombre, contenido = pdf_de(
            sesion, publicador_id, anio_servicio, aplanado=aplanado
        )
        escritor.append(BytesIO(contenido))
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/services/test_tarjetas.py -v`
Expected: PASS

- [ ] **Step 5: Escribir el test web que falla**

`tests/web/test_exportar_web.py`:

```python
from io import BytesIO

from pypdf import PdfReader

from tests.fixtures.sintetico import crear_s21_sintetico


def _subir_plantilla(cliente, tmp_path):
    ruta = crear_s21_sintetico(tmp_path / "para_subir.pdf")
    return cliente.post(
        "/plantilla",
        files={"archivo": ("s21.pdf", ruta.read_bytes(), "application/pdf")},
        follow_redirects=True,
    )


def test_sin_plantilla_exportar_redirige_al_bootstrap(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/plantilla"


def test_subir_la_plantilla_y_exportar(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "Perez Ana - 2026.pdf" in respuesta.headers["content-disposition"]
    assert len(PdfReader(BytesIO(respuesta.content)).get_fields() or {}) == 75


def test_exportar_aplanado(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf", params={"aplanado": "1"})

    assert PdfReader(BytesIO(respuesta.content)).get_fields() in (None, {})


def test_la_vista_de_tarjeta_muestra_los_doce_meses(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026")

    assert "Septiembre" in respuesta.text
    assert "Agosto" in respuesta.text


def test_exportar_en_lote_devuelve_un_zip(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/publicadores", data={"nombre_completo": "Soto Luis"})

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "zip"}
    )

    assert respuesta.headers["content-type"] == "application/zip"


def test_exportar_en_lote_combinado_devuelve_un_pdf(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/publicadores", data={"nombre_completo": "Soto Luis"})

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "combinado"}
    )

    assert len(PdfReader(BytesIO(respuesta.content)).pages) == 2
```

- [ ] **Step 6: Correr el test y verificar que falla**

Run: `pytest tests/web/test_exportar_web.py -v`
Expected: FAIL con 404 en `/plantilla`

- [ ] **Step 7: Crear `app/web/routers/tarjetas.py`**

```python
from datetime import date

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
from app.web.plantillas import plantillas

router = APIRouter()


def _adjunto(nombre: str, contenido: bytes, tipo: str) -> Response:
    return Response(
        content=contenido,
        media_type=tipo,
        headers={"content-disposition": f'attachment; filename="{nombre}"'},
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
    try:
        servicio.guardar_plantilla(archivo.file.read())
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
```

- [ ] **Step 8: Crear las plantillas**

`app/web/templates/plantilla_falta.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Plantilla del formulario S-21</h1>

{% if hay_plantilla %}
<p>Ya hay una plantilla guardada. Puedes reemplazarla subiendo otra tarjeta.</p>
{% else %}
<p>Para generar tarjetas hace falta el formulario oficial. Sube cualquier tarjeta
S-21 rellenable, llena o vacía: la aplicación le borra los datos y guarda solo el
formulario en blanco.</p>
{% endif %}

{% if error %}<p class="error">{{ error }}</p>{% endif %}

<form method="post" action="/plantilla" enctype="multipart/form-data">
  <input type="file" name="archivo" accept="application/pdf" required>
  <button type="submit">Guardar plantilla</button>
</form>
{% endblock %}
```

`app/web/templates/tarjeta.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>{{ publicador.nombre_completo }} — año {{ anio_servicio }}</h1>

<p>
  <a href="/publicadores/{{ publicador.id }}/tarjeta/{{ anio_servicio }}.pdf">PDF</a>
  ·
  <a href="/publicadores/{{ publicador.id }}/tarjeta/{{ anio_servicio }}.pdf?aplanado=1">PDF solo lectura</a>
  ·
  <a href="/publicadores/{{ publicador.id }}/tarjeta/{{ anio_servicio - 1 }}">← {{ anio_servicio - 1 }}</a>
  ·
  <a href="/publicadores/{{ publicador.id }}/tarjeta/{{ anio_servicio + 1 }}">{{ anio_servicio + 1 }} →</a>
</p>

<table>
  <tr><th>Mes</th><th>Participó</th><th>Cursos</th><th>Prec. auxiliar</th><th>Horas</th><th>Notas</th></tr>
  {% for fila in tarjeta.meses %}
  <tr>
    <td>{{ fila.mes | mes_nombre }}</td>
    <td>{{ 'sí' if fila.participo else '' }}</td>
    <td class="numero">{{ fila.cursos_biblicos if fila.cursos_biblicos is not none else '' }}</td>
    <td>{{ 'sí' if fila.precursor_auxiliar else '' }}</td>
    <td class="numero">{{ fila.horas if fila.horas is not none else '' }}</td>
    <td>{{ fila.notas or '' }}</td>
  </tr>
  {% endfor %}
  <tr><th>Total</th><td colspan="3"></td>
      <td class="numero">{{ tarjeta.total_horas() if tarjeta.total_horas() is not none else '' }}</td>
      <td></td></tr>
</table>
{% endblock %}
```

`app/web/templates/exportar.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Exportar tarjetas</h1>

<form method="post" action="/exportar">
  <label>Año de servicio
    <input type="number" name="anio_servicio" value="{{ anio_servicio }}" required></label>
  <label>Grupo
    <select name="grupo_id"><option value="">Toda la congregación</option>
      {% for grupo in grupos %}<option value="{{ grupo.id }}">{{ grupo.nombre }}</option>{% endfor %}
    </select></label>
  <label>Formato
    <select name="formato">
      <option value="zip">ZIP con un PDF por publicador</option>
      <option value="combinado">Un solo PDF para imprimir</option>
    </select></label>
  <label><input type="checkbox" name="aplanado" value="true"> Solo lectura (aplanado)</label>
  <button type="submit">Exportar</button>
</form>
{% endblock %}
```

- [ ] **Step 9: Enlazar la tarjeta desde el detalle del publicador**

Añadir después del `<h1>` en `app/web/templates/publicador_detalle.html`:

```html
<p>Tarjetas:
  {% for anio in [2024, 2025, 2026, 2027] %}
  <a href="/publicadores/{{ publicador.id }}/tarjeta/{{ anio }}">{{ anio }}</a>
  {% endfor %}
</p>
```

- [ ] **Step 10: Montar el router y añadir el enlace de exportación al menú**

En `app/main.py` añadir `tarjetas` a los imports de routers y `app.include_router(tarjetas.router)`.
En `app/web/templates/base.html`, añadir `<a href="/exportar">Exportar</a>` después del enlace de Importar.

- [ ] **Step 11: Correr los tests y verificar que pasan**

Run: `pytest tests/services/test_tarjetas.py tests/web -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add app/services/tarjetas.py app/web tests/services/test_tarjetas.py tests/web/test_exportar_web.py app/main.py
git commit -m "feat: bootstrap de plantilla y exportación de tarjetas individuales y en lote"
```

---

## Task 19: Pantalla de importación

**Files:**
- Modify: `app/services/importacion.py` (añadir el manejo de lotes en disco)
- Create: `app/web/routers/importar.py`, `app/web/templates/importar.html`, `app/web/templates/importar_revision.html`, `tests/web/test_importar_web.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `app.services.importacion`
- Produces:
  - `app.services.importacion.guardar_lote(archivos: list[tuple[str, bytes]]) -> str`
  - `app.services.importacion.archivos_del_lote(lote: str) -> list[tuple[str, bytes]]`
  - `app.services.importacion.borrar_lote(lote: str) -> None`
  - Rutas: `GET /importar`, `POST /importar`, `GET /importar/{lote}`, `POST /importar/{lote}`, `POST /importar/{lote}/deshacer`

El lote se guarda en `data/subidas/<lote>/` y la propuesta se recalcula al mostrar
la revisión y al aplicarla. Así no hay estado en la sesión y recargar la página de
revisión nunca deja datos a medio escribir.

Nombres de los campos del formulario de revisión, con `i` = índice del archivo:
`destino_{i}` (`nuevo`, `omitir` o el id del publicador), `campo_{i}_{campo}`,
`nombramiento_{i}_{tipo}`, `desde_{i}_{tipo}`, `mes_{i}_{mes}`.

- [ ] **Step 1: Escribir el test que falla**

`tests/web/test_importar_web.py`:

```python
from io import BytesIO

from pypdf import PdfWriter

from app.pdf import campos
from tests.fixtures.sintetico import crear_s21_sintetico


def _tarjeta_bytes(tmp_path, nombre: str, anio: str = "2025") -> bytes:
    base = crear_s21_sintetico(tmp_path / f"{nombre}.pdf")
    escritor = PdfWriter(clone_from=str(base))
    escritor.update_page_form_field_values(
        escritor.pages[0],
        {
            campos.CABECERA_TEXTO["nombre"]: nombre,
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: anio,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
        auto_regenerate=False,
    )
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def _subir(cliente, tmp_path, nombres: list[str]):
    archivos = [
        ("archivos", (f"{nombre}.pdf", _tarjeta_bytes(tmp_path, nombre), "application/pdf"))
        for nombre in nombres
    ]
    return cliente.post("/importar", files=archivos, follow_redirects=True)


def test_la_pantalla_de_importar_carga(cliente):
    assert cliente.get("/importar").status_code == 200


def test_subir_lleva_a_la_revision_sin_escribir_nada(cliente, tmp_path):
    respuesta = _subir(cliente, tmp_path, ["Rojas Mauricio"])

    assert "Rojas Mauricio" in respuesta.text
    assert "Crear nuevo" in respuesta.text
    # nada en la base todavía
    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_rechaza_un_pdf_que_no_es_s21(cliente):
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)

    respuesta = cliente.post(
        "/importar",
        files=[("archivos", ("cualquiera.pdf", buffer.getvalue(), "application/pdf"))],
        follow_redirects=True,
    )

    assert "no es una tarjeta S-21 rellenable" in respuesta.text


def test_aplicar_la_revision_crea_el_publicador_y_sus_registros(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]

    cliente.post(
        f"/importar/{lote}",
        data={
            "destino_0": "nuevo",
            "campo_0_fecha_bautismo": "1",
            "nombramiento_0_siervo_ministerial": "1",
            "desde_0_siervo_ministerial": "2024-09-01",
            "mes_0_9": "1",
        },
        follow_redirects=True,
    )

    assert "Rojas Mauricio" in cliente.get("/publicadores").text
    assert "siervo ministerial" in cliente.get("/publicadores/1").text
    assert "15" in cliente.get("/publicadores/1/tarjeta/2025").text


def test_omitir_un_archivo_no_escribe_nada(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]

    cliente.post(f"/importar/{lote}", data={"destino_0": "omitir"}, follow_redirects=True)

    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_deshacer_revierte_el_lote(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]
    cliente.post(
        f"/importar/{lote}",
        data={"destino_0": "nuevo", "mes_0_9": "1"},
        follow_redirects=True,
    )

    cliente.post(f"/importar/{lote}/deshacer", follow_redirects=True)

    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_el_historial_lista_el_lote_aplicado(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]
    cliente.post(f"/importar/{lote}", data={"destino_0": "nuevo"}, follow_redirects=True)

    assert lote in cliente.get("/importar").text


def test_importar_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/importar", follow_redirects=False).status_code == 303
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/web/test_importar_web.py -v`
Expected: FAIL con 404 en `/importar`

- [ ] **Step 3: Añadir el manejo de lotes a `app/services/importacion.py`**

Añadir los imports `import shutil`, `import uuid` y `from pathlib import Path`, más
`from app.config import cargar_config`, y al final del archivo:

```python
def _directorio_lotes() -> Path:
    return cargar_config().data_dir / "subidas"


def guardar_lote(archivos: list[tuple[str, bytes]]) -> str:
    """Deja los PDF subidos en disco y devuelve el identificador del lote."""
    lote = uuid.uuid4().hex[:12]
    destino = _directorio_lotes() / lote
    destino.mkdir(parents=True, exist_ok=True)
    for indice, (nombre, contenido) in enumerate(archivos):
        # el índice conserva el orden y evita choques de nombre
        (destino / f"{indice:03d}_{Path(nombre).name}").write_bytes(contenido)
    return lote


def archivos_del_lote(lote: str) -> list[tuple[str, bytes]]:
    directorio = _directorio_lotes() / lote
    if not directorio.exists():
        return []
    return [
        (ruta.name.split("_", 1)[1], ruta.read_bytes())
        for ruta in sorted(directorio.iterdir())
    ]


def borrar_lote(lote: str) -> None:
    shutil.rmtree(_directorio_lotes() / lote, ignore_errors=True)
```

- [ ] **Step 4: Crear `app/web/routers/importar.py`**

```python
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
    contenidos = [(archivo.filename or "sin-nombre.pdf", archivo.file.read()) for archivo in archivos]

    errores = []
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
```

- [ ] **Step 5: Crear las plantillas**

`app/web/templates/importar.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Importar tarjetas</h1>

{% for error in errores %}<p class="error">{{ error }}</p>{% endfor %}

<form method="post" action="/importar" enctype="multipart/form-data">
  <input type="file" name="archivos" accept="application/pdf" multiple required>
  <button type="submit">Subir y revisar</button>
</form>

<h2>Importaciones anteriores</h2>
{% if historial %}
<table>
  <tr><th>Lote</th><th>Fecha</th><th>Archivos</th><th></th></tr>
  {% for lote, fecha, cantidad in historial %}
  <tr>
    <td>{{ lote }}</td><td>{{ fecha.strftime('%d.%m.%Y %H:%M') }}</td><td>{{ cantidad }}</td>
    <td>
      <form method="post" action="/importar/{{ lote }}/deshacer">
        <button type="submit">Deshacer</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>Todavía no se ha importado nada.</p>
{% endif %}
{% endblock %}
```

`app/web/templates/importar_revision.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Revisar {{ propuestas | length }} archivo(s)</h1>
<p>Nada se guarda hasta que confirmes al final de la página.</p>

<form method="post" action="/importar/{{ lote }}">
{% for propuesta in propuestas %}
{% set i = loop.index0 %}
<section>
  <h2>{{ propuesta.archivo }} — {{ propuesta.datos.nombre }}
      (año {{ propuesta.datos.anio_servicio or 'sin año' }})</h2>

  {% if propuesta.ya_importado %}
  <p class="error">Este archivo ya se importó el
    {{ propuesta.ya_importado.strftime('%d.%m.%Y %H:%M') }}.</p>
  {% endif %}

  <label>Destino
    <select name="destino_{{ i }}">
      <option value="nuevo" {% if not propuesta.publicador_id %}selected{% endif %}>Crear nuevo</option>
      {% for p in publicadores %}
      <option value="{{ p.id }}" {% if propuesta.publicador_id == p.id %}selected{% endif %}>{{ p.nombre_completo }}</option>
      {% endfor %}
      <option value="omitir">Omitir este archivo</option>
    </select>
  </label>

  {% if propuesta.diferencias %}
  <h3>Datos que cambian</h3>
  <table>
    <tr><th>Aceptar</th><th>Campo</th><th>En la base</th><th>En la tarjeta</th></tr>
    {% for d in propuesta.diferencias %}
    <tr>
      <td><input type="checkbox" name="campo_{{ i }}_{{ d.campo }}" value="1" checked></td>
      <td>{{ d.etiqueta }}</td><td>{{ d.valor_actual or '—' }}</td><td>{{ d.valor_tarjeta }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endif %}

  {% if propuesta.nombramientos %}
  <h3>Nombramientos propuestos</h3>
  {% for n in propuesta.nombramientos %}
  <label>
    <input type="checkbox" name="nombramiento_{{ i }}_{{ n.tipo }}" value="1" checked>
    {{ etiquetas[n.tipo] }} desde
    <input type="date" name="desde_{{ i }}_{{ n.tipo }}" value="{{ n.desde }}">
  </label>
  {% endfor %}
  {% endif %}

  <h3>Meses</h3>
  <table>
    <tr><th>Importar</th><th>Mes</th><th>Participó</th><th>Cursos</th>
        <th>Aux.</th><th>Horas</th><th>Notas</th></tr>
    {% for fila in propuesta.datos.meses %}
    <tr {% if fila.mes in propuesta.meses_en_conflicto %}class="conflicto"{% endif %}>
      <td><input type="checkbox" name="mes_{{ i }}_{{ fila.mes }}" value="1" checked></td>
      <td>{{ fila.mes | mes_nombre }}</td>
      <td>{{ 'sí' if fila.participo else '' }}</td>
      <td class="numero">{{ fila.cursos_biblicos if fila.cursos_biblicos is not none else '' }}</td>
      <td>{{ 'sí' if fila.precursor_auxiliar else '' }}</td>
      <td class="numero">{{ fila.horas if fila.horas is not none else '' }}</td>
      <td>{{ fila.notas or '' }}</td>
    </tr>
    {% endfor %}
  </table>
  {% if propuesta.meses_en_conflicto %}
  <p class="error">Las filas destacadas pisarían un registro distinto que ya está
    guardado. Desmarca las que no quieras reemplazar.</p>
  {% endif %}
</section>
<hr>
{% endfor %}

<button type="submit">Confirmar importación</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Montar el router en `app/main.py`**

Añadir `importar` a los imports de routers y `app.include_router(importar.router)`.

- [ ] **Step 7: Correr los tests y verificar que pasan**

Run: `pytest tests/web/test_importar_web.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/services/importacion.py app/web tests/web/test_importar_web.py app/main.py
git commit -m "feat: pantalla de importación con revisión previa y deshacer"
```

---

## Task 20: Informe, alertas, respaldo y cierre

**Files:**
- Create: `app/web/routers/informes.py`, `app/web/templates/informe.html`, `app/web/templates/alertas.html`, `tests/web/test_informe_web.py`, `README.md`
- Modify: `app/main.py`, `app/web/templates/base.html`

**Interfaces:**
- Consumes: `app.services.informe`, `app.services.alertas`, `app.config.Config.ruta_db`
- Produces: rutas `GET /informe` (parámetros `anio`, `mes`), `GET /informe/anual` (parámetro `anio_servicio`), `GET /alertas`, `GET /respaldo`

- [ ] **Step 1: Escribir el test que falla**

`tests/web/test_informe_web.py`:

```python
def test_el_informe_del_mes_carga(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/grilla",
        data={"anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
              "cursos_1": "3"},
        follow_redirects=True,
    )

    respuesta = cliente.get("/informe", params={"anio": 2026, "mes": 1})

    assert respuesta.status_code == 200
    assert "Publicadores" in respuesta.text
    assert "Enero de 2026" in respuesta.text


def test_el_informe_anual_trae_los_doce_meses(cliente):
    respuesta = cliente.get("/informe/anual", params={"anio_servicio": 2026})

    assert "Septiembre" in respuesta.text
    assert "Agosto" in respuesta.text


def test_alertas_lista_a_los_inactivos(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/alertas")

    assert "Perez Ana" in respuesta.text
    assert "inactivo" in respuesta.text


def test_respaldo_descarga_la_base(cliente):
    respuesta = cliente.get("/respaldo")

    assert respuesta.status_code == 200
    assert respuesta.content[:15] == b"SQLite format 3"
    assert "s21.db" in respuesta.headers["content-disposition"]


def test_el_informe_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/informe", follow_redirects=False).status_code == 303
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/web/test_informe_web.py -v`
Expected: FAIL con 404 en `/informe`

- [ ] **Step 3: Crear `app/web/routers/informes.py`**

```python
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from app.auth import requerir_sesion
from app.config import cargar_config
from app.db import obtener_sesion
from app.dominio import anio_servicio_de
from app.services import alertas, informe
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
    anio = anio or hoy.year
    mes = mes or hoy.month
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
    anio_servicio = anio_servicio or anio_servicio_de(hoy.year, hoy.month)
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
```

- [ ] **Step 4: Crear las plantillas**

`app/web/templates/informe.html`:

```html
{% extends "base.html" %}
{% block contenido %}
{% if informe %}
<h1>{{ mes | mes_nombre }} de {{ anio }}</h1>

<form method="get" action="/informe">
  <label>Mes
    <select name="mes">
      {% for m in [1,2,3,4,5,6,7,8,9,10,11,12] %}
      <option value="{{ m }}" {% if m == mes %}selected{% endif %}>{{ m | mes_nombre }}</option>
      {% endfor %}
    </select></label>
  <label>Año <input type="number" name="anio" value="{{ anio }}"></label>
  <button type="submit">Ver</button>
</form>

<table>
  <tr><th></th><th class="numero">Informaron</th><th class="numero">Cursos</th>
      <th class="numero">Horas</th></tr>
  {% for fila in informe.filas %}
  <tr>
    <td>{{ fila.etiqueta }}</td>
    <td class="numero">{{ fila.informaron }}</td>
    <td class="numero">{{ fila.cursos }}</td>
    <td class="numero">{{ fila.horas if fila.horas is not none else '—' }}</td>
  </tr>
  {% endfor %}
  <tr>
    <th>Total</th>
    <td class="numero">{{ informe.total_informaron }}</td>
    <td class="numero">{{ informe.total_cursos }}</td>
    <td class="numero">{{ informe.total_horas }}</td>
  </tr>
  <tr><td>No informaron</td><td class="numero">{{ informe.no_informaron }}</td><td></td><td></td></tr>
  <tr><td>Promedio horas precursor regular</td><td></td><td></td>
      <td class="numero">{{ informe.promedio_horas_precursor_regular if informe.promedio_horas_precursor_regular is not none else '—' }}</td></tr>
</table>

<p><a href="/informe/anual">Ver el año completo</a></p>
{% else %}
<h1>Año de servicio {{ anio_servicio }}</h1>

<table>
  <tr>
    <th>Mes</th><th class="numero">Informaron</th><th class="numero">No informaron</th>
    <th class="numero">Cursos</th><th class="numero">Horas</th>
  </tr>
  {% for mensual in anual %}
  <tr>
    <td><a href="/informe?anio={{ mensual.anio }}&amp;mes={{ mensual.mes }}">{{ mensual.mes | mes_nombre }}</a></td>
    <td class="numero">{{ mensual.total_informaron }}</td>
    <td class="numero">{{ mensual.no_informaron }}</td>
    <td class="numero">{{ mensual.total_cursos }}</td>
    <td class="numero">{{ mensual.total_horas }}</td>
  </tr>
  {% endfor %}
</table>
{% endif %}
{% endblock %}
```

`app/web/templates/alertas.html`:

```html
{% extends "base.html" %}
{% block contenido %}
<h1>Alertas</h1>

{% if alertas %}
<table>
  <tr><th>Publicador</th><th>Estado</th><th>Meses sin informar</th></tr>
  {% for alerta in alertas %}
  <tr>
    <td><a href="/publicadores/{{ alerta.publicador.id }}">{{ alerta.publicador.nombre_completo }}</a></td>
    <td>{{ alerta.estado }}</td>
    <td>{% for anio, mes in alerta.meses_sin_informar %}{{ mes | mes_nombre }} {{ anio }}{% if not loop.last %}, {% endif %}{% endfor %}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>Sin publicadores irregulares ni inactivos.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Montar el router y añadir el enlace de respaldo**

En `app/main.py` añadir `informes` a los imports y `app.include_router(informes.router)`.
En `base.html`, añadir `<a href="/respaldo">Respaldo</a>` al final de la barra, antes del formulario de salir.

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `pytest tests/web/test_informe_web.py -v`
Expected: PASS

- [ ] **Step 7: Escribir el README**

`README.md`:

```markdown
# Registros de predicación (S-21)

Aplicación web local para administrar los registros de predicación de una
congregación: importa las tarjetas S-21 en PDF, guarda los datos, permite
editarlos y vuelve a generar las tarjetas cuando se necesitan.

## Puesta en marcha

```bash
cp .env.example .env      # y edita AUTH_USER, AUTH_PASS y SECRET_KEY
docker compose up -d
```

La aplicación queda en <http://localhost:8000>, publicada solo en loopback.

La primera vez pide subir una tarjeta S-21 rellenable (llena o vacía) en
`/plantilla`. La aplicación le borra los datos y guarda el formulario en blanco
en `data/plantilla_s21.pdf`. El formulario oficial no se distribuye con el
proyecto.

## Datos y respaldo

Todo vive en `data/`: la base SQLite (`s21.db`) y la plantilla. El botón
**Respaldo** de la barra superior descarga la base; para restaurarla basta con
dejar el archivo en `data/` y reiniciar.

`data/` está en `.gitignore`: los datos de la congregación no se versionan.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

La prueba que compara el mapa de campos contra el formulario real se salta si no
existe `data/plantilla_s21.pdf`. En el equipo donde sí existe, es la que avisa
primero si aparece una versión nueva del S-21.

## Documentos

- Diseño: `docs/superpowers/specs/2026-09-09-gestion-registros-predicacion-design.md`
- Plan: `docs/superpowers/plans/2026-09-09-gestion-registros-predicacion.md`
```

- [ ] **Step 8: Correr toda la suite**

Run: `pytest -v`
Expected: PASS, con un único SKIPPED (la prueba contra el formulario real)

- [ ] **Step 9: Verificar la aplicación completa en Docker**

```bash
cp .env.example .env
docker compose up -d --build
sleep 4
curl -s localhost:8000/salud
```

Expected: `{"estado":"ok"}`. Luego, en el navegador: entrar con las credenciales
de `.env`, subir una tarjeta S-21 real en `/plantilla`, importarla desde
`/importar`, confirmar la revisión, y descargar la tarjeta desde el detalle del
publicador en las dos variantes (PDF y PDF solo lectura). **Abrir los dos PDF en
Preview y confirmar que los valores se ven.** Este es el único punto del plan que
requiere comprobación visual: el resto está cubierto por las pruebas.

- [ ] **Step 10: Correr la prueba de contrato contra el formulario real**

Run: `pytest tests/pdf/test_campos.py -v`
Expected: PASS sin SKIPPED, ahora que `data/plantilla_s21.pdf` existe

- [ ] **Step 11: Commit**

```bash
git add app/web tests/web/test_informe_web.py README.md app/main.py
git commit -m "feat: informe mensual y anual, alertas, respaldo y README"
```

---

## Verificación final

- [ ] `pytest` pasa entero
- [ ] `docker compose up -d --build` levanta y `/salud` responde
- [ ] Importar una tarjeta real y volver a exportarla devuelve el mismo contenido
- [ ] Los dos PDF exportados se ven correctos en Preview
- [ ] `git status` limpio y `data/` sin versionar
