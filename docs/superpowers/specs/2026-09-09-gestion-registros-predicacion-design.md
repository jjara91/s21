# Gestión de registros de predicación (S-21)

Diseño — 2026-09-09

## Propósito

Aplicación web local, en Docker, para administrar los registros de predicación de
una congregación. Reemplaza el manejo manual de las tarjetas S-21 en PDF:
las importa, guarda los datos en una base de datos, permite editarlos desde la
aplicación y vuelve a generar las tarjetas en PDF cuando se necesitan.

Usuario: una persona (el secretario). Uso: red local, un solo equipo.

## Alcance

Entra en la versión 1:

1. Importar tarjetas S-21 en PDF y extraer sus datos.
2. Mantenedor de publicadores, con nombramientos.
3. Carga de registros mensuales de predicación.
4. Exportar tarjetas S-21 en PDF, individuales o en lote.
5. Informe mensual y anual de la congregación.
6. Grupos de predicación.
7. Alertas de publicadores irregulares e inactivos.

No entra: usuarios múltiples, roles, acceso desde internet, sincronización con
ningún servicio externo, otros formularios oficiales además del S-21.

## Hallazgo que determina el diseño

La tarjeta S-21 no es un documento escaneado. Es un PDF con formulario AcroForm
(`S-21-S 11/23`, autor Watch Tower Bible and Tract Society of Pennsylvania) con
75 campos de nombre estable.

Verificado sobre una tarjeta real:

- Lectura de los 75 campos con `pypdf`, valores correctos.
- Vaciado de la tarjeta a plantilla en blanco: 0 campos con valor.
- Relleno de la plantilla con datos nuevos: round-trip exacto.
- Aplanado por estampado de las apariencias en el contenido de la página:
  0 campos de formulario restantes, valores presentes en el texto.

Consecuencia: importar es leer campos y exportar es rellenar la plantilla
oficial. No hace falta OCR, ni análisis de imagen, ni redibujar la tarjeta. El
PDF generado es visualmente idéntico al oficial.

## Stack

- Python 3.12, FastAPI, SQLModel, SQLite.
- Jinja2 + HTMX para la interfaz. Sin build step de JavaScript.
- `pypdf` para leer y escribir el formulario.
- Un contenedor, un volumen.

Se eligió SQLite porque la base es un archivo: el respaldo es copiarlo y no hay
un segundo servicio que mantener. La concurrencia de un solo usuario no la pone
en aprietos.

## Arquitectura

```
docker-compose.yml     1 servicio, 127.0.0.1:8000, volumen ./data:/data
Dockerfile             python:3.12-slim + uvicorn

app/
  main.py              arranque FastAPI, sesión, montaje de routers
  config.py            AUTH_USER, AUTH_PASS, SECRET_KEY, DATA_DIR
  db.py                engine SQLModel -> /data/s21.db, migraciones al arrancar
  models.py            tablas
  auth.py              login por cookie firmada
  services/
    publicadores.py    CRUD, normalización y match de nombres
    nombramientos.py   alta y baja, vigencia en un año de servicio
    registros.py       carga mensual, totales
    informe.py         agregados por mes y por año
    alertas.py         irregulares e inactivos
  pdf/
    campos.py          mapa nombre de campo PDF <-> concepto de dominio
    plantilla.py       generar la plantilla en blanco desde una tarjeta
    importar.py        PDF -> dict de datos
    exportar.py        datos -> PDF (editable o aplanado)
  web/
    routers/           un router por pantalla
    templates/         Jinja
    static/            HTMX y CSS
data/                  s21.db, plantilla_s21.pdf, subidas/   (en .gitignore)
migrations/            001_inicial.sql, 002_....sql
tests/
```

Límites entre capas:

- `pdf/` no conoce SQL ni HTTP. Recibe y devuelve diccionarios.
- `services/` no conoce HTTP. Recibe y devuelve objetos de dominio.
- `web/routers/` no contiene lógica de negocio; traduce petición a llamada de
  servicio y resultado a plantilla.
- `pdf/campos.py` es el único archivo del proyecto que menciona nombres como
  `900_1_Text_SanSerif`. Una versión nueva del S-21 se absorbe ahí.

## Modelo de datos

```
publicador
  id                   INTEGER PK
  nombre_completo      TEXT      tal como aparece en la tarjeta
  nombre_normalizado   TEXT      índice; minúsculas, sin tildes, espacios colapsados
  fecha_nacimiento     DATE NULL
  fecha_bautismo       DATE NULL
  sexo                 TEXT NULL H | M
  esperanza            TEXT NULL otras_ovejas | ungido
  grupo_id             INTEGER NULL -> grupo
  fecha_baja           DATE NULL
  motivo_baja          TEXT NULL    fallecido | mudado | otro

grupo
  id                   INTEGER PK
  nombre               TEXT
  superintendente_id   INTEGER NULL -> publicador

nombramiento
  id                   INTEGER PK
  publicador_id        INTEGER -> publicador
  tipo                 TEXT   anciano | siervo_ministerial | precursor_regular
                              | precursor_especial | misionero_campo
  desde                DATE
  hasta                DATE NULL     NULL = vigente

registro_mensual
  id                   INTEGER PK
  publicador_id        INTEGER -> publicador
  anio                 INTEGER       año calendario
  mes                  INTEGER       1-12, mes calendario
  participo            BOOLEAN
  cursos_biblicos      INTEGER NULL
  precursor_auxiliar   BOOLEAN
  horas                INTEGER NULL
  notas                TEXT NULL
  UNIQUE (publicador_id, anio, mes)
  -- fila ausente = mes sin cargar; participo=false = cargado y no informó

importacion
  id                   INTEGER PK
  archivo              TEXT
  sha256               TEXT
  fecha                DATETIME
  publicador_id        INTEGER NULL -> publicador
  anio_servicio        INTEGER NULL
  accion               TEXT   creado | actualizado | descartado

schema_version
  version              INTEGER
```

Decisiones dentro del modelo:

- **El año de servicio se deriva, no se almacena.** `registro_mensual` guarda mes
  calendario. `anio_servicio = anio + 1` si `mes >= 9`, si no `anio`. Así un mismo
  mes no puede existir bajo dos años de servicio distintos.
- **Precursor auxiliar no es un nombramiento.** Es una condición mensual y vive en
  `registro_mensual`. Los otros cinco privilegios sí son nombramientos con fecha.
- **`hasta = NULL` significa vigente.**
- **No hay tabla de usuarios.** La credencial única viene de variables de entorno.
- **`nombre_normalizado` es interno.** Se usa solo para el match de importación y
  nunca se muestra en pantalla.

## Reglas de dominio

### Año de servicio

Va del 1 de septiembre al 31 de agosto. El año de servicio N abarca
`[01-09-(N-1), 31-08-N]`. Las filas de la tarjeta van de septiembre a agosto.

### Vigencia de un nombramiento en un año de servicio

Un nombramiento marca la casilla del año N si su intervalo `[desde, hasta]` se
cruza con `[01-09-(N-1), 31-08-N]`, aunque sea por un mes.

Casos borde de referencia:

| Nombramiento | Marca 2025 | Marca 2026 |
|---|---|---|
| `desde 01-09-2025` | no | sí |
| `hasta 31-08-2025` | sí | no |
| `desde 15-07-2025, hasta 20-09-2025` | sí | sí |

### Nota automática de cambio de privilegio

En el mes en que un nombramiento empieza o termina, la aplicación propone un
texto para `registro_mensual.notas`: `nombrado siervo ministerial`,
`deja de ser precursor regular`, y equivalentes por tipo.

La propuesta se guarda solo si esa nota está vacía. Nunca sobrescribe un texto
escrito por el usuario. La nota queda editable como cualquier otra.

### Categoría del publicador en un mes

Para el informe, cada publicador cuenta en una sola categoría por mes. Se aplica
la primera que corresponda, en este orden:

1. Misionero que sirve en el campo
2. Precursor especial
3. Precursor regular
4. Precursor auxiliar
5. Publicador

Las cuatro primeras se determinan por nombramiento vigente en ese mes, salvo
precursor auxiliar, que se determina por la casilla del registro mensual.

### Alertas

La ventana son los 6 meses calendario completos anteriores al mes en curso. Un
mes sin fila en `registro_mensual` cuenta como no informado.

- **Irregular** — informó menos de 6 de esos 6 meses, pero al menos 1.
- **Inactivo** — los 6 sin informar.

Un publicador no puede ser las dos cosas: inactivo excluye irregular.

Los publicadores con `fecha_baja` quedan fuera de alertas y de informes.

## Capa PDF

### Mapa de campos

```python
CABECERA = {
  "nombre":            "900_1_Text_SanSerif",
  "fecha_nacimiento":  "900_2_Text_SanSerif",
  "sexo":              {"H": "900_3_CheckBox", "M": "900_4_CheckBox"},
  "fecha_bautismo":    "900_5_Text_SanSerif",
  "esperanza":         {"otras_ovejas": "900_6_CheckBox", "ungido": "900_7_CheckBox"},
  "nombramientos": {
      "anciano":            "900_8_CheckBox",
      "siervo_ministerial": "900_9_CheckBox",
      "precursor_regular":  "900_10_CheckBox",
      "precursor_especial": "900_11_CheckBox",
      "misionero_campo":    "900_12_CheckBox",
  },
  "anio_servicio":     "900_13_Text_C_SanSerif",
}

# índice de fila: 20 = septiembre ... 31 = agosto, 32 = total
FILA = {
  "participo":          "901_{i}_CheckBox",
  "cursos_biblicos":    "902_{i}_Text_C_SanSerif",
  "precursor_auxiliar": "903_{i}_CheckBox",
  "horas":              "904_{i}_S21_Value",
  "notas":              "905_{i}_Text_SanSerif",
}
TOTAL = {"horas": "904_32_S21_Value", "notas": "905_32_Text_SanSerif"}
```

Las casillas marcadas usan el valor `/Yes`; las desmarcadas, `/Off`.

### Plantilla en blanco

El repositorio no distribuye el formulario oficial. En el primer arranque, si no
existe `/data/plantilla_s21.pdf`, la aplicación pide subir una tarjeta S-21
cualquiera, llena o vacía, borra sus 75 valores y guarda el resultado como
plantilla.

### Importar

```
PDF subido
  -> validar AcroForm con los campos S-21    si no: rechazo
  -> leer campos -> dict {cabecera, 12 meses}
  -> parsear fechas
  -> match por nombre_normalizado
  -> PANTALLA DE REVISIÓN                    nada se escribe antes de este punto
  -> guardar + registrar en `importacion`
```

Formatos de fecha aceptados: `dd.mm.aaaa`, `dd/mm/aaaa`, `aaaa-mm-dd`. Si ninguno
calza, se conserva el texto crudo y el campo se marca para revisión manual.

La pantalla de revisión muestra, por archivo:

- **Destino**: publicador coincidente, crear uno nuevo, o elegir otro de la lista.
- **Cabecera**: solo los campos que difieren de lo que hay en la base, lado a
  lado, con una casilla para aceptar cada uno.
- **Nombramientos**: una casilla marcada en el año N sin nombramiento
  correspondiente en la base propone `desde = 01-09-(N-1)`. La fecha es editable
  y la propuesta se puede descartar.
- **Meses**: las 12 filas, destacando las que pisarían un registro existente con
  un valor distinto.
- **Duplicado**: si el `sha256` ya figura en `importacion`, se avisa la fecha de
  la importación anterior y se permite continuar igual.

Se pueden subir varios archivos de una vez y revisarlos uno tras otro. Cada carga
queda registrada en `importacion`, lo que permite deshacer una importación
completa.

### Exportar

Una tarjeta corresponde a un publicador y un año de servicio. Se rellena la
plantilla.

- Las casillas de nombramiento se marcan según la regla de vigencia de arriba.
- Los 12 meses se llenan desde `registro_mensual`.
- El total de horas (`904_32`) se calcula al exportar como suma de las horas del
  año. La nota del total (`905_32`) se deja vacía; no hay dato en la base que la
  alimente y la tarjeta oficial tampoco la usa.
- **PDF editable**: el AcroForm queda intacto, se escribe con
  `update_page_form_field_values(..., auto_regenerate=True)`.
- **PDF solo lectura**: se estampan las apariencias de cada widget en el
  contenido de la página, se vacía `/Annots` y se elimina `/AcroForm`.
- **Lote**: por grupo o por congregación completa, en un ZIP con un PDF por
  publicador, o en un único PDF combinado para imprimir.
- Nombre de archivo: `Apellidos Nombres - 2026.pdf`.

### Errores de la capa PDF

| Caso | Respuesta |
|---|---|
| PDF sin AcroForm, o escaneado | Rechazo con mensaje explícito; el archivo no se guarda |
| Faltan campos esperados | Rechazo listando cuáles faltan (indica otra versión del S-21) |
| Año de servicio vacío o no numérico | Se pide en la pantalla de revisión |
| Horas o cursos no numéricos | Se marca esa fila; el resto del archivo sigue |
| Plantilla ausente al exportar | Redirección al bootstrap de plantilla |
| `sha256` ya importado | Aviso con la fecha anterior; se permite continuar |

## Pantallas

| Pantalla | Contenido |
|---|---|
| Login | Usuario y clave desde variables de entorno; cookie de sesión firmada |
| Inicio | Año de servicio en curso, alertas pendientes, atajo a la grilla del mes |
| Grilla mensual | Selector de mes y grupo; una fila por publicador con participó, cursos, auxiliar, horas y notas; guardado del mes completo en un POST. El campo de horas se habilita solo si el publicador tiene un nombramiento de precursor o misionero vigente ese mes, o si se marca la casilla de precursor auxiliar en esa misma fila |
| Publicadores | Lista con buscador y filtros por grupo, estado y privilegio. Detalle con datos personales, nombramientos, tarjeta del año y botones de exportación |
| Grupos | CRUD, asignación de superintendente y de publicadores |
| Importar | Subida múltiple, pantalla de revisión, historial de importaciones con opción de deshacer |
| Informe mensual | Agregado del mes por categoría |
| Alertas | Irregulares e inactivos, con el detalle de los meses faltantes |

La grilla mensual es la pantalla de uso diario y es la que se optimiza: tabulable
de campo en campo, sin diálogos intermedios, un solo guardado.

Interfaz en español. HTMX para la grilla y la revisión de importación.

## Informe

Formato del informe mensual:

```
Enero 2026                              Informaron  Cursos  Horas
Publicadores                                    54      12      —
Precursores auxiliares                           7       9    213
Precursores regulares                            4       6    268
Precursores especiales                           0       0      0
Misioneros en el campo                           0       0      0
────────────────────────────────────────────────────────────────
Total                                           65      27    481
No informaron                                    9
Promedio horas precursor regular                                67
```

La columna Horas queda vacía para la fila Publicadores, que no registra horas.

Existe la vista equivalente por año de servicio, con las 12 columnas de meses.

## Pruebas

Desarrollo guiado por pruebas, con pytest.

- **Contrato del formulario** — la plantilla expone los 75 campos esperados. Es la
  prueba que rompe primero si aparece una versión nueva del S-21.
- **Round-trip** — datos a PDF, leer el PDF, obtener los mismos datos. Incluye
  horas vacías, cursos en cero, notas con tildes y nombres largos.
- **Aplanado** — el PDF resultante no tiene campos de formulario y sus valores
  aparecen en el texto de la página.
- **Vigencia de nombramientos** — los casos borde de la tabla de reglas.
- **Nota automática** — se escribe si la nota está vacía; no se escribe si ya hay
  texto.
- **Alertas** — límites exactos de los 6 meses, en ambos sentidos.
- **Informe** — precedencia de categorías: un precursor regular que además fue
  auxiliar cuenta una sola vez.
- **Importación** — match por nombre con tildes y mayúsculas distintas; rechazo de
  PDF sin AcroForm; detección de `sha256` repetido; deshacer una importación.
- **Smoke web** — cada ruta responde, autenticado y sin autenticar.

Los fixtures de PDF se generan rellenando la plantilla en blanco con datos
inventados. Ninguna tarjeta con datos reales entra al repositorio.

## Despliegue y datos

```yaml
services:
  s21:
    build: .
    ports: ["127.0.0.1:8000:8000"]
    volumes: ["./data:/data"]
    environment: [AUTH_USER, AUTH_PASS, SECRET_KEY]
```

- El puerto se publica solo en la interfaz de loopback. La aplicación no queda
  expuesta a la red local salvo que se cambie esa línea a propósito.
- `data/` está en `.gitignore`. Los datos de la congregación no se commitean.
- Esquema: scripts SQL numerados en `migrations/`, aplicados al arrancar y
  registrados en `schema_version`.
- Botón **Descargar respaldo** que entrega el archivo `.db`. Restaurar consiste en
  dejar el archivo en `data/`.
- La aplicación no hace ninguna llamada de red saliente.
