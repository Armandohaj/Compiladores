// Este Worker aísla la ejecución para que un ciclo infinito no bloquee el editor.
self.onmessage = async ({ data }) => {
  try {
    const modulo = await WebAssembly.instantiate(data.wasm);
    const main = modulo.instance.exports.main;
    if (typeof main !== "function") {
      throw new Error("El módulo no exporta una función main ejecutable.");
    }
    self.postMessage({ valor: main() });
  } catch (error) {
    self.postMessage({ error: error.message || "Error al ejecutar WebAssembly." });
  }
};
