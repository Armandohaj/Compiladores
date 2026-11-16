// Este Worker aísla la ejecución para que un ciclo infinito no bloquee el editor.
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
    self.postMessage({ valor: main(), salidas });
  } catch (error) {
    self.postMessage({ error: error.message || "Error al ejecutar WebAssembly." });
  }
};
