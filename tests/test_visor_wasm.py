import hashlib
from pathlib import Path

import pytest
import wasmtime

from ejecutar_wasm import ejecutar_main_con_entradas
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


def test_visor_carga_y_ejecuta_binario_con_read_y_print(tmp_path):
    resultado = compilar_programa(
        "fn main() -> i32 { let valor = read(); print(valor); return valor; }"
    )
    archivo = tmp_path / "entrada-salida.wasm"
    archivo.write_bytes(resultado["wasm"])

    wasm = cargar_archivo_wasm(archivo)

    assert resultado["valido"]
    assert ejecutar_main_con_entradas(wasm, [37]) == (37, [37])


def test_visor_carga_y_ejecuta_main_unit_con_read_y_print(tmp_path):
    resultado = compilar_programa(
        "fn main() { let valor = read(); print(valor); }"
    )
    archivo = tmp_path / "unit.wasm"
    archivo.write_bytes(resultado["wasm"])

    wasm = cargar_archivo_wasm(archivo)

    assert resultado["valido"]
    assert ejecutar_main_con_entradas(wasm, [37]) == (None, [37])


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("fn main() -> i32 { 7 }", "Resultado de main(): 7"),
        ("fn main() -> f64 { 1.5 }", "Resultado de main(): 1.5"),
        ("fn main() -> bool { true }", "Resultado de main(): true"),
        ("fn main() -> char { 'ñ' }", "Resultado de main(): 'ñ'"),
        (r"fn main() -> char { '\n' }", r"Resultado de main(): '\n'"),
        ('fn main() -> String { "hola" }', 'Resultado de main(): "hola"'),
        ("fn main() -> (i32, bool) { (7, true) }", "Resultado de main(): [7, true]"),
        (
            "struct Punto { x: i32 } fn main() -> Punto { Punto { x: 7 } }",
            'Resultado de main(): {"x": 7}',
        ),
        (
            "enum Estado { Valor(i32), Vacio } fn main() -> Estado { Estado::Valor(7) }",
            'Resultado de main(): {"enum": "Estado", "variante": "Valor", "datos": [7]}',
        ),
        (
            "fn main() -> [[i32; 2]; 2] { [[1, 2], [3, 4]] }",
            "Resultado de main(): [[1, 2], [3, 4]]",
        ),
    ],
)
def test_visor_acepta_y_decodifica_retornos_rustiq(tmp_path, codigo, esperado):
    resultado = compilar_programa(codigo)
    archivo = tmp_path / "retorno.wasm"
    archivo.write_bytes(resultado["wasm"])

    wasm = cargar_archivo_wasm(archivo)
    _, _, mostrado = ejecutar_main_con_entradas(wasm, detalles=True)

    assert resultado["valido"]
    assert mostrado == esperado


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
            "sin parámetros y retornar i32, f64 o no retornar valor",
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
