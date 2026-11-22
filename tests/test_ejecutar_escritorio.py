import pytest

from ejecutar_escritorio import ejecutar_archivo, main


def crear_programa(tmp_path, nombre, codigo):
    archivo = tmp_path / nombre
    archivo.write_text(codigo, encoding="utf-8")
    return archivo


def test_ejecutor_escritorio_compila_guarda_y_ejecuta(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "valido.rustiq",
        "fn main() -> i32 { return 10 + 20; }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 0
    assert archivo.with_suffix(".wasm").read_bytes().startswith(b"\x00asm")
    assert "Resultado de main(): 30" in capsys.readouterr().out


def test_ejecutor_escritorio_ejecuta_main_unit_con_read_y_print(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "unit.rustiq",
        """fn main() {
    let valor = read();
    print(valor);
}""",
    )

    codigo_salida = ejecutar_archivo(archivo, entradas=[15])
    salida = capsys.readouterr().out

    assert codigo_salida == 0
    assert archivo.with_suffix(".wasm").read_bytes().startswith(b"\x00asm")
    assert "Salida: 15" in salida
    assert "main() finalizó correctamente." in salida
    assert "Resultado de main()" not in salida


def test_ejecutor_escritorio_muestra_errores_de_compilacion(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "invalido.rustiq",
        "fn main() -> i32 { return @; }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 1
    assert not archivo.with_suffix(".wasm").exists()
    assert "lexico: línea 1" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("fn main() -> f64 { 1.5 }", "Resultado de main(): 1.5"),
        ("fn main() -> bool { true }", "Resultado de main(): true"),
        ("fn main() -> char { 'ñ' }", "Resultado de main(): 'ñ'"),
        (r"fn main() -> char { '\n' }", r"Resultado de main(): '\n'"),
        ('fn main() -> String { "hola" }', 'Resultado de main(): "hola"'),
        ("fn main() -> [i32; 2] { [7, 8] }", "Resultado de main(): [7, 8]"),
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
def test_ejecutor_escritorio_muestra_retornos_admitidos(tmp_path, capsys, codigo, esperado):
    archivo = crear_programa(
        tmp_path,
        "retorno.rustiq",
        codigo,
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 0
    assert esperado in capsys.readouterr().out


def test_ejecutor_escritorio_rechaza_main_con_parametros(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "parametro.rustiq",
        "fn main(valor: i32) -> i32 { valor }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 1
    assert not archivo.with_suffix(".wasm").exists()
    assert "main() sin parámetros" in capsys.readouterr().out


def test_ejecutor_escritorio_termina_ciclo_infinito(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "infinito.rustiq",
        "fn main() -> i32 { loop {} return 0; }",
    )

    codigo_salida = ejecutar_archivo(archivo, limite_segundos=1)

    assert codigo_salida == 1
    assert archivo.with_suffix(".wasm").exists()
    assert "superó el límite de 1 segundos" in capsys.readouterr().out


def test_ejecutor_escritorio_entrega_entradas_y_muestra_salidas(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "entrada_salida.rustiq",
        """fn main() -> i32 {
    let primero = read();
    let segundo = read();
    print(primero);
    print(segundo);
    return primero + segundo;
}""",
    )

    codigo_salida = main([
        str(archivo), "--entrada", "15", "--entrada", "22",
    ])

    salida = capsys.readouterr().out
    assert codigo_salida == 0
    assert archivo.with_suffix(".wasm").read_bytes().startswith(b"\x00asm")
    assert "Salida: 15" in salida
    assert "Salida: 22" in salida
    assert "Resultado de main(): 37" in salida


def test_ejecutor_escritorio_informa_entradas_insuficientes(tmp_path, capsys):
    archivo = crear_programa(
        tmp_path,
        "faltan_entradas.rustiq",
        """fn main() -> i32 {
    let primero = read();
    let segundo = read();
    return primero + segundo;
}""",
    )

    codigo_salida = ejecutar_archivo(archivo, entradas=[10])

    assert codigo_salida == 1
    assert "solicitó más entradas i32" in capsys.readouterr().out
