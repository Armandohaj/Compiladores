import pytest
import wasmtime

from generador_wasm import ErrorGeneracion, compilar_programa, ejecutar_modulo_wasm
from main import analizar_programa


def test_compila_y_ejecuta_la_prueba_obligatoria(tmp_path):
    resultado = compilar_programa("""fn main() -> i32 {
    return 10 + 20;
}""")

    assert resultado["valido"]
    assert resultado["errores"] == []
    assert resultado["wasm"].startswith(b"\x00asm")
    archivo = tmp_path / "main.wasm"
    archivo.write_bytes(resultado["wasm"])
    wasmtime.Module(wasmtime.Engine(), archivo.read_bytes())
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 30


def test_respeta_parentesis_y_precedencia():
    resultado = compilar_programa("""fn main() -> i32 {
    return (2 + 3) * 4 - 6;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 14


def test_puede_generar_varias_funciones_sin_parametros():
    resultado = compilar_programa("""fn main() -> i32 {
    return 1 + 2;
}

fn producto() -> i32 {
    return 6 * 7;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "main") == 3
    assert ejecutar_modulo_wasm(resultado["wasm"], "producto") == 42


def test_programa_invalido_no_genera_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    return @;
}""")

    assert not resultado["valido"]
    assert any(error["fase"] == "lexico" for error in resultado["errores"])
    assert resultado["wat"] is None
    assert resultado["wasm"] is None


def test_control_de_flujo_no_soportado_no_genera_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    if true {
        return 10;
    } else {
        return 20;
    }
}""")

    assert not resultado["valido"]
    assert resultado["errores"][0]["fase"] == "generacion"
    assert resultado["wat"] is None
    assert resultado["wasm"] is None


@pytest.mark.parametrize(
    ("operador", "esperado"),
    [("/", 3), ("%", 1)],
)
def test_division_y_residuo_generan_y_ejecutan_wasm(operador, esperado):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    return 10 {operador} 3;
}}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_operaciones_con_signo_y_negacion_unaria():
    resultado = compilar_programa("""fn main() -> i32 {
    return -(2 + 3) * 4 + (-7 / 2) + (-7 % 2);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == -24


def test_el_minimo_i32_es_un_literal_negativo_valido():
    resultado = compilar_programa("""fn main() -> i32 {
    return -2147483648;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == -2147483648


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> i32 {
    return 1 / 0;
}""",
        """fn main() -> i32 {
    return -2147483648 / -1;
}""",
    ],
)
def test_divisiones_que_trapan_en_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


@pytest.mark.parametrize("literal", ["2147483648", "-2147483649"])
def test_literales_fuera_del_rango_i32_no_generan_wasm(literal):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    return {literal};
}}""")

    assert not resultado["valido"]
    assert resultado["errores"][0]["fase"] == "generacion"
    assert resultado["wasm"] is None


def test_error_generacion_acepta_nodo_terminal_antlr():
    analisis = analizar_programa("""fn main() -> i32 {
    return 10 / 2;
}""")
    expresion = analisis["arbol"].functionDecl(0).block().statement(0).returnStmt().expression()
    multiplicativa = expresion.logicalOr().logicalAnd(0).comparison(0).additive(0).multiplicative(0)
    operador = multiplicativa.getChild(1)

    error = ErrorGeneracion("Operador de prueba", operador).como_error()

    assert error == {
        "fase": "generacion",
        "mensaje": "Operador de prueba",
        "linea": 2,
        "columna": 15,
    }


def test_declaracion_y_asignacion_obligatoria_generan_locales_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut numero: i32 = 10;
    numero = numero + 5;
    return numero;
}""")

    assert resultado["valido"]
    assert "(local $local_0 i32)" in resultado["wat"]
    assert "local.get $local_0" in resultado["wat"]
    assert "local.set $local_0" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 15


def test_declaraciones_explicitas_e_inferidas_y_varias_operaciones():
    resultado = compilar_programa("""fn main() -> i32 {
    let base: i32 = 8;
    let factor = 3;
    let mut resultado = base * factor;
    resultado += 2;
    resultado *= 2;
    resultado -= 4;
    resultado /= 2;
    return resultado;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 24


def test_inicializacion_posterior_y_asignaciones_compuestas():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut valor: i32;
    valor = 20;
    valor /= 3;
    valor += 1;
    return valor;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 7


def test_sombras_usando_identidades_distintas_de_resolucion():
    resultado = compilar_programa("""fn main() -> i32 {
    let valor = 10;
    {
        let valor = 3;
        let mut copia = valor * 2;
        copia += 1;
    }
    return valor;
}""")

    assert resultado["valido"]
    assert "(local $local_0 i32)" in resultado["wat"]
    assert "(local $local_1 i32)" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 10


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> i32 {
    let valor = 1;
    valor = 2;
    return valor;
}""",
        """fn main() -> i32 {
    let valor: i32;
    return valor;
}""",
        """fn main() -> i32 {
    let valor: i32 = true;
    return 0;
}""",
    ],
)
def test_errores_de_kevin_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wat"] is None
    assert resultado["wasm"] is None


@pytest.mark.parametrize(
    ("expresion", "esperado"),
    [
        ("10 > 5", 1),
        ("10 < 5", 0),
        ("true && false", 0),
        ("true || false", 1),
        ("!false", 1),
    ],
)
def test_booleanos_y_comparaciones_basicas(expresion, esperado):
    resultado = compilar_programa(f"""fn main() -> bool {{
    return {expresion};
}}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_comparaciones_de_variables_i32_y_variables_bool():
    resultado = compilar_programa("""fn main() -> bool {
    let limite: i32 = 10;
    let actual = 7;
    let mut activo: bool = false;
    activo = !(actual >= limite);
    return activo && (actual < limite) && (activo == true);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_precedencia_y_expresiones_booleanas_anidadas():
    resultado = compilar_programa("""fn main() -> bool {
    return !false && ((2 + 3 * 2) == 8 || false);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


@pytest.mark.parametrize(
    "expresion, esperado",
    [
        ("false && (10 / 0 == 1)", 0),
        ("true || (10 / 0 == 1)", 1),
    ],
)
def test_operadores_logicos_hacen_cortocircuito_real(expresion, esperado):
    resultado = compilar_programa(f"""fn main() -> bool {{
    return {expresion};
}}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_tipo_incompatible_rechazado_por_kevin_no_genera_wasm():
    resultado = compilar_programa("""fn main() -> bool {
    return true + false;
}""")

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wasm"] is None
