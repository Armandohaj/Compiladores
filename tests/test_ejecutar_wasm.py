import hashlib
import subprocess
import sys
from pathlib import Path

import wasmtime

from ejecutar_wasm import ejecutar_archivo_wasm
from generador_wasm import compilar_programa


def crear_wasm(tmp_path, nombre, wat):
    archivo = tmp_path / nombre
    archivo.write_bytes(wasmtime.wat2wasm(wat))
    return archivo


def test_ejecutor_wasm_ejecuta_y_no_modifica_el_archivo(tmp_path, capsys):
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
    resultado = compilar_programa("fn main() -> i32 { return 10 + 20; }")
    archivo = tmp_path / "rustiq.wasm"
    archivo.write_bytes(resultado["wasm"])

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert resultado["valido"] is True
    assert codigo_salida == 0
    assert "Resultado de main(): 30" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_archivo_inexistente(tmp_path, capsys):
    codigo_salida = ejecutar_archivo_wasm(tmp_path / "ausente.wasm")

    assert codigo_salida == 2
    assert "No se pudo leer" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_archivo_corrupto(tmp_path, capsys):
    archivo = tmp_path / "corrupto.wasm"
    archivo.write_bytes(b"esto no es wasm")

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "no es un módulo WebAssembly válido" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_modulo_sin_main(tmp_path, capsys):
    archivo = crear_wasm(tmp_path, "sin-main.wasm", '(module (func (export "otra")))')

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "no exporta una función main" in capsys.readouterr().out


def test_ejecutor_wasm_rechaza_firma_incompatible(tmp_path, capsys):
    archivo = crear_wasm(
        tmp_path,
        "firma.wasm",
        '(module (func (export "main") (param i32) (result i32) local.get 0))',
    )

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert "sin parámetros y retornar i32" in capsys.readouterr().out


def test_ejecutor_wasm_detiene_ciclo_infinito(tmp_path, capsys):
    archivo = crear_wasm(
        tmp_path,
        "infinito.wasm",
        '(module (func (export "main") (result i32) (loop br 0) unreachable))',
    )

    codigo_salida = ejecutar_archivo_wasm(archivo, limite_segundos=1)

    assert codigo_salida == 1
    assert "superó el límite de 1 segundos" in capsys.readouterr().out


def test_ejecutor_wasm_no_importa_el_compilador():
    codigo = Path("ejecutar_wasm.py").read_text(encoding="utf-8")

    assert "generador_wasm" not in codigo
    assert "from main import" not in codigo
    assert "antlr" not in codigo.lower()


def test_ejecutor_wasm_funciona_desde_powershell(tmp_path):
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
