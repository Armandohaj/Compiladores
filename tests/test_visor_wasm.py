import hashlib
from pathlib import Path

import pytest
import wasmtime

from generador_wasm import compilar_programa
from visor_wasm import cargar_archivo_wasm


def crear_wasm(tmp_path, nombre, wat):
    archivo = tmp_path / nombre
    archivo.write_bytes(wasmtime.wat2wasm(wat))
    return archivo


def test_visor_carga_modulo_valido_sin_modificarlo(tmp_path):
    archivo = crear_wasm(
        tmp_path,
        "treinta.wasm",
        '(module (func (export "main") (result i32) i32.const 30))',
    )
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()

    wasm = cargar_archivo_wasm(archivo)

    assert wasm == archivo.read_bytes()
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


def test_visor_carga_un_binario_generado_por_rustiq(tmp_path):
    resultado = compilar_programa("fn main() -> i32 { return 10 + 20; }")
    archivo = tmp_path / "editor.wasm"
    archivo.write_bytes(resultado["wasm"])

    assert cargar_archivo_wasm(archivo) == resultado["wasm"]


@pytest.mark.parametrize(
    ("nombre", "contenido", "mensaje"),
    [
        ("corrupto.wasm", b"no es wasm", "no es un módulo WebAssembly válido"),
        (
            "sin-main.wasm",
            wasmtime.wat2wasm('(module (func (export "otra")))'),
            "no exporta una función main",
        ),
        (
            "firma.wasm",
            wasmtime.wat2wasm(
                '(module (func (export "main") (param i32) (result i32) local.get 0))'
            ),
            "sin parámetros y retornar i32",
        ),
        (
            "importacion.wasm",
            wasmtime.wat2wasm(
                '(module (import "otro" "read_i32" (func (result i32))) '
                '(func (export "main") (result i32) i32.const 0))'
            ),
            "Importación no admitida",
        ),
    ],
)
def test_visor_rechaza_archivos_no_ejecutables(tmp_path, nombre, contenido, mensaje):
    archivo = tmp_path / nombre
    archivo.write_bytes(contenido)

    with pytest.raises(ValueError, match=mensaje):
        cargar_archivo_wasm(archivo)


def test_visor_no_importa_el_compilador():
    codigo = Path("visor_wasm.py").read_text(encoding="utf-8")

    assert "generador_wasm" not in codigo
    assert "from main import" not in codigo
    assert "antlr" not in codigo.lower()
