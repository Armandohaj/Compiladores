import hashlib
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
from ejecutar_wasm import ejecutar_archivo_wasm, ejecutar_main_con_entradas
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


def test_read_y_print_generan_imports_y_ejecutan_el_programa_obligatorio(tmp_path, capsys):
    resultado = compilar_programa("""fn main() -> i32 {
    let primero: i32 = read();
    let segundo: i32 = read();
    let resultado = primero + segundo;
    print(primero);
    print(segundo);
    print(resultado);
    return resultado;
}""")

    assert resultado["valido"]
    assert '(import "env" "read_i32" (func $read_i32 (result i32)))' in resultado["wat"]
    assert '(import "env" "print_i32" (func $print_i32 (param i32)))' in resultado["wat"]
    assert ejecutar_main_con_entradas(resultado["wasm"], [15, 22]) == (37, [15, 22, 37])

    archivo = tmp_path / "entrada-salida.wasm"
    archivo.write_bytes(resultado["wasm"])
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()
    assert ejecutar_archivo_wasm(archivo, entradas=[15, 22]) == 0
    assert "Salida: 37" in capsys.readouterr().out
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


def test_read_y_print_funcionan_en_funciones_condiciones_y_ciclos():
    resultado = compilar_programa("""fn doble_entrada() -> i32 {
    return read() * 2;
}

fn main() -> i32 {
    let mut total = 0;
    if read() > 0 {
        total = doble_entrada();
    }
    while total < 6 {
        print(total);
        total += 1;
    }
    return total;
}""")

    assert resultado["valido"]
    assert ejecutar_main_con_entradas(resultado["wasm"], [1, 2]) == (6, [4, 5])


def test_tupla_local_obligatoria_lectura_y_asignacion_compuesta():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut datos = (10, true);
    datos.0 += 5;
    return datos.0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 15


def test_tuplas_locales_explicitas_e_inferidas_con_f64():
    explicita = compilar_programa("""fn main() -> f64 {
    let mut datos: (i32, f64, char) = (10 + 2, 2.5 * 2.0, 'x');
    datos.1 /= 2.0;
    return datos.1;
}""")
    inferida = compilar_programa("""fn main() -> i32 {
    let datos = (4, false, 'ñ');
    if !datos.1 && datos.2 == 'ñ' {
        return datos.0;
    }
    return 0;
}""")

    assert explicita["valido"]
    assert "f64.load offset=8 align=8" in explicita["wat"]
    assert ejecutar_modulo_wasm(explicita["wasm"]) == pytest.approx(2.5)
    assert inferida["valido"]
    assert ejecutar_modulo_wasm(inferida["wasm"]) == 4


def test_asignaciones_simples_y_compuestas_a_campos_de_tupla():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut datos = (20, 2, true, 'a');
    datos.1 = 5;
    datos.2 = false;
    datos.3 = 'z';
    datos.0 -= 4;
    datos.0 *= 2;
    datos.0 /= 4;
    if !datos.2 && datos.3 == 'z' {
        return datos.0 + datos.1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 13


def test_dos_tuplas_locales_tienen_almacenamiento_independiente():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut izquierda = (1, 2);
    let mut derecha = (10, 20);
    izquierda.0 = 50;
    derecha.1 += 5;
    return izquierda.0 + izquierda.1 + derecha.0 + derecha.1;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 87


@pytest.mark.parametrize(
    "codigo",
    [
        "fn main() -> i32 { let datos = (1, true); datos.0 = 2; return datos.0; }",
        "fn main() -> i32 { let datos = (1, true); datos.1 += true; return datos.0; }",
        "fn main() -> i32 { let datos = (1, \"texto\"); return datos.0; }",
        "fn main() -> i32 { let datos = (1, (2, true)); return datos.0; }",
        "fn main() -> i32 { let primero = (1, true); let segundo = primero; return segundo.0; }",
    ],
)
def test_tuplas_no_admitidas_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_estructura_local_obligatoria_lectura_y_asignacion_compuesta():
    resultado = compilar_programa("""struct Persona {
    edad: i32,
    activo: bool
}

fn main() -> i32 {
    let mut persona = Persona { edad: 20, activo: true };
    persona.edad += 1;
    return persona.edad;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 21


def test_estructuras_explicitas_inferidas_y_orden_de_constructor():
    resultado = compilar_programa("""struct Medida {
    activo: bool,
    valor: f64,
    letra: char,
    entero: i32
}

fn main() -> f64 {
    let mut medida: Medida = Medida { letra: 'ñ', entero: 2, valor: 3.5, activo: true };
    medida.valor *= 2.0;
    if medida.activo && medida.letra == 'ñ' {
        return medida.valor + 2.0;
    }
    return 0.0;
}""")
    orden = compilar_programa("""struct Par { primero: i32, segundo: i32 }
fn main() -> i32 {
    let par = Par { segundo: read(), primero: read() };
    return par.primero * 10 + par.segundo;
}""")

    assert resultado["valido"]
    assert "f64.load offset=8 align=8" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == pytest.approx(9.0)
    assert orden["valido"]
    assert ejecutar_main_con_entradas(orden["wasm"], [2, 3]) == (32, [])


def test_asignaciones_simples_y_compuestas_a_campos_de_estructura():
    resultado = compilar_programa("""struct Datos {
    entero: i32,
    decimal: f64,
    activo: bool,
    letra: char
}

fn main() -> i32 {
    let mut datos = Datos { letra: 'a', activo: true, decimal: 2.0, entero: 20 };
    datos.activo = false;
    datos.letra = 'z';
    datos.entero -= 4;
    datos.entero *= 2;
    datos.entero /= 4;
    datos.decimal += 1.5;
    if !datos.activo && datos.letra == 'z' && datos.decimal == 3.5 {
        return datos.entero;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 8


def test_estructuras_independientes_en_condicionales_y_ciclos():
    resultado = compilar_programa("""struct Contador { valor: i32, activo: bool }
fn main() -> i32 {
    let mut primero = Contador { valor: 0, activo: true };
    let mut segundo = Contador { valor: 10, activo: false };
    while primero.valor < 3 {
        primero.valor += 1;
    }
    if primero.activo {
        segundo.valor = segundo.valor + primero.valor;
    }
    return primero.valor + segundo.valor;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 16


@pytest.mark.parametrize(
    "codigo",
    [
        "struct P { x: i32 } fn main() -> i32 { let p = P { x: 1 }; p.x = 2; return p.x; }",
        "struct P { x: i32 } fn main() -> i32 { let p = P { x: 1 }; let q = p; return q.x; }",
        "struct P { x: String } fn main() -> i32 { let p = P { x: \"a\" }; return 0; }",
        "struct P { x: i32 } struct Q { p: P } fn main() -> i32 { let q = Q { p: P { x: 1 } }; return 0; }",
    ],
)
def test_estructuras_no_admitidas_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_retornos_implicitos_obligatorios_y_bloques_con_valor():
    directo = compilar_programa("""fn main() -> i32 {
    let numero = 10;
    numero + 20
}""")
    inicializador = compilar_programa("""fn main() -> i32 {
    let resultado = {
        let base = 10;
        base + 5
    };
    return resultado;
}""")
    funciones = compilar_programa("""fn sumar(numero: i32) -> i32 {
    numero + 1
}

fn main() -> i32 {
    sumar(20)
}""")

    assert directo["valido"]
    assert ejecutar_modulo_wasm(directo["wasm"]) == 30
    assert inicializador["valido"]
    assert ejecutar_modulo_wasm(inicializador["wasm"]) == 15
    assert funciones["valido"]
    assert ejecutar_modulo_wasm(funciones["wasm"]) == 21


def test_bloques_con_valor_en_argumentos_y_tipos_primitivos():
    argumentos = compilar_programa("""fn sumar(valor: i32) -> i32 {
    valor + 1
}

fn main() -> i32 {
    sumar({ let base = 20; base })
}""")
    primitivos = compilar_programa("""fn main() -> i32 {
    let decimal = { let valor = 2.5; valor * 2.0 };
    let bandera = { let valor = true; valor };
    let letra = { let valor = 'ñ'; valor };
    if bandera && letra == 'ñ' && decimal == 5.0 {
        return 1;
    }
    return 0;
}""")
    texto = compilar_programa("""fn main() -> String {
    let mensaje = { let base = "Hola"; base };
    mensaje
}""")

    assert argumentos["valido"]
    assert ejecutar_modulo_wasm(argumentos["wasm"]) == 21
    assert primitivos["valido"]
    assert ejecutar_modulo_wasm(primitivos["wasm"]) == 1
    assert texto["valido"]
    assert ejecutar_string_wasm(texto["wasm"]) == "Hola"


def test_bloques_sin_valor_sombreado_y_return_anticipado():
    resultado = compilar_programa("""fn main() -> i32 {
    let valor = 1;
    {
        let valor = 10;
    }
    let ignorado = {
        return valor + 6;
    } + 1;
    print(99);
    0
}""")

    assert resultado["valido"]
    assert "call $print_i32" not in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 7


def test_match_obligatorio_patrones_basicos_negativos_y_comodin():
    enteros = compilar_programa("""fn main() -> i32 {
    let numero = 2;
    return match numero {
        1 => 10,
        2 => 20,
        _ => 0,
    };
}""")
    booleanos = compilar_programa("""fn main() -> i32 {
    return match true {
        true => 10,
        false => 20,
    };
}""")
    negativos = compilar_programa("""fn main() -> i32 {
    return match -1 {
        -1 => 7,
        _ => 0,
    };
}""")
    caracteres = compilar_programa("""fn main() -> i32 {
    return match 'ñ' {
        'a' => 0,
        'ñ' => 1,
        _ => 2,
    };
}""")

    assert enteros["valido"]
    assert ejecutar_modulo_wasm(enteros["wasm"]) == 20
    assert booleanos["valido"]
    assert ejecutar_modulo_wasm(booleanos["wasm"]) == 10
    assert negativos["valido"]
    assert ejecutar_modulo_wasm(negativos["wasm"]) == 7
    assert caracteres["valido"]
    assert ejecutar_modulo_wasm(caracteres["wasm"]) == 1


def test_match_receptores_sombreado_bloques_y_anidamiento():
    receptores = compilar_programa("""fn main() -> i32 {
    let numero = 5;
    let resultado = match numero {
        numero => {
            let base = numero;
            match true { true => base + 1, false => 0 }
        },
    };
    return numero + resultado;
}""")
    primer_brazo = compilar_programa("""fn main() -> i32 {
    return match 2 {
        2 => 20,
        2 => 30,
        _ => 0,
    };
}""")

    assert receptores["valido"]
    assert ejecutar_modulo_wasm(receptores["wasm"]) == 11
    assert primer_brazo["valido"]
    assert ejecutar_modulo_wasm(primer_brazo["wasm"]) == 20


def test_match_evalua_una_vez_y_ejecuta_solo_el_brazo_elegido():
    resultado = compilar_programa("""fn main() -> i32 {
    return match read() {
        1 => { print(10); 10 },
        _ => { print(20); 20 },
    };
}""")

    assert resultado["valido"]
    assert resultado["wat"].count("call $read_i32") == 1
    assert ejecutar_main_con_entradas(resultado["wasm"], [1]) == (10, [10])
    assert ejecutar_main_con_entradas(resultado["wasm"], [2]) == (20, [20])


def test_match_con_return_anticipado_y_patrones_pendientes_controlados():
    retorno = compilar_programa("""fn main() -> i32 {
    let valor = match 1 {
        1 => { return 9; },
        _ => 0,
    };
    return valor;
}""")
    tupla = compilar_programa("""fn main() -> i32 {
    return match (1, true) {
        (numero, _) => numero,
    };
}""")

    assert retorno["valido"]
    assert ejecutar_modulo_wasm(retorno["wasm"]) == 9
    assert not tupla["valido"]
    assert tupla["wasm"] is None


@pytest.mark.parametrize(
    "codigo",
    [
        "fn main() -> i32 { return read(1); }",
        "fn main() -> i32 { let valor = print(1); return 0; }",
        "fn read() -> i32 { return 1; }",
        "fn main() -> i32 { return print(1); }",
    ],
)
def test_errores_semanticos_de_read_y_print_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


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


def test_constantes_globales_i32_dependencias_y_referencias_adelantadas():
    resultado = compilar_programa("""const LIMITE: i32 = 10;
const DOBLE: i32 = LIMITE * 2;

fn main() -> i32 {
    return DOBLE + 5;
}""")
    adelantada = compilar_programa("""const DOBLE: i32 = BASE * 2;
const BASE: i32 = 11;

fn main() -> i32 {
    return DOBLE;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 25
    assert adelantada["valido"]
    assert ejecutar_modulo_wasm(adelantada["wasm"]) == 22


def test_constantes_globales_f64_bool_char_y_string():
    resultado = compilar_programa("""const PI: f64 = 1.5 + 1.5;
const ACTIVO: bool = 10 > 2 && !false;
const LETRA: char = 'ñ';
const MENSAJE: String = "Hola\\nRustiQ";

fn decimal() -> f64 { return PI; }
fn estado() -> bool { return ACTIVO; }
fn letra() -> char { return LETRA; }
fn texto() -> String { return MENSAJE; }
fn main() -> i32 {
    if ACTIVO { return 1; }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1
    assert ejecutar_modulo_wasm(resultado["wasm"], "decimal") == pytest.approx(3.0)
    assert ejecutar_modulo_wasm(resultado["wasm"], "estado") == 1
    assert ejecutar_modulo_wasm(resultado["wasm"], "letra") == ord("ñ")
    assert ejecutar_string_wasm(resultado["wasm"], "texto") == "Hola\nRustiQ"


def test_variable_local_sombrea_constante_global():
    resultado = compilar_programa("""const VALOR: i32 = 10;

fn main() -> i32 {
    let VALOR = 20;
    return VALOR;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 20


def test_constante_global_no_soportada_genera_error_controlado():
    resultado = compilar_programa("""const DATOS: [i32; 2] = [1, 2];

fn main() -> i32 { return 0; }""")

    assert not resultado["valido"]
    assert resultado["errores"][0]["fase"] == "generacion"
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
    if primero != distinto && iguales(primero, segundo) {
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


def test_matrices_de_tres_dimensiones_y_asignaciones_se_rechazan_controladamente():
    casos = [
        """fn main() -> i32 {
    let valores: [[[i32; 1]; 1]; 1] = [[[1]]];
    return valores[0][0][0];
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


def test_asignacion_simple_a_elemento_de_arreglo():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut numeros = [10, 20, 30];
    numeros[1] = 50;
    return numeros[1];
}""")

    assert resultado["valido"]
    assert "call $array_addr" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 50


def test_asignacion_a_matriz_y_arreglo_f64():
    matriz = compilar_programa("""fn main() -> i32 {
    let mut valores = [[1, 2], [3, 4]];
    valores[1][0] = 30;
    valores[0][1] += 8;
    return valores[1][0] + valores[0][1];
}""")
    decimales = compilar_programa("""fn main() -> f64 {
    let mut valores = [1.5, 2.0];
    valores[1] *= 3.0;
    return valores[1];
}""")

    assert matriz["valido"]
    assert ejecutar_modulo_wasm(matriz["wasm"]) == 40
    assert decimales["valido"]
    assert ejecutar_modulo_wasm(decimales["wasm"]) == pytest.approx(6.0)


@pytest.mark.parametrize("indice", ["0 - 1", "1 + 1"])
def test_asignacion_fuera_de_rango_en_arreglo_produce_trap(indice):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    let mut valores = [1, 2];
    valores[{indice}] = 9;
    return 0;
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


def test_arreglo_string_explicito_compara_el_elemento_principal():
    resultado = compilar_programa("""fn main() -> i32 {
    let mensajes: [String; 3] = ["Hola", "Adiós", "RustiQ"];
    if mensajes[1] == "Adiós" {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


@pytest.mark.parametrize(
    ("literal", "indice"),
    [
        ('["", "ñ"]', 0),
        (r'["a\n", "中"]', 1),
        (r'["\t", "a\0b"]', 0),
        (r'["\t", "a\0b"]', 1),
    ],
)
def test_arreglos_string_inferidos_unicode_y_escapes(literal, indice):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    let textos = {literal};
    if textos[{indice}] == textos[{indice}] {{
        return 1;
    }}
    return 0;
}}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_arreglos_string_indices_comparaciones_y_condicionales():
    resultado = compilar_programa("""fn main() -> i32 {
    let primero = ["igual", "distinto"];
    let segundo = ["igual", "final"];
    let indice = 0;
    if primero[indice + 1] != segundo[indice + 1] && primero[indice] == segundo[indice] {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert "call $string_eq" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_arreglos_string_en_llamadas_y_arreglos_distintos():
    resultado = compilar_programa("""fn coincide(texto: String) -> bool {
    return texto == "dos";
}

fn main() -> i32 {
    let primero = ["uno", "dos"];
    let segundo: [String; 2] = ["tres", "cuatro"];
    if primero[1] == "dos" && segundo[0] == "tres" && coincide("dos") {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_arreglos_string_en_llamadas_recursivas():
    resultado = compilar_programa("""fn elegir(n: i32) -> i32 {
    let textos = ["base", "recursivo"];
    if n == 0 {
        if textos[0] == "base" {
            return 1;
        }
        return 0;
    }
    if textos[1] != "recursivo" {
        return 0;
    }
    return elegir(n - 1) + 1;
}

fn main() -> i32 {
    return elegir(3);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 4


@pytest.mark.parametrize("indice", ["0 - 1", "1 + 2"])
def test_indices_invalidos_en_arreglos_string_producen_trap(indice):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    let textos = ["uno", "dos"];
    let indice = {indice};
    if textos[indice] == "uno" {{
        return 1;
    }}
    return 0;
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


def test_matriz_i32_principal_explicita_e_inferida():
    explicita = compilar_programa("""fn main() -> i32 {
    let matriz: [[i32; 2]; 2] = [[10, 20], [30, 40]];
    return matriz[1][0];
}""")
    inferida = compilar_programa("""fn main() -> i32 {
    let matriz = [[1, 2, 3], [4, 5, 6]];
    return matriz[0][2] + matriz[1][0];
}""")

    assert explicita["valido"]
    assert ejecutar_modulo_wasm(explicita["wasm"]) == 30
    assert inferida["valido"]
    assert ejecutar_modulo_wasm(inferida["wasm"]) == 7


def test_matrices_indices_variables_y_expresiones():
    resultado = compilar_programa("""fn main() -> i32 {
    let matriz = [[10, 20], [30, 40], [50, 60]];
    let fila = 1;
    let columna = 0;
    return matriz[fila + 1][columna + 1];
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 60


def test_matrices_bool_char_y_f64():
    booleanos = compilar_programa("""fn main() -> bool {
    let matriz: [[bool; 2]; 2] = [[true, false], [false, true]];
    return matriz[0][0] && matriz[1][1] && !matriz[0][1];
}""")
    caracteres = compilar_programa("""fn main() -> char {
    let matriz = [['A', 'ñ'], ['中', 'Z']];
    return matriz[1][0];
}""")
    decimales = compilar_programa("""fn main() -> f64 {
    let matriz = [[1.5, 2.25], [3.0, 4.5]];
    return matriz[0][1] + matriz[1][1];
}""")

    assert booleanos["valido"]
    assert ejecutar_modulo_wasm(booleanos["wasm"]) == 1
    assert caracteres["valido"]
    assert ejecutar_modulo_wasm(caracteres["wasm"]) == ord("中")
    assert decimales["valido"]
    assert "f64.load align=8" in decimales["wat"]
    assert ejecutar_modulo_wasm(decimales["wasm"]) == pytest.approx(6.75)


def test_matrices_string_comparaciones_y_condicionales():
    resultado = compilar_programa("""fn main() -> i32 {
    let primera = [["igual", "uno"], ["dos", "final"]];
    let segunda = [["igual", "tres"], ["cuatro", "final"]];
    if primera[0][0] == segunda[0][0] && primera[1][1] == segunda[1][1] {
        return 1;
    }
    return 0;
}""")

    assert resultado["valido"]
    assert "call $string_eq" in resultado["wat"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_matrices_distintas_llamadas_repetidas_y_recursion():
    resultado = compilar_programa("""fn sumar(n: i32) -> i32 {
    let primera = [[n, n + 1]];
    let segunda = [[n + 2, n + 3]];
    if n == 0 {
        return primera[0][0];
    }
    return sumar(n - 1) + primera[0][1] + segunda[0][0];
}

fn main() -> i32 {
    return sumar(2) + sumar(1);
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 17


@pytest.mark.parametrize(
    ("fila", "columna"),
    [("0 - 1", "0"), ("2", "0"), ("0", "0 - 1"), ("0", "2")],
)
def test_indices_invalidos_en_cada_dimension_de_matriz_producen_trap(fila, columna):
    resultado = compilar_programa(f"""fn main() -> i32 {{
    let matriz = [[1, 2], [3, 4]];
    let fila = {fila};
    let columna = {columna};
    return matriz[fila][columna];
}}""")

    assert resultado["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(resultado["wasm"])


@pytest.mark.parametrize(
    "codigo",
    [
        """fn main() -> i32 {
    let matriz: [[i32; 2]; 2] = [[1, 2], [3]];
    return 0;
}""",
        """fn main() -> i32 {
    let matriz: [[i32; 2]; 1] = [[1, true]];
    return 0;
}""",
    ],
)
def test_errores_semanticos_de_matrices_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


def test_asignador_monotonico_crece_memoria_en_un_ciclo():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut indice = 0;
    let mut suma = 0;
    while indice < 20000 {
        let valor = [indice];
        suma += valor[0];
        indice += 1;
    }
    return suma;
}""")

    assert resultado["valido"]
    motor = wasmtime.Engine()
    modulo = wasmtime.Module(motor, resultado["wasm"])
    almacen = wasmtime.Store(motor)
    instancia = wasmtime.Instance(almacen, modulo, [])
    exportaciones = instancia.exports(almacen)
    assert exportaciones["main"](almacen) == 199990000
    assert exportaciones["memory"].size(almacen) == 2
