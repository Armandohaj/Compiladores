from ejecutar_escritorio import ejecutar_archivo


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


def test_ejecutor_escritorio_rechaza_firma_main_incompatible(tmp_path, capsys):
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
    archivo = crear_programa(
        tmp_path,
        "infinito.rustiq",
        "fn main() -> i32 { loop {} return 0; }",
    )

    codigo_salida = ejecutar_archivo(archivo, limite_segundos=1)

    assert codigo_salida == 1
    assert archivo.with_suffix(".wasm").exists()
    assert "superó el límite de 1 segundos" in capsys.readouterr().out
