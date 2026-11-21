# Suite de integración: compilación y ejecución desde procesos de terminal. Los casos usan
# archivos o instancias de prueba para aislar resultados.
from ejecutar_escritorio import ejecutar_archivo, main


# Escribe un fuente temporal de prueba sin modificar los ejemplos del repositorio.
def crear_programa(tmp_path, nombre, codigo):
    archivo = tmp_path / nombre
    archivo.write_text(codigo, encoding="utf-8")
    return archivo


def test_ejecutor_escritorio_compila_guarda_y_ejecuta(tmp_path, capsys):
    # Objetivo: ejecutor escritorio compila guarda y ejecuta. Comprueba resultados o errores
    # de ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_programa(
        tmp_path,
        "valido.rustiq",
        "fn main() -> i32 { return 10 + 20; }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 0
    assert archivo.with_suffix(".wasm").read_bytes().startswith(b"\x00asm")
    assert "Resultado de main(): 30" in capsys.readouterr().out


def test_ejecutor_escritorio_muestra_errores_de_compilacion(tmp_path, capsys):
    # Objetivo: ejecutor escritorio muestra errores de compilacion. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_programa(
        tmp_path,
        "invalido.rustiq",
        "fn main() -> i32 { return @; }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 1
    assert not archivo.with_suffix(".wasm").exists()
    assert "lexico: línea 1" in capsys.readouterr().out


def test_ejecutor_escritorio_rechaza_firma_main_incompatible(tmp_path, capsys):
    # Objetivo: ejecutor escritorio rechaza firma main incompatible. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
    archivo = crear_programa(
        tmp_path,
        "bool.rustiq",
        "fn main() -> bool { return true; }",
    )

    codigo_salida = ejecutar_archivo(archivo)

    assert codigo_salida == 1
    assert not archivo.with_suffix(".wasm").exists()
    assert "main() sin parámetros que retorne i32" in capsys.readouterr().out


def test_ejecutor_escritorio_termina_ciclo_infinito(tmp_path, capsys):
    # Objetivo: ejecutor escritorio termina ciclo infinito. Comprueba resultados o errores
    # de ejecución mediante las funciones o procesos invocados en esta prueba.
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
    # Objetivo: ejecutor escritorio entrega entradas y muestra salidas. Las aserciones fijan
    # el comportamiento esperado; un rechazo previsto también es un resultado correcto.
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
    # Objetivo: ejecutor escritorio informa entradas insuficientes. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
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
