const codigo = document.querySelector("#codigo");
const lineas = document.querySelector("#lineas");
const botonAnalizar = document.querySelector("#analizar");
const botonCompilar = document.querySelector("#compilar");
const botonEjecutar = document.querySelector("#ejecutar");
const botonDescargarWasm = document.querySelector("#descargar-wasm");
const campoEntradas = document.querySelector("#entradas");
const archivo = document.querySelector("#archivo");
const estado = document.querySelector("#estado");
const listaErrores = document.querySelector("#errores");
const LIMITE_EJECUCION_MS = 3000;
let wasmCompilado = null;
let revisionCodigo = 0;
let ultimaSolicitudAnalisis = 0;
let ultimaSolicitudCompilacion = 0;
let ultimaAccion = 0;
let ubicacionErrores = null;

function actualizarLineas() {
  const total = codigo.value.split("\n").length;
  lineas.textContent = Array.from({ length: total }, (_, indice) => indice + 1).join("\n");
}

function localizarError(linea, columna) {
  if (!ubicacionErrores
    || ubicacionErrores.revision !== revisionCodigo
    || ubicacionErrores.codigo !== codigo.value) {
    return;
  }
  const lineasCodigo = codigo.value.split("\n");
  const lineaSegura = Math.min(Math.max(Number(linea) || 1, 1), lineasCodigo.length);
  const columnaSegura = Math.min(
    Math.max(Number(columna) || 1, 1), lineasCodigo[lineaSegura - 1].length + 1
  );
  const inicio = lineasCodigo.slice(0, lineaSegura - 1).reduce(
    (total, texto) => total + texto.length + 1, 0
  ) + columnaSegura - 1;
  const fin = inicio < codigo.value.length && codigo.value[inicio] !== "\n" ? inicio + 1 : inicio;
  codigo.focus();
  codigo.setSelectionRange(inicio, fin);
}

function mostrarResultado(resultado) {
  listaErrores.replaceChildren();
  if (resultado.valido) {
    ubicacionErrores = null;
    estado.textContent = "El análisis léxico, sintáctico y semántico fue correcto.";
    estado.className = "correcto";
    listaErrores.hidden = true;
    return;
  }

  estado.textContent = `Se encontraron ${resultado.errores.length} error(es).`;
  estado.className = "error";
  ubicacionErrores = { revision: revisionCodigo, codigo: codigo.value };
  resultado.errores.forEach(({ fase, linea, columna, mensaje }) => {
    const item = document.createElement("li");
    item.textContent = `${fase}: línea ${linea}, columna ${columna}: ${mensaje}`;
    item.tabIndex = 0;
    item.role = "button";
    item.addEventListener("click", () => localizarError(linea, columna));
    item.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        localizarError(linea, columna);
      }
    });
    listaErrores.append(item);
  });
  listaErrores.hidden = false;
}

function mostrarMensaje(mensaje, clase = "") {
  ubicacionErrores = null;
  listaErrores.replaceChildren();
  listaErrores.hidden = true;
  estado.textContent = mensaje;
  estado.className = clase;
}

// Invalida el binario al cambiar el código para evitar descargas desactualizadas.
function invalidarWasm() {
  wasmCompilado = null;
  botonDescargarWasm.disabled = true;
}

function invalidarResultados() {
  // Una respuesta pendiente no debe presentar el análisis de una versión anterior.
  revisionCodigo += 1;
  ubicacionErrores = null;
  listaErrores.replaceChildren();
  listaErrores.hidden = true;
  estado.textContent = "El código cambió. Analiza nuevamente.";
  estado.className = "";
}

// Convierte la respuesta Base64 del servidor en bytes reutilizables.
function decodificarWasm(wasmBase64) {
  const binario = atob(wasmBase64);
  const bytes = new Uint8Array(binario.length);
  for (let indice = 0; indice < binario.length; indice += 1) {
    bytes[indice] = binario.charCodeAt(indice);
  }
  return bytes;
}

// Termina el Worker al recibir un resultado o al superar el límite de ejecución.
function obtenerEntradas() {
  const texto = campoEntradas.value.trim();
  if (!texto) return [];
  return texto.split(/[\s,]+/).map((entrada) => {
    if (!/^[+-]?\d+$/.test(entrada)) {
      throw new Error(`La entrada '${entrada}' no es un entero i32 válido.`);
    }
    const valor = Number(entrada);
    if (!Number.isInteger(valor) || valor < -2147483648 || valor > 2147483647) {
      throw new Error(`La entrada '${entrada}' no es un entero i32 válido.`);
    }
    return valor;
  });
}

function ejecutarEnWorker(wasm, entradas) {
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
      resolver(data);
    };
    worker.onerror = () => {
      finalizar();
      rechazar(new Error("No se pudo ejecutar el módulo WebAssembly."));
    };
    // Se transfiere una copia para conservar los mismos bytes descargables.
    const copiaTransferible = wasm.slice().buffer;
    worker.postMessage({ wasm: copiaTransferible, entradas }, [copiaTransferible]);
  });
}

// Descarga exactamente el binario conservado tras la última compilación válida.
function descargarWasm() {
  if (!wasmCompilado) return;
  const archivoWasm = new Blob([wasmCompilado], { type: "application/wasm" });
  const url = URL.createObjectURL(archivoWasm);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = "programa.wasm";
  enlace.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function analizar() {
  const codigoEnviado = codigo.value;
  const revisionEnviada = revisionCodigo;
  const solicitud = ++ultimaSolicitudAnalisis;
  botonAnalizar.disabled = true;
  estado.textContent = "Analizando…";
  estado.className = "";
  try {
    const respuesta = await fetch("/api/analizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigoEnviado }),
    });
    const resultado = await respuesta.json();
    if (solicitud !== ultimaSolicitudAnalisis
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo analizar el código.");
    mostrarResultado(resultado);
  } catch (error) {
    if (solicitud !== ultimaSolicitudAnalisis
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    estado.textContent = error.message;
    estado.className = "error";
    listaErrores.hidden = true;
  } finally {
    if (solicitud === ultimaSolicitudAnalisis) {
      botonAnalizar.disabled = false;
    }
  }
}

async function compilar() {
  const codigoEnviado = codigo.value;
  const revisionEnviada = revisionCodigo;
  const solicitud = ++ultimaSolicitudCompilacion;
  const accion = ++ultimaAccion;
  botonCompilar.disabled = true;
  invalidarWasm();
  mostrarMensaje("Compilando…");
  try {
    const respuesta = await fetch("/api/compilar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigoEnviado }),
    });
    const resultado = await respuesta.json();
    if (accion !== ultimaAccion
      || solicitud !== ultimaSolicitudCompilacion
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo compilar el programa.");
    if (!resultado.valido) {
      mostrarResultado(resultado);
      return;
    }
    wasmCompilado = decodificarWasm(resultado.wasm_base64);
    botonDescargarWasm.disabled = false;
    mostrarMensaje("La compilación fue correcta.", "correcto");
  } catch (error) {
    if (accion !== ultimaAccion
      || solicitud !== ultimaSolicitudCompilacion
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    mostrarMensaje(error.message, "error");
  } finally {
    if (solicitud === ultimaSolicitudCompilacion) {
      botonCompilar.disabled = false;
    }
  }
}

async function ejecutar() {
  const codigoEnviado = codigo.value;
  const revisionEnviada = revisionCodigo;
  const accion = ++ultimaAccion;
  let entradas;
  try {
    entradas = obtenerEntradas();
  } catch (error) {
    mostrarMensaje(error.message, "error");
    return;
  }
  botonEjecutar.disabled = true;
  invalidarWasm();
  mostrarMensaje("Compilando para ejecutar…");
  try {
    const respuesta = await fetch("/api/compilar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: codigoEnviado }),
    });
    const resultado = await respuesta.json();
    if (accion !== ultimaAccion
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    if (!respuesta.ok) throw new Error(resultado.error || "No se pudo compilar el programa.");
    if (!resultado.valido) {
      mostrarResultado(resultado);
      return;
    }
    const wasm = decodificarWasm(resultado.wasm_base64);
    if (accion !== ultimaAccion
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      mostrarMensaje("El código cambió durante la compilación. Ejecuta nuevamente.", "error");
      return;
    }
    wasmCompilado = wasm;
    botonDescargarWasm.disabled = false;
    // La firma llega del análisis semántico; no se infiere desde el texto fuente.
    if (!resultado.main || resultado.main.parametros.length !== 0) {
      mostrarMensaje("Por ahora solo se puede ejecutar main() sin parámetros.", "error");
      return;
    }
    mostrarMensaje("Ejecutando main()…");
    const ejecucion = await ejecutarEnWorker(wasmCompilado, entradas);
    if (accion !== ultimaAccion) {
      return;
    }
    if (revisionEnviada !== revisionCodigo || codigo.value !== codigoEnviado) {
      invalidarWasm();
      mostrarMensaje("El código cambió durante la ejecución. Ejecuta nuevamente.", "error");
      return;
    }
    const salidas = ejecucion.salidas.map((salida) => `Salida: ${salida}`);
    const resultadoMain = ejecucion.resultado ?? (
      resultado.main.retorno === "unit"
        ? "main() finalizó correctamente."
        : `Resultado de main(): ${ejecucion.valor}`
    );
    mostrarMensaje([...salidas, resultadoMain].join("\n"), "correcto");
  } catch (error) {
    if (accion !== ultimaAccion
      || revisionEnviada !== revisionCodigo
      || codigo.value !== codigoEnviado) {
      return;
    }
    mostrarMensaje(error.message, "error");
  } finally {
    botonEjecutar.disabled = false;
  }
}

codigo.addEventListener("input", () => {
  actualizarLineas();
  invalidarWasm();
  invalidarResultados();
});
codigo.addEventListener("scroll", () => { lineas.scrollTop = codigo.scrollTop; });
botonAnalizar.addEventListener("click", analizar);
botonCompilar.addEventListener("click", compilar);
botonEjecutar.addEventListener("click", ejecutar);
botonDescargarWasm.addEventListener("click", descargarWasm);
archivo.addEventListener("change", () => {
  const seleccionado = archivo.files[0];
  if (!seleccionado) return;
  const lector = new FileReader();
  lector.onload = () => {
    codigo.value = lector.result;
    actualizarLineas();
    invalidarWasm();
    invalidarResultados();
  };
  lector.readAsText(seleccionado);
});
actualizarLineas();
