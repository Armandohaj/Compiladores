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


def test_ejecutor_wasm_ejecuta_main_unit_con_entradas_y_salidas(tmp_path, capsys):
    resultado = compilar_programa("""fn main() {
    let valor = read();
    print(valor);
}""")
    archivo = tmp_path / "unit.wasm"
    archivo.write_bytes(resultado["wasm"])

    codigo_salida = ejecutar_archivo_wasm(archivo, entradas=[37])
    salida = capsys.readouterr().out

    assert resultado["valido"]
    assert codigo_salida == 0
    assert "Salida: 37" in salida
    assert "main() finalizó correctamente." in salida
    assert "Resultado de main()" not in salida


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("fn main() -> i32 { 30 }", "Resultado de main(): 30"),
        ("fn main() -> f64 { 1.5 }", "Resultado de main(): 1.5"),
        ("fn main() -> bool { true }", "Resultado de main(): true"),
        ("fn main() -> char { 'ñ' }", "Resultado de main(): 'ñ'"),
        (r"fn main() -> char { '\n' }", r"Resultado de main(): '\n'"),
        (r"fn main() -> char { '\t' }", r"Resultado de main(): '\t'"),
        (r"fn main() -> char { '\r' }", r"Resultado de main(): '\r'"),
        (r'''fn main() -> char { '\'' }''', r"Resultado de main(): '\''"),
        (r"fn main() -> char { '\\' }", r"Resultado de main(): '\\'"),
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
            "enum Estado { Pendiente, Listo } fn main() -> Estado { Estado::Listo }",
            'Resultado de main(): {"enum": "Estado", "variante": "Listo", "datos": []}',
        ),
        ("fn main() -> [i32; 2] { [7, 8] }", "Resultado de main(): [7, 8]"),
        (
            "fn main() -> [[i32; 2]; 2] { [[1, 2], [3, 4]] }",
            "Resultado de main(): [[1, 2], [3, 4]]",
        ),
    ],
)
def test_ejecutor_wasm_muestra_todos_los_retornos_rustiq(tmp_path, capsys, codigo, esperado):
    resultado = compilar_programa(codigo)
    archivo = tmp_path / "retorno.wasm"
    archivo.write_bytes(resultado["wasm"])

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert resultado["valido"]
    assert codigo_salida == 0
    assert esperado in capsys.readouterr().out


def test_ejecutor_wasm_entrega_entradas_y_captura_salidas_en_orden(tmp_path):
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
    archivo = crear_wasm(tmp_path, "importacion.wasm", wat)
    modulo = wasmtime.Module(wasmtime.Engine(), archivo.read_bytes())

    compatible, _ = verificar_importaciones(modulo)
    codigo_salida = ejecutar_archivo_wasm(archivo)
    salida = capsys.readouterr().out

    assert not compatible
    assert codigo_salida == 1
    assert "RustiQ" in salida or "Importación" in salida


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


@pytest.mark.parametrize(
    ("wat", "mensaje"),
    [
        (
            '(module (global (export "__rustiq-main-metadata") i32 (i32.const 0)) '
            '(func (export "main") (result i32) i32.const 1))',
            "declara metadatos RustiQ pero no expone la memoria requerida",
        ),
        (
            '(module (memory (export "memory") 1) '
            '(global (export "__rustiq-main-metadata") i32 (i32.const 0)) '
            '(data (i32.const 0) "\\08\\00\\00\\00\\01\\00\\00\\00x") '
            '(func (export "main") (result i32) i32.const 1))',
            "metadatos de retorno del módulo no son compatibles",
        ),
    ],
)
def test_ejecutor_wasm_rechaza_metadatos_declarados_invalidos(tmp_path, capsys, wat, mensaje):
    archivo = crear_wasm(tmp_path, "metadatos-invalidos.wasm", wat)

    codigo_salida = ejecutar_archivo_wasm(archivo)

    assert codigo_salida == 1
    assert mensaje in capsys.readouterr().out


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
    assert "sin parámetros y retornar i32, f64 o no retornar valor" in capsys.readouterr().out


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
