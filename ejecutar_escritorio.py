"""Compila y ejecuta un archivo RustiQ desde la terminal."""

import argparse
import multiprocessing
from pathlib import Path

from generador_wasm import compilar_programa, ejecutar_modulo_wasm
from main import analizar_programa


LIMITE_EJECUCION_SEGUNDOS = 3


def mostrar_errores(errores):
    """Presenta los errores del análisis o la generación con su ubicación."""
    for error in errores:
        print(
            f"{error['fase']}: línea {error['linea']}, "
            f"columna {error['columna']}: {error['mensaje']}"
        )


def firma_main_ejecutable(codigo):
    """Obtiene la firma semántica de main sin inferir tipos desde el texto."""
    analisis = analizar_programa(codigo)
    firma = analisis["funciones"].get("main")
    if firma is None:
        return False, "El programa debe declarar una función main()."
    if firma["parametros"] or firma["retorno"] != "i32":
        return False, "Por ahora solo se puede ejecutar main() sin parámetros que retorne i32."
    return True, None


def _ejecutar_modulo_en_proceso(wasm, conexion):
    """Ejecuta Wasm en el hijo y comunica el resultado al proceso principal."""
    try:
        conexion.send(("resultado", ejecutar_modulo_wasm(wasm)))
    except Exception as error:
        conexion.send(("error", str(error)))
    finally:
        conexion.close()


def ejecutar_main_con_limite(wasm, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Aísla main() para que el padre pueda detener ciclos que no terminan."""
    contexto = multiprocessing.get_context("spawn")
    conexion_padre, conexion_hijo = contexto.Pipe(duplex=False)
    proceso = contexto.Process(
        target=_ejecutar_modulo_en_proceso,
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


def ejecutar_archivo(ruta_archivo, limite_segundos=LIMITE_EJECUCION_SEGUNDOS):
    """Compila un archivo, guarda su Wasm y ejecuta la función main compatible."""
    ruta = Path(ruta_archivo)
    try:
        codigo = ruta.read_text(encoding="utf-8")
    except OSError as error:
        print(f"No se pudo leer '{ruta}': {error}")
        return 2

    resultado = compilar_programa(codigo)
    if not resultado["valido"]:
        mostrar_errores(resultado["errores"])
        return 1

    ejecutable, mensaje = firma_main_ejecutable(codigo)
    if not ejecutable:
        print(mensaje)
        return 1

    ruta_wasm = ruta.with_suffix(".wasm")
    try:
        ruta_wasm.write_bytes(resultado["wasm"])
    except OSError as error:
        print(f"No se pudo guardar '{ruta_wasm}': {error}")
        return 2

    try:
        valor = ejecutar_main_con_limite(resultado["wasm"], limite_segundos)
    except (RuntimeError, TimeoutError) as error:
        print(f"Error de ejecución: {error}")
        return 1

    print(f"Wasm generado: {ruta_wasm}")
    print(f"Resultado de main(): {valor}")
    return 0


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Compila y ejecuta un archivo RustiQ.")
    parser.add_argument("archivo", help="Ruta del archivo RustiQ a ejecutar.")
    opciones = parser.parse_args(argumentos)
    return ejecutar_archivo(opciones.archivo)


if __name__ == "__main__":
    raise SystemExit(main())
