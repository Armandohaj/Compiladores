const codigo = document.querySelector("#codigo");
const lineas = document.querySelector("#lineas");
const botonAnalizar = document.querySelector("#analizar");
const botonEjecutar = document.querySelector("#ejecutar");
const archivo = document.querySelector("#archivo");
const estado = document.querySelector("#estado");
const listaErrores = document.querySelector("#errores");
const LIMITE_EJECUCION_MS = 3000;

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

function mostrarMensaje(mensaje, clase = "") {
  listaErrores.replaceChildren();
  listaErrores.hidden = true;
  estado.textContent = mensaje;
  estado.className = clase;
}

// Convierte la respuesta Base64 del servidor al buffer transferible del Worker.
function decodificarWasm(wasmBase64) {
  const binario = atob(wasmBase64);
  const bytes = new Uint8Array(binario.length);
  for (let indice = 0; indice < binario.length; indice += 1) {
    bytes[indice] = binario.charCodeAt(indice);
  }
  return bytes.buffer;
}

// Termina el Worker al recibir un resultado o al superar el límite de ejecución.
function ejecutarEnWorker(wasm) {
  return new Promise((resolver, rechazar) => {
    const worker = new Worker("/static/js/ejecutor-wasm.js");
    const limite = window.setTimeout(() => {
      worker.terminate();
      rechazar(new Error("La ejecución superó el límite de 3 segundos."));
    }, LIMITE_EJECUCION_MS);

    function finalizar() {
      window.clearTimeout(limite);
      worker.terminate();
    }

    worker.onmessage = ({ data }) => {
      finalizar();
      if (data.error) {
        rechazar(new Error(data.error));
        return;
      }
      resolver(data.valor);
    };
    worker.onerror = () => {
      finalizar();
      rechazar(new Error("No se pudo ejecutar el módulo WebAssembly."));
    };
    worker.postMessage({ wasm }, [wasm]);
  });
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

async function ejecutar() {
  const codigoEnviado = codigo.value;
  botonEjecutar.disabled = true;
  mostrarMensaje("Compilando para ejecutar…");
  try {
    const respuesta = await fetch("/api/compilar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigoEnviado }),
    });
    const resultado = await respuesta.json();
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo compilar el programa.");
    if (!resultado.valido) {
      mostrarResultado(resultado);
      return;
    }
    // La firma llega del análisis semántico; no se infiere desde el texto fuente.
    if (!resultado.main || resultado.main.parametros.length !== 0 || resultado.main.retorno !== "i32") {
      mostrarMensaje("Por ahora solo se puede ejecutar main() sin parámetros que retorne i32.", "error");
      return;
    }
    if (codigo.value !== codigoEnviado) {
      mostrarMensaje("El código cambió durante la compilación. Ejecuta nuevamente.", "error");
      return;
    }
    mostrarMensaje("Ejecutando main()…");
    const valor = await ejecutarEnWorker(decodificarWasm(resultado.wasm_base64));
    mostrarMensaje(`Resultado de main(): ${valor}`, "correcto");
  } catch (error) {
    mostrarMensaje(error.message, "error");
  } finally {
    botonEjecutar.disabled = false;
  }
}

codigo.addEventListener("input", actualizarLineas);
codigo.addEventListener("scroll", () => { lineas.scrollTop = codigo.scrollTop; });
botonAnalizar.addEventListener("click", analizar);
botonEjecutar.addEventListener("click", ejecutar);
archivo.addEventListener("change", () => {
  const seleccionado = archivo.files[0];
  if (!seleccionado) return;
  const lector = new FileReader();
  lector.onload = () => { codigo.value = lector.result; actualizarLineas(); };
  lector.readAsText(seleccionado);
});
actualizarLineas();
