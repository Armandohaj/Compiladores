"""Compila y ejecuta un archivo RustiQ desde la terminal."""

import argparse
from pathlib import Path

from ejecutar_wasm import ejecutar_main_con_entradas
from generador_wasm import compilar_programa
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


def ejecutar_main_con_limite(wasm, limite_segundos=LIMITE_EJECUCION_SEGUNDOS, entradas=None):
    """Conserva la llamada anterior y delega imports, aislamiento y límite al ejecutor Wasm."""
    valor, _ = ejecutar_main_con_entradas(wasm, entradas, limite_segundos)
    return valor


def ejecutar_archivo(ruta_archivo, limite_segundos=LIMITE_EJECUCION_SEGUNDOS, entradas=None):
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
        valor, salidas = ejecutar_main_con_entradas(
            resultado["wasm"], entradas, limite_segundos
        )
    except (RuntimeError, TimeoutError, ValueError) as error:
        print(f"Error de ejecución: {error}")
        return 1

    print(f"Wasm generado: {ruta_wasm}")
    for salida in salidas:
        print(f"Salida: {salida}")
    print(f"Resultado de main(): {valor}")
    return 0


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Compila y ejecuta un archivo RustiQ.")
    parser.add_argument("archivo", help="Ruta del archivo RustiQ a ejecutar.")
    parser.add_argument(
        "--entrada",
        action="append",
        default=[],
        help="Entero i32 disponible para read(); se puede repetir.",
    )
    opciones = parser.parse_args(argumentos)
    return ejecutar_archivo(opciones.archivo, entradas=opciones.entrada)


if __name__ == "__main__":
    raise SystemExit(main())
