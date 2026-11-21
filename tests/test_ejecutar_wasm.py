# Suite de integración: ejecución de binarios existentes y sus errores. Los casos usan
# archivos o instancias de prueba para aislar resultados.
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
import wasmtime

from ejecutar_wasm import (
    ejecutar_archivo_wasm,
    ejecutar_main_con_entradas,
    normalizar_entradas,
    verificar_importaciones,
)
from generador_wasm import compilar_programa


# Prepara un binario de prueba a partir de WAT para aislar la ejecución de la compilación RustiQ.
def crear_wasm(tmp_path, nombre, wat):
    archivo = tmp_path / nombre
    archivo.write_bytes(wasmtime.wat2wasm(wat))
    return archivo


def test_ejecutor_wasm_ejecuta_y_no_modifica_el_archivo(tmp_path, capsys):
    # Objetivo: ejecutor wasm ejecuta y no modifica el archivo. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_wasm(
        tmp_path,
        "treinta.wasm",
        '(module (func (export "main") (result i32) i32.const 30))',
    )
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 0
    assert "Resultado de main(): 30" in capsys.readouterr().out
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


def test_ejecutor_wasm_ejecuta_binario_generado_por_rustiq(tmp_path, capsys):
    # Objetivo: ejecutor wasm ejecuta binario generado por rustiq. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
    resultado = compilar_programa("fn main() -> i32 { return 10 + 20; }")
    archivo = tmp_path / "rustiq.wasm"
    archivo.write_bytes(resultado["wasm"])

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert resultado["valido"] is True
    assert codigo_salida == 0
    assert "Resultado de main(): 30" in capsys.readouterr().out


def test_ejecutor_wasm_entrega_entradas_y_captura_salidas_en_orden(tmp_path):
    # Objetivo: ejecutor wasm entrega entradas y captura salidas en orden. Comprueba
    # resultados o errores de ejecución mediante las funciones o procesos invocados en esta
    # prueba.
    archivo = crear_wasm(
        tmp_path,
        "entrada-salida.wasm",
        """(module
  (import "env" "read_i32" (func $read_i32 (result i32)))
  (import "env" "print_i32" (func $print_i32 (param i32)))
  (func (export "main") (result i32) (local i32)
    call $read_i32
    local.tee 0
    call $print_i32
    call $read_i32
    local.tee 0
    call $print_i32
    local.get 0))""",
    )

    valor, salidas = ejecutar_main_con_entradas(archivo.read_bytes(), [10, 20])

    assert valor == 20
    assert salidas == [10, 20]


def test_ejecutor_wasm_rechaza_entradas_insuficientes_y_fuera_de_rango(tmp_path):
    # Objetivo: ejecutor wasm rechaza entradas insuficientes y fuera de rango. Comprueba
    # resultados o errores de ejecución mediante las funciones o procesos invocados en esta
    # prueba.
    archivo = crear_wasm(
        tmp_path,
        "dos-lecturas.wasm",
        """(module
  (import "env" "read_i32" (func $read_i32 (result i32)))
  (func (export "main") (result i32) call $read_i32 call $read_i32 i32.add))""",
    )

    with pytest.raises(RuntimeError, match="más entradas"):
        ejecutar_main_con_entradas(archivo.read_bytes(), [1])
    with pytest.raises(ValueError, match="fuera del rango"):
        normalizar_entradas([2**31])
    with pytest.raises(ValueError, match="no es un entero"):
        normalizar_entradas([1.5])


@pytest.mark.parametrize(
    "wat",
    [
        '(module (import "env" "read_i32" (func (param i32) (result i32))) (func (export "main") (result i32) i32.const 0))',
        '(module (import "otro" "read_i32" (func (result i32))) (func (export "main") (result i32) i32.const 0))',
    ],
)
def test_ejecutor_wasm_rechaza_importaciones_incompatibles(tmp_path, wat, capsys):
    # Objetivo: ejecutor wasm rechaza importaciones incompatibles. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_wasm(tmp_path, "importacion.wasm", wat)
    modulo = wasmtime.Module(wasmtime.Engine(), archivo.read_bytes())

    compatible, _ = verificar_importaciones(modulo)
    codigo_salida = ejecutar_archivo_wasm(archivo)
    salida = capsys.readouterr().out

    assert not compatible
    assert codigo_salida == 1
    assert "RustiQ" in salida or "Importación" in salida


def test_ejecutor_wasm_rechaza_archivo_inexistente(tmp_path, capsys):
    # Objetivo: ejecutor wasm rechaza archivo inexistente. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    codigo_salida = ejecutar_archivo_wasm(tmp_path / "ausente.wasm")

    assert codigo_salida == 2
    assert "No se pudo leer" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_archivo_corrupto(tmp_path, capsys):
    # Objetivo: ejecutor wasm rechaza archivo corrupto. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = tmp_path / "corrupto.wasm"
    archivo.write_bytes(b"esto no es wasm")

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "no es un módulo WebAssembly válido" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_modulo_sin_main(tmp_path, capsys):
    # Objetivo: ejecutor wasm rechaza modulo sin main. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_wasm(tmp_path, "sin-main.wasm", '(module (func (export "otra")))')

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "no exporta una función main" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_firma_incompatible(tmp_path, capsys):
    # Objetivo: ejecutor wasm rechaza firma incompatible. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_wasm(
        tmp_path,
        "firma.wasm",
        '(module (func (export "main") (param i32) (result i32) local.get 0))',
    )

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "sin parámetros y retornar i32" in capsys.readouterr().out


def test_ejecutor_wasm_detiene_ciclo_infinito(tmp_path, capsys):
    # Objetivo: ejecutor wasm detiene ciclo infinito. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_wasm(
        tmp_path,
        "infinito.wasm",
        '(module (func (export "main") (result i32) (loop br 0) unreachable))',
    )

    codigo_salida = ejecutar_archivo_wasm(archivo, limite_segundos=1)

    assert codigo_salida == 1
    assert "superó el límite de 1 segundos" in capsys.readouterr().out


def test_ejecutor_wasm_no_importa_el_compilador():
    # Objetivo: ejecutor wasm no importa el compilador. Comprueba resultados o errores de
    # ejecución mediante las funciones o procesos invocados en esta prueba.
    codigo = Path("ejecutar_wasm.py").read_text(encoding="utf-8")

    assert "generador_wasm" not in codigo
    assert "from main import" not in codigo
    assert "antlr" not in codigo.lower()


def test_ejecutor_wasm_funciona_desde_powershell(tmp_path):
    # Objetivo: ejecutor wasm funciona desde powershell. Lanza el comando como proceso
    # externo y comprueba su respuesta; necesita las herramientas de su plataforma.
    archivo = crear_wasm(
        tmp_path,
        "consola.wasm",
        '(module (func (export "main") (result i32) i32.const 30))',
    )
    comando = (
        f'& "{sys.executable}" "ejecutar_wasm.py" "{archivo}"'
    )

    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command", comando],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0
    assert "Resultado de main(): 30" in resultado.stdout
