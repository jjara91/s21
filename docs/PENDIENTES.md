# Pendientes conocidos

Lista de lo que quedó sin cerrar al terminar la implementación, con el criterio
para priorizarlo. Nada de esto impide usar la aplicación.

## Decisión tomada sobre retención de datos

El deshacer de una importación **no caduca**: se puede revertir cualquier
importación de cualquier época. A cambio, `Importacion.estado_previo` conserva
indefinidamente los valores anteriores de los publicadores afectados.

Ya se minimizó lo que no hacía falta para deshacer: el nombre del archivo
original no se guarda, el respaldo se vacía después de deshacer, y los datos de
un publicador borrado se limpian de las filas que lo referenciaban.

## Conviene revisarlo antes de que crezca

- **`/plantilla` no tiene entrada permanente en el menú.** El inicio avisa y
  enlaza mientras no haya plantilla; una vez cargada, el enlace desaparece. Para
  reemplazarla —si cambia la versión oficial del S-21— hay que escribir la URL a
  mano.
- **Consultas N+1 en la grilla y el informe.** Una consulta por publicador para
  saber sus nombramientos. A escala de una congregación es irrelevante; si el
  padrón creciera mucho, se resuelve trayendo los nombramientos de una vez.
- **`aplanar()` usa APIs internas de pypdf.** No hay alternativa pública. Está
  comentado en el código: una actualización de pypdf exige revisar esa función.
  Las versiones están acotadas en `pyproject.toml` precisamente por eso.
- **Un entero enorme en horas o cursos se guarda sin tope de magnitud.** Se
  valida que sea un número, no que sea razonable.

## Cosmético

- El nombre ASCII de respaldo en la descarga descarta las tildes en vez de
  transliterarlas. Solo lo verían navegadores muy antiguos: el nombre real viaja
  en `filename*`.
- `mes_nombre` capitaliza siempre, así que en mitad de una frase queda
  "Cargar Septiembre de 2026" en vez de "septiembre".
- Un lote de importación dejado abierto más de siete días se purga sin avisar; al
  confirmarlo después, la pantalla redirige en silencio en vez de explicar que ya
  no existe.

## Verificación que ningún agente pudo hacer

Abrir en un visor de PDF las dos variantes de tarjeta exportada —editable y de
solo lectura— y confirmar a ojo que se ven bien. Se verificó renderizando con
una librería, pero no en el visor que se usará a diario.
