# Ejecutor independiente del compilador. Valida bytes, firma de main e imports, y ejecuta
# con entradas, salidas y límite de tiempo.
"""Ejecuta directamente un módulo WebAssembly descargado de RustiQ."""

import argparse
import multiprocessing
from pathlib import Path

import wasmtime


LIMITE_EJECUCION_SEGUNDOS = 3
MINIMO_I32 = -(2**31)
MAXIMO_I32 = 2**31 - 1


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


def verificar_importaciones(modulo):
    """Acepta solo el contrato de entrada y salida acordado para RustiQ."""
    firmas = {
        ("env", "read_i32"): ([], [wasmtime.ValType.i32()]),
        ("env", "print_i32"): ([wasmtime.ValType.i32()], []),
    }
    for importacion in modulo.imports:
        firma = firmas.get((importacion.module, importacion.name))
        if firma is None or not isinstance(importacion.type, wasmtime.FuncType):
            return False, f"Importación no admitida: {importacion.module}.{importacion.name}."
        parametros, resultados = firma
        if list(importacion.type.params) != parametros or list(importacion.type.results) != resultados:
            return False, (
                f"La firma de {importacion.module}.{importacion.name} no coincide con el contrato RustiQ."
            )
    return True, None


def normalizar_entradas(entradas):
    """Convierte las entradas previas a enteros i32 sin inventar valores faltantes."""
    valores = []
    for entrada in entradas or []:
        if isinstance(entrada, bool) or not isinstance(entrada, (int, str)):
            raise ValueError(f"La entrada '{entrada}' no es un entero i32 válido.")
        try:
            valor = int(entrada)
        except (TypeError, ValueError) as error:
            raise ValueError(f"La entrada '{entrada}' no es un entero i32 válido.") from error
        if not MINIMO_I32 <= valor <= MAXIMO_I32:
            raise ValueError(f"La entrada '{entrada}' está fuera del rango de i32.")
        valores.append(valor)
    return valores


def entradas_desde_texto(texto):
    """Separa números por espacios o comas para las interfaces de usuario."""
    return normalizar_entradas(texto.replace(",", " ").split())


def _ejecutar_main_en_proceso(wasm, entradas, conexion):
    """Ejecuta main en el hijo con imports reales y comunica salidas ordenadas."""
    # El módulo se instancia en un proceso hijo con imports concretos para read/print. El
    # aislamiento permite terminar ejecuciones que excedan el tiempo sin bloquear la
    # interfaz.
    try:
        motor = wasmtime.Engine()
        modulo = cargar_modulo(wasm, motor)
        almacen = wasmtime.Store(motor)
        posicion = 0
        salidas = []

        def read_i32():
            # Entrega el siguiente entero previamente validado; si faltan datos se informa
            # el error en lugar de inventar una entrada para el programa.
            nonlocal posicion
            if posicion >= len(entradas):
                raise RuntimeError("El programa solicitó más entradas i32 de las disponibles.")
            valor = entradas[posicion]
            posicion += 1
            return valor

        def print_i32(valor):
            # Conserva el orden de las salidas emitidas por WASM para devolverlas al proceso
            # que presenta el resultado.
            salidas.append(valor)

        enlazador = wasmtime.Linker(motor)
        enlazador.define_func(
            "env",
            "read_i32",
            wasmtime.FuncType([], [wasmtime.ValType.i32()]),
            read_i32,
        )
        enlazador.define_func(
            "env", "print_i32", wasmtime.FuncType([wasmtime.ValType.i32()], []), print_i32
        )
        instancia = enlazador.instantiate(almacen, modulo)
        main = instancia.exports(almacen)["main"]
        conexion.send(("resultado", main(almacen), salidas))
    except Exception as error:
        conexion.send(("error", str(error), []))
    finally:
        conexion.close()


def ejecutar_main_con_entradas(wasm, entradas=None, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Aísla main() y devuelve el resultado junto con las salidas capturadas."""
    entradas = normalizar_entradas(entradas)
    contexto = multiprocessing.get_context("spawn")
    conexion_padre, conexion_hijo = contexto.Pipe(duplex=False)
    proceso = contexto.Process(
        target=_ejecutar_main_en_proceso,
        args=(wasm, entradas, conexion_hijo),
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
        estado, valor, salidas = conexion_padre.recv()
        if estado == "error":
            raise RuntimeError(valor)
        return valor, salidas
    finally:
        conexion_padre.close()


def ejecutar_main_con_limite(wasm, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Conserva la interfaz previa para módulos sin entradas ni salidas."""
    valor, _ = ejecutar_main_con_entradas(wasm, limite_segundos=limite_segundos)
    return valor


def ejecutar_archivo_wasm(ruta_archivo, limite_segundos=LIMITE_EJECUCION_SEGUNDOS, entradas=None):
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

    compatible, mensaje = verificar_importaciones(modulo)
    if not compatible:
        print(mensaje)
        return 1

    try:
        valor, salidas = ejecutar_main_con_entradas(wasm, entradas, limite_segundos)
    except (RuntimeError, TimeoutError, ValueError) as error:
        print(f"Error de ejecución: {error}")
        return 1

    for salida in salidas:
        print(f"Salida: {salida}")
    print(f"Resultado de main(): {valor}")
    return 0


# Prepara argumentos o interfaz y coordina la operación principal; los errores se presentan
# al usuario.
def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Ejecuta un archivo WebAssembly existente.")
    parser.add_argument("archivo", help="Ruta del archivo .wasm a ejecutar.")
    parser.add_argument(
        "--entrada",
        action="append",
        default=[],
        help="Entero i32 disponible para read_i32; se puede repetir.",
    )
    opciones = parser.parse_args(argumentos)
    return ejecutar_archivo_wasm(opciones.archivo, entradas=opciones.entrada)


if __name__ == "__main__":
    raise SystemExit(main())
