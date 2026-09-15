// Los formularios de filtro (método GET) marcados con data-filtro envían todos
// sus campos, incluidos los vacíos, y la URL termina con ?texto=&grupo_id=&...
// Un campo deshabilitado no se envía: se deshabilitan los vacíos justo durante
// el submit y se devuelven al estado anterior enseguida, para que la URL quede
// limpia sin que el usuario vea los campos apagarse.
//
// Es solo cosmética de la URL: el servidor sigue aceptando los parámetros
// vacíos (IdOpcional en app/web/errores.py), así que sin JS todo funciona igual.
document.querySelectorAll("form[data-filtro]").forEach((formulario) => {
  formulario.addEventListener("submit", () => {
    const apagados = [];
    for (const campo of formulario.elements) {
      if (!campo.name || campo.disabled) continue;
      if (campo.type === "checkbox" || campo.type === "radio") continue;
      if (campo.value === "") {
        campo.disabled = true;
        apagados.push(campo);
      }
    }
    // El navegador ya serializó el formulario cuando termina este manejador.
    setTimeout(() => apagados.forEach((campo) => (campo.disabled = false)), 0);
  });
});
