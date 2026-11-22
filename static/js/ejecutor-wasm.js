function esIndirecto(layout) {
  return ["arreglo", "tupla", "estructura"].includes(layout.clase)
    || (layout.clase === "enum" && layout.con_datos);
}

function entero(vista, direccion, firmado = false) {
  return firmado ? vista.getInt32(direccion, true) : vista.getUint32(direccion, true);
}

function texto(vista, memoria, descriptor) {
  const inicio = entero(vista, descriptor);
  const longitud = entero(vista, descriptor + 4);
  return new TextDecoder().decode(new Uint8Array(memoria.buffer, inicio, longitud));
}

function validarLayout(layout) {
  if (!layout || typeof layout !== "object" || Array.isArray(layout)) throw new Error();
  if (["i32", "f64", "bool", "char", "String", "unit"].includes(layout.clase)) return;
  if (layout.clase === "arreglo") {
    if (!Number.isInteger(layout.cantidad) || layout.cantidad < 0
      || !Number.isInteger(layout.paso) || layout.paso <= 0) throw new Error();
    validarLayout(layout.elemento);
    return;
  }
  if (["tupla", "estructura"].includes(layout.clase)) {
    if (!Array.isArray(layout.campos)) throw new Error();
    layout.campos.forEach((campo) => {
      if (!campo || !Number.isInteger(campo.desplazamiento) || campo.desplazamiento < 0
        || (layout.clase === "estructura" && typeof campo.nombre !== "string")) throw new Error();
      validarLayout(campo.valor);
    });
    return;
  }
  if (layout.clase === "enum") {
    if (typeof layout.nombre !== "string" || typeof layout.con_datos !== "boolean"
      || !Array.isArray(layout.variantes)) throw new Error();
    layout.variantes.forEach((variante) => {
      if (!variante || typeof variante.nombre !== "string" || !Number.isInteger(variante.etiqueta)
        || !Array.isArray(variante.campos)) throw new Error();
      variante.campos.forEach((campo) => {
        if (!campo || !Number.isInteger(campo.desplazamiento) || campo.desplazamiento < 0) throw new Error();
        validarLayout(campo.valor);
      });
    });
    return;
  }
  throw new Error();
}

function charMostrable(valor) {
  const escapes = { "\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\0": "\\0" };
  const codigo = valor.codePointAt(0);
  const texto = Object.prototype.hasOwnProperty.call(escapes, valor)
    ? escapes[valor]
    : (codigo < 32 || (codigo >= 0x7f && codigo <= 0x9f) ? `\\u${codigo.toString(16).padStart(4, "0")}` : valor);
  return `'${texto}'`;
}

function escalar(layout, valor, vista, memoria) {
  if (layout.clase === "bool") return Boolean(valor);
  if (layout.clase === "char") {
    if (valor < 0 || valor > 0x10ffff || (valor >= 0xd800 && valor <= 0xdfff)) {
      throw new Error("El módulo devolvió un char Unicode inválido.");
    }
    return String.fromCodePoint(valor);
  }
  if (layout.clase === "String") return texto(vista, memoria, valor);
  return valor;
}

function desdeDireccion(layout, vista, memoria, direccion) {
  if (layout.clase === "f64") return vista.getFloat64(direccion, true);
  if (["i32", "bool", "char", "String"].includes(layout.clase)) {
    return escalar(layout, entero(vista, direccion, layout.clase === "i32"), vista, memoria);
  }
  return desdeResultado(
    layout,
    entero(vista, direccion, !esIndirecto(layout)),
    vista,
    memoria,
  );
}

function desdeResultado(layout, valor, vista, memoria) {
  if (["i32", "f64", "bool", "char", "String"].includes(layout.clase)) {
    return escalar(layout, valor, vista, memoria);
  }
  if (layout.clase === "arreglo") {
    return Array.from(
      { length: layout.cantidad },
      (_, indice) => desdeDireccion(layout.elemento, vista, memoria, valor + indice * layout.paso),
    );
  }
  if (layout.clase === "tupla") {
    return layout.campos.map((campo) => desdeDireccion(
      campo.valor, vista, memoria, valor + campo.desplazamiento,
    ));
  }
  if (layout.clase === "estructura") {
    return Object.fromEntries(layout.campos.map((campo) => [campo.nombre, desdeDireccion(
      campo.valor, vista, memoria, valor + campo.desplazamiento,
    )]));
  }
  if (layout.clase === "enum") {
    const direccion = layout.con_datos ? valor : null;
    const etiqueta = direccion === null ? valor : entero(vista, direccion, true);
    const variante = layout.variantes.find((item) => item.etiqueta === etiqueta);
    if (!variante) throw new Error("El módulo devolvió una etiqueta de enum inválida.");
    return {
      enum: layout.nombre,
      variante: variante.nombre,
      datos: direccion === null ? [] : variante.campos.map((campo) => desdeDireccion(
        campo.valor, vista, memoria, direccion + campo.desplazamiento,
      )),
    };
  }
  throw new Error("Los metadatos de retorno del módulo no son compatibles.");
}

function resultadoMostrable(instancia, valor) {
  const descriptor = instancia.exports["__rustiq-main-metadata"];
  if (!descriptor) {
    return valor === undefined ? "main() finalizó correctamente." : `Resultado de main(): ${valor}`;
  }
  const memoria = instancia.exports.memory;
  if (!memoria) throw new Error("El módulo declara metadatos RustiQ pero no expone la memoria requerida.");
  let layout;
  let vista;
  try {
    if (!(descriptor instanceof WebAssembly.Global) || !(memoria instanceof WebAssembly.Memory)
      || !Number.isInteger(descriptor.value) || descriptor.value < 0) throw new Error();
    vista = new DataView(memoria.buffer);
    const metadatos = JSON.parse(texto(vista, memoria, descriptor.value));
    if (metadatos.version !== 1) throw new Error();
    layout = metadatos.retorno;
    validarLayout(layout);
  } catch (error) {
    throw new Error("Los metadatos de retorno del módulo no son compatibles.");
  }
  if (layout.clase === "unit") return "main() finalizó correctamente.";
  const resultado = desdeResultado(layout, valor, vista, memoria);
  let mostrado;
  if (layout.clase === "bool") mostrado = resultado ? "true" : "false";
  else if (layout.clase === "char") mostrado = charMostrable(resultado);
  else if (layout.clase === "String" || Array.isArray(resultado) || typeof resultado === "object") {
    mostrado = JSON.stringify(resultado);
  } else mostrado = String(resultado);
  return `Resultado de main(): ${mostrado}`;
}

self.onmessage = async ({ data }) => {
  try {
    const entradas = Array.isArray(data.entradas) ? data.entradas : [];
    if (entradas.some((valor) => !Number.isInteger(valor) || valor < -2147483648 || valor > 2147483647)) {
      throw new Error("Las entradas deben ser enteros dentro del rango de i32.");
    }
    let siguienteEntrada = 0;
    const salidas = [];
    // Las importaciones siguen el contrato env.read_i32 y env.print_i32 de RustiQ.
    const imports = {
      env: {
        read_i32() {
          if (siguienteEntrada >= entradas.length) {
            throw new Error("El programa solicitó más entradas i32 de las disponibles.");
          }
          const valor = entradas[siguienteEntrada];
          siguienteEntrada += 1;
          return valor;
        },
        print_i32(valor) {
          salidas.push(valor);
        },
      },
    };
    const modulo = await WebAssembly.instantiate(data.wasm, imports);
    const main = modulo.instance.exports.main;
    if (typeof main !== "function") {
      throw new Error("El módulo no exporta una función main ejecutable.");
    }
    const valor = main();
    self.postMessage({ valor, resultado: resultadoMostrable(modulo.instance, valor), salidas });
  } catch (error) {
    self.postMessage({ error: error.message || "Error al ejecutar WebAssembly." });
  }
};
