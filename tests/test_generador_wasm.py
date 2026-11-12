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


def test_ciclos_no_soportados_no_generan_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    while false {
        break;
    }
    return 10;
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


def test_llamada_principal_a_funcion_con_parametros():
    resultado = compilar_programa("""fn sumar(a: i32, b: i32) -> i32 {
    return a + b;
}

fn main() -> i32 {
    return sumar(10, 20);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 30


def test_funcion_declarada_despues_y_exportada_con_argumentos():
    resultado = compilar_programa("""fn main() -> i32 {
    return doble(9);
}

fn doble(numero: i32) -> i32 {
    return numero * 2;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 18
    assert ejecutar_modulo_wasm(resultado["wasm"], "doble", 11) == 22


def test_llamadas_anidadas_y_resultados_en_variables():
    resultado = compilar_programa("""fn sumar(a: i32, b: i32) -> i32 {
    return a + b;
}

fn main() -> i32 {
    let valor = sumar(sumar(1, 2), 3);
    return valor * sumar(2, 2);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 24


def test_parametro_mutable_y_parametros_booleanos():
    resultado = compilar_programa("""fn incrementar(mut numero: i32) -> i32 {
    numero += 1;
    return numero;
}

fn negar(valor: bool) -> bool {
    return !valor;
}

fn main() -> bool {
    return negar(incrementar(4) == 5);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "incrementar", 9) == 10
    assert ejecutar_modulo_wasm(resultado["wasm"], "negar", 0) == 1
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 0


def test_funciones_unit_y_llamadas_como_sentencias():
    resultado = compilar_programa("""fn registrar(valor: i32) {
    return;
}

fn sumar(a: i32, b: i32) -> i32 {
    return a + b;
}

fn main() -> i32 {
    registrar(10);
    sumar(1, 2);
    return 7;
}""")

    assert resultado["valido"]
    assert "call $funcion_1\n    drop" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "registrar", 10) is None
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 7


@pytest.mark.parametrize(
    "codigo",
    [
        """fn uno(valor: i32) -> i32 {
    return valor;
}
fn main() -> i32 {
    return uno();
}""",
        """fn uno(valor: i32) -> i32 {
    return valor;
}
fn main() -> i32 {
    return uno(true);
}""",
        """fn main() -> i32 {
    return inexistente(1);
}""",
    ],
)
def test_errores_de_llamadas_rechazados_por_kevin(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wat"] is None
    assert resultado["wasm"] is None


def test_if_else_principal_con_funcion_y_parametros():
    resultado = compilar_programa("""fn mayor(a: i32, b: i32) -> i32 {
    if a > b {
        return a;
    } else {
        return b;
    }
}

fn main() -> i32 {
    return mayor(15, 8);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 15
    assert ejecutar_modulo_wasm(resultado["wasm"], "mayor", 2, 9) == 9


def test_if_sin_else_y_else_if():
    resultado = compilar_programa("""fn clasificar(numero: i32) -> i32 {
    let mut resultado = 0;
    if numero > 0 {
        resultado = 1;
    }
    if numero < 0 {
        return -1;
    } else if numero == 0 {
        return 0;
    } else {
        return resultado;
    }
}

fn main() -> i32 {
    return clasificar(3);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "clasificar", 3) == 1
    assert ejecutar_modulo_wasm(resultado["wasm"], "clasificar", 0) == 0
    assert ejecutar_modulo_wasm(resultado["wasm"], "clasificar", -4) == -1


def test_condicionales_anidados_ambitos_y_modificacion_externa():
    resultado = compilar_programa("""fn ajustar(mut valor: i32, activo: bool) -> i32 {
    if activo {
        let mut valor = 50;
        if valor > 10 {
            valor = valor + 1;
        }
    } else {
        valor += 2;
    }
    return valor;
}

fn main() -> i32 {
    return ajustar(10, false);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "ajustar", 10, 1) == 10
    assert ejecutar_modulo_wasm(resultado["wasm"], "ajustar", 10, 0) == 12


def test_bool_unit_y_retorno_anticipado_en_condicionales():
    resultado = compilar_programa("""fn es_positivo(numero: i32) -> bool {
    if numero > 0 {
        return true;
    }
    return false;
}

fn registrar(activo: bool) {
    if activo {
        return;
    }
    return;
}

fn main() -> bool {
    registrar(true);
    return es_positivo(-2);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "es_positivo", 4) == 1
    assert ejecutar_modulo_wasm(resultado["wasm"], "registrar", 0) is None
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 0


def test_rama_no_ejecutada_no_divide_entre_cero():
    resultado = compilar_programa("""fn main() -> i32 {
    if false {
        return 10 / 0;
    } else {
        return 7;
    }
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 7


def test_recursion_factorial_con_if_else():
    resultado = compilar_programa("""fn factorial(numero: i32) -> i32 {
    if numero <= 1 {
        return 1;
    } else {
        return numero * factorial(numero - 1);
    }
}

fn main() -> i32 {
    return factorial(5);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 120


def test_condicion_no_booleana_rechazada_por_kevin():
    resultado = compilar_programa("""fn main() -> i32 {
    if 10 {
        return 1;
    }
    return 0;
}""")

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wasm"] is None
