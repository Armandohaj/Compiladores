"""Ejecuta directamente un módulo WebAssembly descargado de RustiQ."""

import argparse
import json
import multiprocessing
from pathlib import Path
import struct

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
    if parametros or resultados not in (
        [], [wasmtime.ValType.i32()], [wasmtime.ValType.f64()]
    ):
        return False, "main debe ejecutarse sin parámetros y retornar i32, f64 o no retornar valor."
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


def _leer_entero(memoria, almacen, direccion, firmado=False):
    return int.from_bytes(
        bytes(memoria.read(almacen, direccion, direccion + 4)), "little", signed=firmado
    )


def _leer_f64(memoria, almacen, direccion):
    return struct.unpack("<d", bytes(memoria.read(almacen, direccion, direccion + 8)))[0]


def _es_indirecto(layout):
    return layout["clase"] in {"arreglo", "tupla", "estructura"} or (
        layout["clase"] == "enum" and layout["con_datos"]
    )


def _leer_string(memoria, almacen, descriptor):
    if descriptor < 0 or descriptor + 8 > memoria.data_len(almacen):
        raise ValueError
    puntero = _leer_entero(memoria, almacen, descriptor)
    longitud = _leer_entero(memoria, almacen, descriptor + 4)
    if puntero + longitud > memoria.data_len(almacen):
        raise ValueError
    return bytes(memoria.read(almacen, puntero, puntero + longitud)).decode("utf-8")


def _validar_layout_metadatos(layout):
    if not isinstance(layout, dict):
        raise ValueError
    clase = layout.get("clase")
    if clase in {"i32", "f64", "bool", "char", "String", "unit"}:
        return
    if clase == "arreglo":
        if (
            not isinstance(layout.get("cantidad"), int)
            or isinstance(layout["cantidad"], bool)
            or layout["cantidad"] < 0
            or not isinstance(layout.get("paso"), int)
            or isinstance(layout["paso"], bool)
            or layout["paso"] <= 0
        ):
            raise ValueError
        _validar_layout_metadatos(layout.get("elemento"))
        return
    if clase in {"tupla", "estructura"}:
        campos = layout.get("campos")
        if not isinstance(campos, list):
            raise ValueError
        for campo in campos:
            if (
                not isinstance(campo, dict)
                or not isinstance(campo.get("desplazamiento"), int)
                or isinstance(campo["desplazamiento"], bool)
                or campo["desplazamiento"] < 0
                or (clase == "estructura" and not isinstance(campo.get("nombre"), str))
            ):
                raise ValueError
            _validar_layout_metadatos(campo.get("valor"))
        return
    if clase == "enum":
        if not isinstance(layout.get("nombre"), str) or not isinstance(layout.get("con_datos"), bool):
            raise ValueError
        variantes = layout.get("variantes")
        if not isinstance(variantes, list):
            raise ValueError
        for variante in variantes:
            if (
                not isinstance(variante, dict)
                or not isinstance(variante.get("nombre"), str)
                or not isinstance(variante.get("etiqueta"), int)
                or isinstance(variante["etiqueta"], bool)
                or not isinstance(variante.get("campos"), list)
            ):
                raise ValueError
            for campo in variante["campos"]:
                if (
                    not isinstance(campo, dict)
                    or not isinstance(campo.get("desplazamiento"), int)
                    or isinstance(campo["desplazamiento"], bool)
                    or campo["desplazamiento"] < 0
                ):
                    raise ValueError
                _validar_layout_metadatos(campo.get("valor"))
        return
    raise ValueError


def _formatear_char(valor):
    escapes = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\0": "\\0"}
    texto = escapes.get(valor)
    if texto is None:
        texto = f"\\u{ord(valor):04x}" if ord(valor) < 32 or 0x7F <= ord(valor) <= 0x9F else valor
    return f"'{texto}'"


def _valor_escalar(layout, valor, memoria, almacen):
    clase = layout["clase"]
    if clase == "bool":
        return bool(valor)
    if clase == "char":
        if valor < 0 or valor > 0x10FFFF or 0xD800 <= valor <= 0xDFFF:
            raise RuntimeError("El módulo devolvió un char Unicode inválido.")
        return chr(valor)
    if clase == "String":
        return _leer_string(memoria, almacen, valor)
    return valor


def _valor_desde_direccion(layout, memoria, almacen, direccion):
    clase = layout["clase"]
    if clase == "f64":
        return _leer_f64(memoria, almacen, direccion)
    if clase in {"i32", "bool", "char", "String"}:
        return _valor_escalar(layout, _leer_entero(memoria, almacen, direccion, clase == "i32"), memoria, almacen)
    if _es_indirecto(layout):
        return _valor_desde_resultado(
            layout, _leer_entero(memoria, almacen, direccion), memoria, almacen
        )
    return _valor_desde_resultado(
        layout, _leer_entero(memoria, almacen, direccion, True), memoria, almacen
    )


def _valor_desde_resultado(layout, valor, memoria, almacen):
    clase = layout["clase"]
    if clase in {"i32", "f64", "bool", "char", "String"}:
        return _valor_escalar(layout, valor, memoria, almacen)
    if clase == "arreglo":
        return [
            _valor_desde_direccion(layout["elemento"], memoria, almacen, valor + indice * layout["paso"])
            for indice in range(layout["cantidad"])
        ]
    if clase == "tupla":
        return [
            _valor_desde_direccion(campo["valor"], memoria, almacen, valor + campo["desplazamiento"])
            for campo in layout["campos"]
        ]
    if clase == "estructura":
        return {
            campo["nombre"]: _valor_desde_direccion(
                campo["valor"], memoria, almacen, valor + campo["desplazamiento"]
            )
            for campo in layout["campos"]
        }
    if clase == "enum":
        direccion = valor if layout["con_datos"] else None
        etiqueta = _leer_entero(memoria, almacen, direccion, True) if direccion is not None else valor
        variante = next((item for item in layout["variantes"] if item["etiqueta"] == etiqueta), None)
        if variante is None:
            raise RuntimeError("El módulo devolvió una etiqueta de enum inválida.")
        datos = [] if direccion is None else [
            _valor_desde_direccion(campo["valor"], memoria, almacen, direccion + campo["desplazamiento"])
            for campo in variante["campos"]
        ]
        return {"enum": layout["nombre"], "variante": variante["nombre"], "datos": datos}
    raise RuntimeError("Los metadatos de retorno del módulo no son compatibles.")


def _metadatos_main(instancia, almacen):
    exportaciones = instancia.exports(almacen)
    try:
        exportacion = exportaciones["__rustiq-main-metadata"]
    except KeyError:
        return None, None
    try:
        memoria = exportaciones["memory"]
    except KeyError as error:
        raise RuntimeError("El módulo declara metadatos RustiQ pero no expone la memoria requerida.") from error
    try:
        if not isinstance(exportacion, wasmtime.Global) or not isinstance(memoria, wasmtime.Memory):
            raise ValueError
        descriptor = exportacion.value(almacen)
        if not isinstance(descriptor, int) or isinstance(descriptor, bool) or descriptor < 0:
            raise ValueError
        datos = json.loads(_leer_string(memoria, almacen, descriptor))
        if datos.get("version") != 1:
            raise ValueError
        _validar_layout_metadatos(datos.get("retorno"))
    except (AttributeError, IndexError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("Los metadatos de retorno del módulo no son compatibles.")
    return datos["retorno"], memoria


def _resultado_mostrable(instancia, almacen, valor):
    layout, memoria = _metadatos_main(instancia, almacen)
    if layout is None:
        return "main() finalizó correctamente." if valor is None else f"Resultado de main(): {valor}"
    if layout["clase"] == "unit":
        return "main() finalizó correctamente."
    resultado = _valor_desde_resultado(layout, valor, memoria, almacen)
    if layout["clase"] == "bool":
        texto = "true" if resultado else "false"
    elif layout["clase"] == "char":
        texto = _formatear_char(resultado)
    elif layout["clase"] == "String":
        texto = json.dumps(resultado, ensure_ascii=False)
    elif isinstance(resultado, (list, dict)):
        texto = json.dumps(resultado, ensure_ascii=False)
    else:
        texto = str(resultado)
    return f"Resultado de main(): {texto}"


def _ejecutar_main_en_proceso(wasm, entradas, conexion):
    """Ejecuta main en el hijo con imports reales y comunica salidas ordenadas."""
    try:
        motor = wasmtime.Engine()
        modulo = cargar_modulo(wasm, motor)
        almacen = wasmtime.Store(motor)
        posicion = 0
        salidas = []

        def read_i32():
            nonlocal posicion
            if posicion >= len(entradas):
                raise RuntimeError("El programa solicitó más entradas i32 de las disponibles.")
            valor = entradas[posicion]
            posicion += 1
            return valor

        def print_i32(valor):
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
        valor = main(almacen)
        conexion.send(("resultado", valor, salidas, _resultado_mostrable(instancia, almacen, valor)))
    except Exception as error:
        conexion.send(("error", str(error), [], None))
    finally:
        conexion.close()


def ejecutar_main_con_entradas(wasm, entradas=None, limite_segundos=LIMITE_EJECUCION_SEGUNDOS, detalles=False):
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
        estado, valor, salidas, resultado = conexion_padre.recv()
        if estado == "error":
            raise RuntimeError(valor)
        return (valor, salidas, resultado) if detalles else (valor, salidas)
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
        valor, salidas, resultado = ejecutar_main_con_entradas(
            wasm, entradas, limite_segundos, detalles=True
        )
    except (RuntimeError, TimeoutError, ValueError) as error:
        print(f"Error de ejecución: {error}")
        return 1

    for salida in salidas:
        print(f"Salida: {salida}")
    print(resultado)
    return 0


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
