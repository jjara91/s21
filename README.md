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
