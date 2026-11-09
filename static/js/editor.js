const codigo = document.querySelector("#codigo");
const lineas = document.querySelector("#lineas");
const botonAnalizar = document.querySelector("#analizar");
const archivo = document.querySelector("#archivo");
const estado = document.querySelector("#estado");
const listaErrores = document.querySelector("#errores");
let versionCodigo = 0;
let controladorAnalisis = null;

function actualizarLineas() {
  const total = codigo.value.split("\n").length;
  lineas.textContent = Array.from({ length: total }, (_, indice) => indice + 1).join("\n");
}

function invalidarResultados() {
  versionCodigo += 1;
  controladorAnalisis?.abort();
  controladorAnalisis = null;
  botonAnalizar.disabled = false;
  listaErrores.replaceChildren();
  listaErrores.hidden = true;
  estado.textContent = "Código modificado. Analiza para actualizar los resultados.";
  estado.className = "";
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
  const versionAnalizada = versionCodigo;
  const controlador = new AbortController();
  controladorAnalisis = controlador;
  botonAnalizar.disabled = true;
  estado.textContent = "Analizando…";
  estado.className = "";
  try {
    const respuesta = await fetch("/api/analizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigo.value }),
      signal: controlador.signal,
    });
    const resultado = await respuesta.json();
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo analizar el código.");
    if (versionAnalizada !== versionCodigo) return;
    mostrarResultado(resultado);
  } catch (error) {
    if (error.name === "AbortError") return;
    if (versionAnalizada !== versionCodigo) return;
    estado.textContent = error.message;
    estado.className = "error";
    listaErrores.hidden = true;
  } finally {
    if (versionAnalizada === versionCodigo) botonAnalizar.disabled = false;
    if (controladorAnalisis === controlador) controladorAnalisis = null;
  }
}

codigo.addEventListener("input", () => {
  actualizarLineas();
  invalidarResultados();
});
codigo.addEventListener("scroll", () => { lineas.scrollTop = codigo.scrollTop; });
botonAnalizar.addEventListener("click", analizar);
archivo.addEventListener("change", () => {
  const seleccionado = archivo.files[0];
  if (!seleccionado) return;
  const lector = new FileReader();
  lector.onload = () => {
    codigo.value = lector.result;
    actualizarLineas();
    invalidarResultados();
  };
  lector.readAsText(seleccionado);
});
actualizarLineas();
