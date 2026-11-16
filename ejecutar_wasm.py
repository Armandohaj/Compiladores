"""Ejecuta directamente un módulo WebAssembly descargado de RustiQ."""

import argparse
import multiprocessing
from pathlib import Path

import wasmtime


LIMITE_EJECUCION_SEGUNDOS = 3


def cargar_modulo(wasm, motor=None):
    """Valida los bytes Wasm y devuelve el módulo sin usar el compilador RustiQ."""
    return wasmtime.Module(motor or wasmtime.Engine(), wasm)


def verificar_firma_main(modulo):
    """Comprueba en las exportaciones del módulo que main sea ejecutable."""
    exportacion = next((item for item in modulo.exports if item.name == "main"), None)
    if exportacion is None:
        return False, "El módulo no exporta una función main."
    if not isinstance(exportacion.type, wasmtime.FuncType):
        return False, "La exportación main debe ser una función."

    parametros = list(exportacion.type.params)
    resultados = list(exportacion.type.results)
    if parametros or resultados != [wasmtime.ValType.i32()]:
        return False, "main debe ejecutarse sin parámetros y retornar i32."
    return True, None


def _ejecutar_main_en_proceso(wasm, conexion):
    """Ejecuta main en el proceso hijo y comunica solo su resultado o error."""
    try:
        motor = wasmtime.Engine()
        modulo = cargar_modulo(wasm, motor)
        almacen = wasmtime.Store(motor)
        instancia = wasmtime.Instance(almacen, modulo, [])
        main = instancia.exports(almacen)["main"]
        conexion.send(("resultado", main(almacen)))
    except Exception as error:
        conexion.send(("error", str(error)))
    finally:
        conexion.close()


def ejecutar_main_con_limite(wasm, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Aísla el módulo para detener con seguridad una ejecución que no termina."""
    contexto = multiprocessing.get_context("spawn")
    conexion_padre, conexion_hijo = contexto.Pipe(duplex=False)
    proceso = contexto.Process(
        target=_ejecutar_main_en_proceso,
        args=(wasm, conexion_hijo),
    )
    proceso.start()
    conexion_hijo.close()
    proceso.join(limite_segundos)

    try:
        if proceso.is_alive():
            proceso.terminate()
            proceso.join()
            raise TimeoutError(
                f"La ejecución superó el límite de {limite_segundos} segundos."
            )
        if not conexion_padre.poll():
            raise RuntimeError("El proceso de ejecución terminó sin devolver un resultado.")
        estado, valor = conexion_padre.recv()
        if estado == "error":
            raise RuntimeError(valor)
        return valor
    finally:
        conexion_padre.close()


def ejecutar_archivo_wasm(ruta_archivo, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Lee y ejecuta un .wasm existente sin crear ni modificar archivos."""
    ruta = Path(ruta_archivo)
    try:
        wasm = ruta.read_bytes()
    except OSError as error:
        print(f"No se pudo leer '{ruta}': {error}")
        return 2

    try:
        modulo = cargar_modulo(wasm)
    except Exception as error:
        print(f"El archivo no es un módulo WebAssembly válido: {error}")
        return 1

    ejecutable, mensaje = verificar_firma_main(modulo)
    if not ejecutable:
        print(mensaje)
        return 1

    try:
        valor = ejecutar_main_con_limite(wasm, limite_segundos)
    except (RuntimeError, TimeoutError) as error:
        print(f"Error de ejecución: {error}")
        return 1

    print(f"Resultado de main(): {valor}")
    return 0


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Ejecuta un archivo WebAssembly existente.")
    parser.add_argument("archivo", help="Ruta del archivo .wasm a ejecutar.")
    opciones = parser.parse_args(argumentos)
    return ejecutar_archivo_wasm(opciones.archivo)


if __name__ == "__main__":
    raise SystemExit(main())
