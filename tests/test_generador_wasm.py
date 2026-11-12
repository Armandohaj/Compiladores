import math
from concurrent.futures import ThreadPoolExecutor

import pytest
import wasmtime

import generador_wasm
from generador_wasm import (
    ErrorGeneracion,
    compilar_programa,
    ejecutar_modulo_wasm,
    ejecutar_string_wasm,
)
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


def test_compila_y_ejecuta_el_arreglo_i32_principal():
    resultado = compilar_programa("""fn main() -> i32 {
    let numeros: [i32; 3] = [10, 20, 30];
    return numeros[1];
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 20


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


def test_while_principal_y_condicion_inicialmente_falsa():
    resultado = compilar_programa("""fn contar(limite: i32) -> i32 {
    let mut contador = 0;
    while contador < limite {
        contador += 1;
    }
    return contador;
}

fn main() -> i32 {
    return contar(5);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 5
    assert ejecutar_modulo_wasm(resultado["wasm"], "contar", -1) == 0


def test_loop_break_y_continue_en_while_y_loop():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut contador = 0;
    let mut suma = 0;
    while contador < 5 {
        contador += 1;
        if contador == 3 {
            continue;
        }
        suma += contador;
    }
    loop {
        contador += 1;
        if contador < 8 {
            continue;
        }
        break;
    }
    return suma + contador;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 20


def test_ciclos_anidados_break_y_continue_afectan_el_mas_cercano():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut externo = 0;
    let mut total = 0;
    while externo < 3 {
        externo += 1;
        let mut interno = 0;
        loop {
            interno += 1;
            if interno == 2 {
                break;
            }
            continue;
        }
        total += interno;
    }
    return total * 10 + externo;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 63


def test_variables_llamadas_y_return_dentro_de_ciclos():
    resultado = compilar_programa("""fn doble(valor: i32) -> i32 {
    return valor * 2;
}

fn buscar() -> i32 {
    let mut valor = 0;
    loop {
        valor += 1;
        if valor == 4 {
            return doble(valor);
        }
    }
    return 0;
}

fn principal_unit() {
    let mut valor = 0;
    while valor < 2 {
        valor += 1;
    }
    return;
}

fn main() -> i32 {
    principal_unit();
    return buscar();
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "principal_unit") is None
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 8


def test_camino_no_ejecutado_en_ciclo_no_provoca_trap():
    resultado = compilar_programa("""fn main() -> i32 {
    while false {
        let valor = 10 / 0;
        return valor;
    }
    return 9;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 9


def test_errores_de_ciclos_de_kevin_no_generan_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    break;
    return 0;
}""")

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wasm"] is None


def test_f64_prueba_obligatoria_con_parametros_y_retorno():
    resultado = compilar_programa("""fn calcular(a: f64, b: f64) -> f64 {
    return a + b;
}

fn main() -> f64 {
    return calcular(4.5, 2.25);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(6.75)
    assert ejecutar_modulo_wasm(resultado["wasm"], "calcular", 1.5, 2.0) == pytest.approx(3.5)


def test_aritmetica_negacion_y_precedencia_f64():
    resultado = compilar_programa("""fn main() -> f64 {
    return -(1.5 + 2.5) * 3.0 / 2.0 - 0.25;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(-6.25)


def test_variables_f64_y_asignaciones_compuestas():
    resultado = compilar_programa("""fn main() -> f64 {
    let mut valor: f64 = 1.5;
    valor += 2.5;
    valor *= 3.0;
    valor -= 1.0;
    valor /= 2.0;
    return valor;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(5.5)


def test_llamadas_anidadas_y_comparaciones_f64():
    resultado = compilar_programa("""fn promedio(a: f64, b: f64) -> f64 {
    return (a + b) / 2.0;
}

fn main() -> bool {
    let valor = promedio(promedio(2.0, 6.0), 8.0);
    return valor >= 6.0 && valor != 7.0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_f64_en_condiciones_y_ciclos():
    resultado = compilar_programa("""fn main() -> f64 {
    let mut valor = 0.0;
    while valor < 1.0 {
        valor += 0.25;
    }
    if valor == 1.0 {
        return valor;
    }
    return 0.0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(1.0)


def test_division_f64_por_cero_sigue_ieee_754():
    infinito = compilar_programa("""fn main() -> f64 {
    return 1.0 / 0.0;
}""")
    indefinido = compilar_programa("""fn main() -> f64 {
    return 0.0 / 0.0;
}""")

    assert infinito["valido"] and indefinido["valido"]
    assert math.isinf(ejecutar_modulo_wasm(infinito["wasm"]))
    assert math.isnan(ejecutar_modulo_wasm(indefinido["wasm"]))


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> f64 {
    return 1.0 + 1;
}""",
        """fn main() -> f64 {
    return 5.0 % 2.0;
}""",
    ],
)
def test_operaciones_f64_invalidas_rechazadas_por_kevin(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert any(error["fase"] == "semantico" for error in resultado["errores"])
    assert resultado["wasm"] is None


def test_char_prueba_principal_con_variable_y_llamada():
    resultado = compilar_programa("""fn obtener() -> char {
    let letra: char = 'A';
    return letra;
}

fn main() -> char {
    return obtener();
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 65


@pytest.mark.parametrize(
    ("literal", "esperado"),
    [
        ("'A'", 65),
        ("'ñ'", ord("ñ")),
        ("'中'", ord("中")),
        (r"'\n'", 10),
        (r"'\r'", 13),
        (r"'\t'", 9),
        (r"'\0'", 0),
        (r"'\\'", 92),
        (r"'\''", 39),
        (r"'\"'", 34),
    ],
)
def test_literales_char_unicode_y_escapes(literal, esperado):
    resultado = compilar_programa(f"""fn main() -> char {{
    return {literal};
}}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_variables_asignacion_parametros_y_llamadas_char():
    resultado = compilar_programa("""fn identidad(letra: char) -> char {
    return letra;
}

fn siguiente(letra: char) -> char {
    let mut copia = letra;
    copia = '中';
    return identidad(copia);
}

fn main() -> char {
    return siguiente('ñ');
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "identidad", 65) == 65
    assert ejecutar_modulo_wasm(resultado["wasm"]) == ord("中")


def test_igualdad_diferencia_y_condicion_char():
    resultado = compilar_programa("""fn coincide(a: char, b: char) -> bool {
    return a == b;
}

fn main() -> i32 {
    let letra = 'ñ';
    if coincide(letra, 'ñ') && letra != 'A' {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"], "coincide", ord("A"), ord("B")) == 0
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> char {
    return 'ab';
}""",
        """fn main() -> char {
    return 'A' + 'B';
}""",
        """fn main() -> bool {
    return 'A' < 'B';
}""",
    ],
)
def test_chars_invalidos_o_con_operaciones_no_permitidas_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_string_prueba_principal_y_memoria_exportada():
    resultado = compilar_programa("""fn identidad(texto: String) -> String {
    return texto;
}

fn main() -> String {
    let mensaje: String = "Hola";
    return identidad(mensaje);
}""")

    assert resultado["valido"]
    assert '(memory (export "memory") 1)' in resultado["wat"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "Hola"


@pytest.mark.parametrize(
    ("literal", "esperado"),
    [
        ('""', ""),
        ('"Adiós"', "Adiós"),
        ('"ñ"', "ñ"),
        ('"中"', "中"),
        (r'"línea\nfinal"', "línea\nfinal"),
        (r'"a\rb"', "a\rb"),
        (r'"a\tb"', "a\tb"),
        (r'"a\0b"', "a\0b"),
        (r'"\"cita\""', '"cita"'),
        (r'"a\\b"', "a\\b"),
    ],
)
def test_strings_unicode_vacias_y_escapes(literal, esperado):
    resultado = compilar_programa(f"""fn main() -> String {{
    return {literal};
}}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == esperado


def test_variables_asignaciones_y_llamadas_anidadas_string():
    resultado = compilar_programa("""fn identidad(texto: String) -> String {
    return texto;
}

fn envolver(texto: String) -> String {
    let mut copia = texto;
    copia = "final";
    return identidad(copia);
}

fn main() -> String {
    let mensaje = "inicial";
    return envolver(mensaje);
}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "final"


def test_igualdad_string_por_contenido_y_condicionales():
    resultado = compilar_programa("""fn iguales(a: String, b: String) -> bool {
    return a == b;
}

fn main() -> i32 {
    let primero = "Hola";
    let segundo = "Hola";
    let distinto = "Holaa";
    if iguales(primero, segundo) && primero != distinto {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert "call $string_eq" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> String {
    return "a" + "b";
}""",
        """fn main() -> bool {
    return "a" < "b";
}""",
        """fn main() -> String {
    return 1;
}""",
    ],
)
def test_operaciones_y_tipos_string_invalidos_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_datos_estaticos_string_mayores_a_64_kib_usando_dos_paginas():
    texto = "x" * 70000
    resultado = compilar_programa(f'''fn main() -> String {{
    return "{texto}";
}}''')

    assert resultado["valido"]
    assert '(memory (export "memory") 2)' in resultado["wat"]
    assert ejecutar_string_wasm(resultado["wasm"]) == texto


def test_compilaciones_concurrentes_no_comparten_literales_string():
    entradas = [("uno", "uno"), ("dos", "dos"), ("中", "中"), ("ñ", "ñ")] * 4

    def compilar_y_leer(esperado):
        codigo = f'''fn main() -> String {{ return "{esperado}"; }}'''
        resultado = compilar_programa(codigo)
        return resultado["valido"], ejecutar_string_wasm(resultado["wasm"])

    with ThreadPoolExecutor(max_workers=4) as ejecutor:
        resultados = list(ejecutor.map(lambda entrada: compilar_y_leer(entrada[0]), entradas))

    assert resultados == [(True, esperado) for _, esperado in entradas]


def test_limite_de_memoria_estatica_genera_error_controlado(monkeypatch):
    monkeypatch.setattr(generador_wasm, "MAX_PAGINAS_MEMORIA", 1)
    texto = "x" * 65529
    resultado = compilar_programa(f'''fn main() -> String {{
    return "{texto}";
}}''')

    assert not resultado["valido"]
    assert resultado["errores"][0]["fase"] == "generacion"
    assert resultado["wasm"] is None


def test_arreglo_i32_inferido_indices_y_elementos_calculados():
    resultado = compilar_programa("""fn main() -> i32 {
    let numeros = [2 + 3, 4 * 5, 30 - 1];
    return numeros[0] + numeros[2];
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 34


def test_arreglo_i32_acepta_indices_variables_y_expresiones():
    resultado = compilar_programa("""fn main() -> i32 {
    let numeros: [i32; 4] = [10, 20, 30, 40];
    let indice = 1;
    return numeros[indice + 2];
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 40


def test_arreglos_locales_diferentes_y_llamadas_repetidas():
    resultado = compilar_programa("""fn obtener(base: i32) -> i32 {
    let primero = [base, base + 1];
    let segundo = [base + 2, base + 3];
    return primero[1] + segundo[0];
}

fn main() -> i32 {
    return obtener(10) + obtener(20);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 66


def test_arreglos_en_llamadas_recursivas_no_comparten_memoria():
    resultado = compilar_programa("""fn sumar(n: i32) -> i32 {
    let valores = [n, n + 1];
    if n == 0 {
        return valores[0];
    }
    return sumar(n - 1) + valores[1];
}

fn main() -> i32 {
    return sumar(3);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 9


@pytest.mark.parametrize("indice", ["0 - 1", "1 + 2"])
def test_indices_dinamicos_fuera_de_rango_producen_trap(indice):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    let numeros = [10, 20];
    let indice = {indice};
    return numeros[indice];
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> i32 {
    let numeros: [i32; 3] = [1, 2];
    return 0;
}""",
        """fn main() -> i32 {
    let numeros: [i32; 2] = [1, true];
    return 0;
}""",
        """fn main() -> i32 {
    let valores: [f64; 2] = [1.0, true];
    return 0;
}""",
        """fn main() -> i32 {
    let textos: [String; 2] = ["a", 1];
    return 0;
}""",
    ],
)
def test_errores_semanticos_de_arreglos_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_arreglos_bool_y_char_explicitos_e_inferidos():
    booleanos = compilar_programa("""fn main() -> bool {
    let valores: [bool; 3] = [true, false, true];
    return valores[0] == valores[2] && !valores[1];
}""")
    caracteres = compilar_programa("""fn main() -> char {
    let valores = ['A', 'ñ'];
    return valores[1];
}""")

    assert booleanos["valido"]
    assert ejecutar_modulo_wasm(booleanos["wasm"]) == 1
    assert caracteres["valido"]
    assert ejecutar_modulo_wasm(caracteres["wasm"]) == ord("ñ")


def test_arreglos_f64_usan_alineacion_y_operaciones_reales():
    resultado = compilar_programa("""fn main() -> f64 {
    let mensaje = "dato";
    let primero: [f64; 2] = [1.5, 2.25];
    let segundo = [3.0, 4.5];
    let indice = 1;
    return primero[indice] + segundo[0] * segundo[indice];
}""")

    assert resultado["valido"]
    assert "f64.store offset=8 align=8" in resultado["wat"]
    assert "f64.load align=8" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(15.75)


def test_arreglos_f64_en_llamadas_recursivas_no_comparten_memoria():
    resultado = compilar_programa("""fn sumar(n: i32) -> f64 {
    let valores = [1.0, 2.5];
    if n == 0 {
        return valores[0];
    }
    return sumar(n - 1) + valores[1];
}

fn main() -> f64 {
    return sumar(3);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(8.5)


@pytest.mark.parametrize("indice", ["0 - 1", "1 + 2"])
def test_indices_invalidos_en_arreglos_f64_producen_trap(indice):
    resultado = compilar_programa(f"""fn main() -> f64 {{
    let valores = [1.0, 2.0];
    let indice = {indice};
    return valores[indice];
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


def test_matrices_y_asignaciones_de_arreglos_se_rechazan_controladamente():
    casos = [
        """fn main() -> i32 {
    let valores: [[i32; 1]; 1] = [[1]];
    return valores[0][0];
}""",
        """fn main() -> i32 {
    let mut valores = [1, 2];
    valores = [3, 4];
    return valores[0];
}""",
    ]

    for codigo in casos:
        resultado = compilar_programa(codigo)
        assert not resultado["valido"]
        assert resultado["errores"][0]["fase"] == "generacion"
        assert resultado["wasm"] is None


def test_arreglo_string_explicito_recupera_el_elemento_principal():
    resultado = compilar_programa("""fn main() -> String {
    let mensajes: [String; 3] = ["Hola", "Adiós", "RustiQ"];
    return mensajes[1];
}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "Adiós"


@pytest.mark.parametrize(
    ("literal", "indice", "esperado"),
    [
        ('["", "ñ"]', 0, ""),
        (r'["a\n", "中"]', 1, "中"),
        (r'["\t", "a\0b"]', 0, "\t"),
        (r'["\t", "a\0b"]', 1, "a\0b"),
    ],
)
def test_arreglos_string_inferidos_unicode_y_escapes(literal, indice, esperado):
    resultado = compilar_programa(f"""fn main() -> String {{
    let textos = {literal};
    return textos[{indice}];
}}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == esperado


def test_arreglos_string_indices_comparaciones_y_condicionales():
    resultado = compilar_programa("""fn main() -> String {
    let primero = ["igual", "distinto"];
    let segundo = ["igual", "final"];
    let indice = 0;
    if primero[indice + 1] != segundo[indice + 1] && primero[indice] == segundo[indice] {
        return segundo[indice + 1];
    }
    return primero[indice];
}""")

    assert resultado["valido"]
    assert "call $string_eq" in resultado["wat"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "final"


def test_elementos_string_en_declaraciones_llamadas_y_arreglos_distintos():
    resultado = compilar_programa("""fn identidad(texto: String) -> String {
    return texto;
}

fn main() -> String {
    let primero = ["uno", "dos"];
    let segundo: [String; 2] = ["tres", "cuatro"];
    let elegido = primero[1];
    if elegido == "dos" {
        return identidad(segundo[0]);
    }
    return elegido;
}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "tres"


def test_arreglos_string_en_llamadas_recursivas():
    resultado = compilar_programa("""fn elegir(n: i32) -> String {
    let textos = ["base", "recursivo"];
    if n == 0 {
        return textos[0];
    }
    elegir(n - 1);
    return textos[1];
}

fn main() -> String {
    return elegir(3);
}""")

    assert resultado["valido"]
    assert ejecutar_string_wasm(resultado["wasm"]) == "recursivo"


@pytest.mark.parametrize("indice", ["0 - 1", "1 + 2"])
def test_indices_invalidos_en_arreglos_string_producen_trap(indice):
    resultado = compilar_programa(f"""fn main() -> String {{
    let textos = ["uno", "dos"];
    let indice = {indice};
    return textos[indice];
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])
