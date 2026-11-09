const codigo = document.querySelector("#codigo");
const lineas = document.querySelector("#lineas");
const botonAnalizar = document.querySelector("#analizar");
const archivo = document.querySelector("#archivo");
const estado = document.querySelector("#estado");
const listaErrores = document.querySelector("#errores");

function actualizarLineas() {
  const total = codigo.value.split("\n").length;
  lineas.textContent = Array.from({ length: total }, (_, indice) => indice + 1).join("\n");
}

function mostrarResultado(resultado) {
  listaErrores.replaceChildren();
  if (resultado.valido) {
    estado.textContent = "El análisis léxico, sintáctico y semántico fue correcto.";
    estado.className = "correcto";
    listaErrores.hidden = true;
    return;
  }

  estado.textContent = `Se encontraron ${resultado.errores.length} error(es).`;
  estado.className = "error";
  resultado.errores.forEach(({ fase, linea, columna, mensaje }) => {
    const item = document.createElement("li");
    item.textContent = `${fase}: línea ${linea}, columna ${columna}: ${mensaje}`;
    listaErrores.append(item);
  });
  listaErrores.hidden = false;
}

async function analizar() {
  botonAnalizar.disabled = true;
  estado.textContent = "Analizando…";
  estado.className = "";
  try {
    const respuesta = await fetch("/api/analizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigo.value }),
    });
    const resultado = await respuesta.json();
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo analizar el código.");
    mostrarResultado(resultado);
  } catch (error) {
    estado.textContent = error.message;
    estado.className = "error";
    listaErrores.hidden = true;
  } finally {
    botonAnalizar.disabled = false;
  }
}

codigo.addEventListener("input", actualizarLineas);
codigo.addEventListener("scroll", () => { lineas.scrollTop = codigo.scrollTop; });
botonAnalizar.addEventListener("click", analizar);
archivo.addEventListener("change", () => {
  const seleccionado = archivo.files[0];
  if (!seleccionado) return;
  const lector = new FileReader();
  lector.onload = () => { codigo.value = lector.result; actualizarLineas(); };
  lector.readAsText(seleccionado);
});
actualizarLineas();
