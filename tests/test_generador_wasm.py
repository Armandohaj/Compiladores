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
    assert "f64.load align=8" in explicita["wat"]
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
    assert "f64.load align=8" in resultado["wat"]
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


def test_match_con_return_anticipado_y_patrones_de_tupla():
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
    assert tupla["valido"]
    wasmtime.Module(wasmtime.Engine(), tupla["wasm"])
    assert ejecutar_modulo_wasm(tupla["wasm"]) == 1


def test_match_tuplas_literales_receptores_y_rechazos_controlados():
    booleanos = compilar_programa("""fn main() -> i32 {
    return match (true, false) {
        (true, _) => 1,
        (false, _) => 0,
    };
}""")
    seleccion = compilar_programa("""fn main() -> i32 {
    return match (false, true) {
        (true, _) => 0,
        (false, true) => 2,
        _ => 3,
    };
}""")
    sombreado = compilar_programa("""fn main() -> i32 {
    let x = 9;
    let y = match (1, true) {
        (x, _) => { let r = &x; *r },
    };
    return x + y;
}""")
    literales = compilar_programa("""fn main() -> i32 {
    return match (1.5, 'ñ') {
        (2.0, _) => 0,
        (1.5, 'ñ') => 1,
        _ => 2,
    };
}""")
    decimal_negativo = compilar_programa("""fn main() -> i32 {
    return match (-1.5, true) {
        (1.5, _) => 9,
        (-1.5, _) => 1,
        _ => 0,
    };
}""")
    variable = compilar_programa("""fn main() -> i32 {
    let datos = (4, false);
    return match datos {
        (x, false) => x,
        _ => 0,
    };
}""")
    anidada = compilar_programa("""fn main() -> i32 {
    return match ((1, true), 2) {
        ((x, _), _) => x,
    };
}""")

    for resultado, esperado in [
        (booleanos, 1), (seleccion, 2), (sombreado, 10), (literales, 1),
        (decimal_negativo, 1), (variable, 4), (anidada, 1),
    ]:
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_match_string_y_f64_generan_comparaciones_reales():
    cadenas = compilar_programa('''fn main() -> i32 {
    return match "hola\\n" {
        "adios" => 0,
        "hola\\n" => 10,
        _ => 20,
    };
}''')
    decimal = compilar_programa('''fn main() -> i32 {
    return match -1.5 {
        1.5 => 0,
        -1.5 => 10,
        _ => 20,
    };
}''')

    for resultado in (cadenas, decimal):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == 10

    for codigo in (
        '''fn main() -> i32 { return match "hola" { 1 => 0, _ => 1, }; }''',
        '''fn main() -> i32 { return match 1.5 { true => 0, _ => 1, }; }''',
    ):
        invalido = compilar_programa(codigo)
        assert not invalido["valido"]
        assert invalido["wasm"] is None


def test_match_string_y_f64_enlazan_receptores_correctos():
    cadenas = compilar_programa('''fn main() -> i32 {
    let texto = "hola";
    return match texto {
        valor => match valor { "hola" => 10, _ => 0, },
    };
}''')
    decimal = compilar_programa('''fn main() -> i32 {
    let valor = 1.5;
    return match valor {
        numero => match numero { 1.5 => 10, _ => 0, },
    };
}''')

    for resultado in (cadenas, decimal):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == 10


def test_match_enum_con_datos_tupla_y_patron_anidado():
    resultado = compilar_programa('''enum Dato {
    Valor((i32, f64)),
    Vacio,
}

fn identidad(dato: Dato) -> Dato {
    return dato;
}

fn main() -> i32 {
    let dato = identidad(Dato::Valor((3, 1.5)));
    return match dato {
        Dato::Valor((numero, 1.5)) => numero,
        Dato::Valor(_) => 0,
        Dato::Vacio => 0,
    };
}''')

    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 3


def test_enum_tupla_string_mueve_y_conserva_el_patron_por_contenido():
    valido = compilar_programa('''enum Dato {
    Valor((String, i32)),
    Vacio,
}

fn identidad(dato: Dato) -> Dato { return dato; }

fn main() -> i32 {
    let dato = identidad(Dato::Valor(("Falló", 3)));
    return match dato {
        Dato::Valor(("Falló", numero)) => numero,
        Dato::Valor(_) => 0,
        Dato::Vacio => 0,
    };
}''')
    invalido = compilar_programa('''enum Dato { Valor((String, i32)), Vacio }
fn main() -> i32 {
    let original = Dato::Valor(("hola", 3));
    let copia = original;
    return match original { Dato::Valor(_) => 1, Dato::Vacio => 0, };
}''')

    assert valido["valido"]
    wasmtime.Module(wasmtime.Engine(), valido["wasm"])
    assert ejecutar_modulo_wasm(valido["wasm"]) == 3
    assert not invalido["valido"]
    assert invalido["wasm"] is None


def test_enumeraciones_sin_datos_obligatorias_variables_y_comparaciones():
    obligatorio = compilar_programa("""enum Estado {
    Pendiente,
    Completado
}

fn main() -> i32 {
    let estado = Estado::Completado;
    return match estado {
        Estado::Pendiente => 0,
        Estado::Completado => 1,
    };
}""")
    variables = compilar_programa("""enum Estado { Completado, Pendiente }
fn main() -> i32 {
    let mut primero: Estado = Estado::Pendiente;
    let segundo = Estado::Completado;
    primero = segundo;
    if primero == Estado::Completado && primero != Estado::Pendiente {
        return 1;
    }
    return 0;
}""")

    assert obligatorio["valido"]
    assert ejecutar_modulo_wasm(obligatorio["wasm"]) == 1
    assert variables["valido"]
    assert ejecutar_modulo_wasm(variables["wasm"]) == 1


def test_match_enumeraciones_anidadas_y_nombres_de_variantes_independientes():
    resultado = compilar_programa("""enum A { Activo, Inactivo }
enum B { Activo, Inactivo }
fn main() -> i32 {
    let primero = A::Activo;
    let segundo = B::Inactivo;
    return match primero {
        A::Activo => match segundo { B::Activo => 10, B::Inactivo => 11 },
        A::Inactivo => 0,
    };
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 11


def test_match_enum_ejecuta_un_solo_brazo_y_respeta_el_comodin():
    resultado = compilar_programa("""enum Estado { Pendiente, Completado, Cancelado }
fn main() -> i32 {
    return match Estado::Completado {
        Estado::Pendiente => { print(0); 0 },
        Estado::Completado => { print(1); 1 },
        _ => { print(2); 2 },
    };
}""")

    assert resultado["valido"]
    assert ejecutar_main_con_entradas(resultado["wasm"], []) == (1, [1])


def test_enumeraciones_con_datos_obligatoria_y_receptores():
    resultado = compilar_programa("""enum Resultado {
    Vacio,
    Correcto(i32),
    Error(i32)
}
fn main() -> i32 {
    let resultado = Resultado::Correcto(25);
    return match resultado {
        Resultado::Vacio => 0,
        Resultado::Correcto(numero) => numero + 5,
        Resultado::Error(codigo) => codigo,
    };
}""")
    varios_datos = compilar_programa("""enum Dato { Vacio, Punto(f64, i32), Marca(bool, char) }
fn main() -> i32 {
    let dato: Dato = Dato::Punto(2.5, 4);
    return match dato {
        Dato::Vacio => 0,
        Dato::Punto(2.5, numero) => numero,
        Dato::Punto(_, _) => 1,
        Dato::Marca(true, 'ñ') => 2,
        Dato::Marca(_, _) => 3,
    };
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 30
    assert varios_datos["valido"]
    assert ejecutar_modulo_wasm(varios_datos["wasm"]) == 4


def test_enumeraciones_con_datos_copia_efectos_y_match_anidado():
    copia = compilar_programa("""enum Dato { Numero(i32), Vacio }
fn main() -> i32 {
    let primero = Dato::Numero(3);
    let mut segundo = { primero };
    segundo = Dato::Numero(9);
    return match primero { Dato::Numero(valor) => valor, Dato::Vacio => 0 };
}""")
    efectos = compilar_programa("""enum Dato { Numero(i32), Vacio }
fn main() -> i32 {
    let dato = Dato::Numero(read());
    return match dato {
        Dato::Numero(valor) => { print(valor); match true { true => valor + 1, false => 0 } },
        Dato::Vacio => { print(99); 0 },
    };
}""")

    assert copia["valido"]
    assert ejecutar_modulo_wasm(copia["wasm"]) == 3
    assert efectos["valido"]
    assert ejecutar_main_con_entradas(efectos["wasm"], [20]) == (21, [20])


def test_enumeraciones_con_datos_string_mueven_y_conservan_contenido():
    principal = compilar_programa("""enum Resultado {
    Correcto(i32),
    Error(String),
    Vacio
}
fn identidad(valor: Resultado) -> Resultado { return valor; }
fn main() -> i32 {
    let resultado = identidad(Resultado::Error("Falló"));
    return match resultado {
        Resultado::Correcto(_) => 0,
        Resultado::Error(_) => 1,
        Resultado::Vacio => 2
    };
}""")
    receptor = compilar_programa("""enum Resultado { Error(String), Vacio }
fn recibir(mensaje: String) -> i32 { return 3; }
fn identidad(valor: Resultado) -> Resultado { return valor; }
fn main() -> i32 {
    let resultado = identidad(Resultado::Error("Falló"));
    return match resultado {
        Resultado::Error(mensaje) => recibir(mensaje),
        Resultado::Vacio => 0
    };
}""")
    reasignacion = compilar_programa("""enum Resultado { Error(String), Vacio }
fn main() -> i32 {
    let mut resultado = Resultado::Error("antes");
    resultado = Resultado::Error("después");
    return match resultado {
        Resultado::Error("después") => 4,
        Resultado::Error(_) => 0,
        Resultado::Vacio => 0
    };
}""")
    movimiento_invalido = compilar_programa("""enum Resultado { Error(String), Vacio }
fn main() -> i32 {
    let resultado = Resultado::Error("Falló");
    let movido = resultado;
    return match resultado { Resultado::Error(_) => 1, Resultado::Vacio => 0 };
}""")

    for resultado, esperado in [(principal, 1), (receptor, 3), (reasignacion, 4)]:
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado
    assert not movimiento_invalido["valido"]
    assert movimiento_invalido["wasm"] is None


def test_patrones_de_enum_f64_negativos_y_string_utf8():
    decimal = compilar_programa("""enum Dato {
    Valor(f64),
    Error(String)
}
fn main() -> i32 {
    let dato = Dato::Valor(-1.5);
    return match dato {
        Dato::Valor(-1.5) => 1,
        Dato::Valor(_) => 0,
        Dato::Error(_) => 0
    };
}""")
    utf8 = compilar_programa("""enum Dato { Valor(i32), Error(String) }
fn main() -> i32 {
    let dato = Dato::Error("Falló");
    return match dato {
        Dato::Valor(_) => 0,
        Dato::Error("Falló") => 2,
        Dato::Error(_) => 0
    };
}""")

    for resultado, esperado in [(decimal, 1), (utf8, 2)]:
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_funciones_con_parametros_y_retornos_de_enumeraciones():
    con_datos = compilar_programa("""enum Resultado { Correcto(i32), Vacio }
fn identidad(valor: Resultado) -> Resultado { return valor; }
fn main() -> i32 {
    let original = Resultado::Correcto(42);
    let dato = identidad(identidad(original));
    return match dato { Resultado::Correcto(n) => n, Resultado::Vacio => 0 };
}""")
    sin_datos = compilar_programa("""enum Estado { Pendiente, Listo }
fn identidad(estado: Estado) -> Estado { estado }
fn main() -> i32 {
    let estado = identidad(identidad(Estado::Listo));
    return match estado { Estado::Pendiente => 0, Estado::Listo => 10 };
}""")
    copia = compilar_programa("""enum Resultado { Correcto(i32), Vacio }
fn identidad(valor: Resultado) -> Resultado { return valor; }
fn main() -> i32 {
    let original = Resultado::Correcto(7);
    let copia = identidad(original);
    return match original { Resultado::Correcto(n) => match copia { Resultado::Correcto(m) => n + m, Resultado::Vacio => 0 }, Resultado::Vacio => 0 };
}""")
    tipos_basicos = compilar_programa("""enum Dato { Medida(f64), Marca(bool, char) }
fn identidad(valor: Dato) -> Dato { valor }
fn main() -> i32 {
    let medida = identidad(Dato::Medida(2.5));
    let marca = identidad(Dato::Marca(true, 'ñ'));
    return match medida {
        Dato::Medida(_) => match marca { Dato::Marca(true, 'ñ') => 12, Dato::Marca(_, _) => 0, Dato::Medida(_) => 0 },
        Dato::Marca(_, _) => 0,
    };
}""")

    for resultado, esperado in [(con_datos, 42), (sin_datos, 10), (copia, 14), (tipos_basicos, 12)]:
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_copias_completas_de_tuplas_y_asignaciones_independientes():
    obligatorio = compilar_programa("""fn main() -> i32 {
    let original = (10, true);
    let mut copia = original;
    copia.0 += 5;
    return original.0 * 10 + copia.0;
}""")
    reasignacion = compilar_programa("""fn main() -> i32 {
    let original = (10, 2.5, true, 'a');
    let mut destino = (1, 1.0, false, 'b');
    destino = original;
    destino.0 = 20;
    destino.1 = 4.5;
    if original.0 == 10 && original.1 == 2.5 && destino.0 == 20 && destino.1 == 4.5 {
        return 1;
    }
    return 0;
}""")

    assert obligatorio["valido"]
    assert ejecutar_modulo_wasm(obligatorio["wasm"]) == 115
    assert reasignacion["valido"]
    assert ejecutar_modulo_wasm(reasignacion["wasm"]) == 1


def test_copias_completas_de_estructuras_y_bloques_con_valor():
    obligatorio = compilar_programa("""struct Punto { x: i32, y: f64 }
fn main() -> i32 {
    let original = Punto { x: 10, y: 2.5 };
    let mut copia = original;
    copia.x = 30;
    return original.x + copia.x;
}""")
    bloque = compilar_programa("""struct Punto { x: i32, y: f64 }
fn main() -> i32 {
    let original = Punto { x: 10, y: 2.5 };
    let mut copia = { original };
    copia.x += 20;
    if original.y == 2.5 && copia.y == 2.5 { return original.x + copia.x; }
    return 0;
}""")

    assert obligatorio["valido"]
    assert ejecutar_modulo_wasm(obligatorio["wasm"]) == 40
    assert bloque["valido"]
    assert ejecutar_modulo_wasm(bloque["wasm"]) == 40


def test_copias_completas_de_arreglos_y_asignaciones_independientes():
    obligatorio = compilar_programa("""fn main() -> i32 {
    let original = [10, 20];
    let mut copia = original;
    copia[0] = 50;
    return original[0] + copia[0];
}""")
    reasignacion = compilar_programa("""fn main() -> i32 {
    let original = [10, 20];
    let mut copia = [1, 2];
    copia = original;
    copia[1] = 50;
    return original[1] + copia[1];
}""")
    tipos = compilar_programa("""fn main() -> i32 {
    let decimales = [1.5, 2.5];
    let mut copia_decimal = { decimales };
    copia_decimal[0] = 3.5;
    let banderas = [true, false];
    let copia_bandera = banderas;
    let letras = ['a', 'ñ'];
    let copia_letra = letras;
    if decimales[0] == 1.5 && copia_decimal[0] == 3.5 && copia_bandera[0] && copia_letra[1] == 'ñ' {
        return 1;
    }
    return 0;
}""")

    assert obligatorio["valido"]
    assert ejecutar_modulo_wasm(obligatorio["wasm"]) == 60
    assert reasignacion["valido"]
    assert ejecutar_modulo_wasm(reasignacion["wasm"]) == 70
    assert tipos["valido"]
    assert ejecutar_modulo_wasm(tipos["wasm"]) == 1


def test_copias_completas_de_matrices_y_rechazos_de_move():
    obligatorio = compilar_programa("""fn main() -> i32 {
    let original = [[1, 2], [3, 4]];
    let mut copia = original;
    copia[1][0] = 30;
    return original[1][0] + copia[1][0];
}""")
    reasignacion = compilar_programa("""fn main() -> i32 {
    let original = [[1.5, 2.5], [3.5, 4.5]];
    let mut copia = [[0.0, 0.0], [0.0, 0.0]];
    copia = { original };
    copia[0][1] = 8.5;
    let banderas = [[true, false], [false, true]];
    let mut copia_bandera = banderas;
    copia_bandera[0][0] = false;
    let letras = [['a', 'b'], ['ñ', '中']];
    let copia_letra = letras;
    if original[0][1] == 2.5 && copia[0][1] == 8.5 && banderas[0][0]
        && !copia_bandera[0][0] && copia_letra[1][1] == '中' { return 1; }
    return 0;
}""")
    move = compilar_programa("""fn main() -> i32 {
    let original = ["texto"];
    let copia = original;
    return 0;
}""")

    assert obligatorio["valido"]
    assert ejecutar_modulo_wasm(obligatorio["wasm"]) == 33
    assert reasignacion["valido"]
    assert ejecutar_modulo_wasm(reasignacion["wasm"]) == 1
    assert move["valido"]
    wasmtime.Module(wasmtime.Engine(), move["wasm"])
    assert ejecutar_modulo_wasm(move["wasm"]) == 0


def test_borrowing_escalar_obligatorio_lecturas_y_escrituras():
    local = compilar_programa("""fn main() -> i32 {
    let mut numero = 10;
    { let referencia = &mut numero; *referencia = 25; }
    numero
}""")
    parametro = compilar_programa("""fn incrementar(r: &mut i32) { *r += 1; }
fn main() -> i32 {
    let mut numero = 10;
    incrementar(&mut numero);
    numero
}""")
    compartidos = compilar_programa("""fn main() -> i32 {
    let numero = 10;
    let a = &numero;
    let b = a;
    *a + *b
}""")
    sombreado = compilar_programa("""fn main() -> i32 {
    let numero = 10;
    let exterior = &numero;
    { let numero = 20; let interior = &numero; if *interior != 20 { return 0; } }
    *exterior
}""")
    transferencia = compilar_programa("""fn main() -> i32 {
    let mut numero = 10;
    let referencia = &mut numero;
    let destino = referencia;
    *destino += 2;
    *destino
}""")

    assert local["valido"]
    assert ejecutar_modulo_wasm(local["wasm"]) == 25
    assert parametro["valido"]
    assert ejecutar_modulo_wasm(parametro["wasm"]) == 11
    assert compartidos["valido"]
    assert ejecutar_modulo_wasm(compartidos["wasm"]) == 20
    assert sombreado["valido"]
    assert ejecutar_modulo_wasm(sombreado["wasm"]) == 10
    assert transferencia["valido"]
    assert ejecutar_modulo_wasm(transferencia["wasm"]) == 12


def test_borrowing_escalar_f64_bool_char_y_rechazos_controlados():
    decimales = compilar_programa("""fn aumentar(r: &mut f64) { *r += 2.0; }
fn main() -> f64 {
    let mut valor = 1.5;
    aumentar(&mut valor);
    valor
}""")
    booleanos = compilar_programa("""fn main() -> bool {
    let valor = true;
    let referencia = &valor;
    !*referencia
}""")
    caracteres = compilar_programa("""fn main() -> char {
    let mut letra = 'a';
    { let referencia = &mut letra; *referencia = 'ñ'; }
    letra
}""")
    conflicto = compilar_programa("""fn main() -> i32 {
    let mut numero = 1;
    let referencia = &numero;
    numero = 2;
    0
}""")
    compuesto = compilar_programa("""fn main() -> i32 {
    let datos = [1, 2];
    let referencia = &datos;
    (*referencia)[0]
}""")
    receptor = compilar_programa("""fn main() -> i32 {
    match 1 { numero => { let referencia = &numero; *referencia } }
}""")

    assert decimales["valido"]
    assert ejecutar_modulo_wasm(decimales["wasm"]) == pytest.approx(3.5)
    assert booleanos["valido"]
    assert ejecutar_modulo_wasm(booleanos["wasm"]) == 0
    assert caracteres["valido"]
    assert ejecutar_modulo_wasm(caracteres["wasm"]) == ord("ñ")
    assert not conflicto["valido"]
    assert conflicto["wasm"] is None
    assert compuesto["valido"]
    wasmtime.Module(wasmtime.Engine(), compuesto["wasm"])
    assert ejecutar_modulo_wasm(compuesto["wasm"]) == 1
    assert receptor["valido"]
    assert ejecutar_modulo_wasm(receptor["wasm"]) == 1


def test_prestamos_de_receptores_match_tipos_sombreado_y_enum():
    booleano = compilar_programa("""fn main() -> bool {
    match true { x => { let r = &x; *r } }
}""")
    caracter = compilar_programa("""fn main() -> char {
    match 'ñ' { x => { let r = &x; *r } }
}""")
    copias_y_brazos = compilar_programa("""fn main() -> i32 {
    let x = 9;
    let y = match 2 {
        1 => 0,
        x => { let a = &x; let b = a; *a + *b }
    };
    x + y
}""")
    enum = compilar_programa("""enum E { A(i32) }
fn main() -> i32 {
    match E::A(3) { E::A(x) => { let r = &x; *r } }
}""")

    assert booleano["valido"]
    assert ejecutar_modulo_wasm(booleano["wasm"]) == 1
    assert caracter["valido"]
    assert ejecutar_modulo_wasm(caracter["wasm"]) == ord("ñ")
    assert copias_y_brazos["valido"]
    assert ejecutar_modulo_wasm(copias_y_brazos["wasm"]) == 13
    assert enum["valido"]
    assert ejecutar_modulo_wasm(enum["wasm"]) == 3


def test_prestamos_de_receptores_match_rechazan_escape_mutable_y_admiten_f64():
    mutable = compilar_programa("""fn main() -> i32 {
    match 1 { x => { let r = &mut x; *r = 2; *r } }
}""")
    escape = compilar_programa("""fn main() -> i32 {
    let r = match 1 { x => &x };
    *r
}""")
    decimal = compilar_programa("""fn main() -> f64 {
    match 1.0 { x => { let r = &x; *r } }
}""")

    assert not mutable["valido"]
    assert mutable["wasm"] is None
    assert not escape["valido"]
    assert escape["wasm"] is None
    assert decimal["valido"]
    wasmtime.Module(wasmtime.Engine(), decimal["wasm"])
    assert ejecutar_modulo_wasm(decimal["wasm"]) == pytest.approx(1.0)


def test_constantes_locales_materializadas_por_id_y_sombreado():
    resultado = compilar_programa("""const BASE: i32 = 10;
fn main() -> i32 {
    const LIMITE: i32 = BASE + 2;
    {
        const BASE: i32 = 20;
        const DOBLE: i32 = BASE * 2;
        DOBLE;
    }
    LIMITE
}""")
    decimal = compilar_programa("""fn main() -> i32 {
    const BASE: f64 = 2.5;
    const LIMITE: f64 = BASE * 2.0;
    if LIMITE == 5.0 { return 1; }
    return 0;
}""")
    invalida = compilar_programa("""fn main() -> i32 {
    let numero = 1;
    const LIMITE: i32 = numero;
    LIMITE
}""")

    assert resultado["valido"]
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 12
    assert decimal["valido"]
    assert ejecutar_modulo_wasm(decimal["wasm"]) == 1
    assert not invalida["valido"]
    assert invalida["wasm"] is None


def test_expresiones_como_sentencias_descartan_valores_y_prestamos_temporales():
    basica = compilar_programa("""fn main() -> i32 {
    10 + 20;
    5
}""")
    efectos = compilar_programa("""fn main() -> i32 {
    let mut numero = 10;
    &mut numero;
    numero = 20;
    match numero { 20 => { 30 }, _ => 0 };
    ({ let valor = 1; valor + 2 });
    numero
}""")
    retorno = compilar_programa("""fn main() -> i32 {
    ({ return 9; });
    0
}""")

    assert basica["valido"]
    assert ejecutar_modulo_wasm(basica["wasm"]) == 5
    assert efectos["valido"]
    assert ejecutar_modulo_wasm(efectos["wasm"]) == 20
    assert retorno["valido"]
    assert ejecutar_modulo_wasm(retorno["wasm"]) == 9


def test_borrowing_estructuras_ejemplo_oficial_y_lecturas_compartidas():
    oficial = compilar_programa("""struct Punto { x: f64, y: f64 }
fn mover_x(p: &mut Punto, dx: f64) { p.x = p.x + dx; }
fn main() -> f64 {
    let mut punto = Punto { x: 1.0, y: 2.0 };
    mover_x(&mut punto, 3.0);
    punto.x
}""")
    compartida = compilar_programa("""struct Punto {
    x: i32, activo: bool, letra: char, valor: f64
}
fn main() -> i32 {
    let punto = Punto { x: 10, activo: true, letra: 'ñ', valor: 2.5 };
    let referencia = &punto;
    if referencia.activo && referencia.letra == 'ñ' && referencia.valor == 2.5 {
        return referencia.x;
    }
    return 0;
}""")

    assert oficial["valido"]
    assert ejecutar_modulo_wasm(oficial["wasm"]) == pytest.approx(4.0)
    assert compartida["valido"]
    assert ejecutar_modulo_wasm(compartida["wasm"]) == 10


def test_borrowing_estructuras_escrituras_compuestas_y_aislamiento():
    mutacion = compilar_programa("""struct Punto { x: i32, y: f64 }
fn cambiar(p: &mut Punto) { p.x += 2; p.y *= 2.0; }
fn main() -> i32 {
    let mut punto = Punto { x: 10, y: 2.5 };
    cambiar(&mut punto);
    if punto.y == 5.0 { return punto.x; }
    return 0;
}""")
    independientes = compilar_programa("""struct Punto { x: i32, y: f64 }
fn mover(p: &mut Punto) { p.x = 30; }
fn main() -> i32 {
    let mut primero = Punto { x: 10, y: 1.0 };
    let mut segundo = Punto { x: 20, y: 2.0 };
    mover(&mut segundo);
    return primero.x + segundo.x;
}""")
    ambitos = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let mut punto = Punto { x: 10 };
    { let exterior = &punto;
      { let punto = Punto { x: 20 }; let interior = &punto; if interior.x != 20 { return 0; } }
      if exterior.x != 10 { return 0; }
    }
    { let referencia = &mut punto; referencia.x = 25; }
    punto.x
}""")
    invalida = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let punto = Punto { x: 1 };
    let referencia = &punto;
    referencia.x = 2;
    0
}""")
    exclusivo = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let mut punto = Punto { x: 1 };
    let referencia = &mut punto;
    referencia.x = 2;
    punto.x
}""")

    assert mutacion["valido"]
    assert ejecutar_modulo_wasm(mutacion["wasm"]) == 12
    assert independientes["valido"]
    assert ejecutar_modulo_wasm(independientes["wasm"]) == 40
    assert ambitos["valido"]
    assert ejecutar_modulo_wasm(ambitos["wasm"]) == 25
    assert not invalida["valido"]
    assert invalida["wasm"] is None
    assert not exclusivo["valido"]
    assert exclusivo["wasm"] is None


def test_borrowing_tuplas_arreglos_y_matrices_obligatorios():
    tupla = compilar_programa("""fn main() -> i32 {
    let mut datos = (10, true);
    { let r = &mut datos; r.0 += 5; }
    datos.0
}""")
    arreglo = compilar_programa("""fn main() -> i32 {
    let mut numeros = [1, 2, 3];
    { let r = &mut numeros; r[1] += 5; }
    numeros[1]
}""")
    matriz = compilar_programa("""fn main() -> i32 {
    let mut datos = [[1, 2], [3, 4]];
    { let r = &mut datos; r[1][0] += 10; }
    datos[1][0]
}""")
    compartidos = compilar_programa("""fn main() -> i32 {
    let datos = (10, true);
    let numeros = [1, 2];
    let matriz = [[3, 4], [5, 6]];
    let tupla = &datos;
    let arreglo = &numeros;
    let tabla = &matriz;
    if tupla.1 && arreglo[0] == 1 { return tabla[1][1] + tupla.0; }
    return 0;
}""")

    assert tupla["valido"]
    assert ejecutar_modulo_wasm(tupla["wasm"]) == 15
    assert arreglo["valido"]
    assert ejecutar_modulo_wasm(arreglo["wasm"]) == 7
    assert matriz["valido"]
    assert ejecutar_modulo_wasm(matriz["wasm"]) == 13
    assert compartidos["valido"]
    assert ejecutar_modulo_wasm(compartidos["wasm"]) == 16


def test_borrowing_compuestos_parametros_f64_e_indices():
    parametros = compilar_programa("""fn cambiar_t(t: &mut (i32, bool)) { t.0 += 2; }
fn cambiar_a(a: &mut [i32; 2]) { a[1] = 9; }
fn cambiar_m(m: &mut [[i32; 2]; 2]) { m[1][0] += 10; }
fn main() -> i32 {
    let mut tupla = (1, true);
    let mut arreglo = [3, 4];
    let mut matriz = [[1, 2], [3, 4]];
    cambiar_t(&mut tupla); cambiar_a(&mut arreglo); cambiar_m(&mut matriz);
    tupla.0 + arreglo[1] + matriz[1][0]
}""")
    decimales = compilar_programa("""fn cambiar_a(a: &mut [f64; 2]) { a[1] *= 2.0; }
fn cambiar_m(m: &mut [[f64; 2]; 2]) { m[1][0] += 1.5; }
fn main() -> f64 {
    let mut arreglo = [1.0, 2.5];
    let mut matriz = [[1.0, 2.0], [3.0, 4.0]];
    cambiar_a(&mut arreglo); cambiar_m(&mut matriz);
    arreglo[1] + matriz[1][0]
}""")
    indices = compilar_programa("""fn main() -> i32 {
    let mut original = [10, 20];
    let mut copia = [30, 40];
    let indice = 0;
    { let r = &mut copia; r[indice] += 5; }
    original[indice] + copia[indice]
}""")
    fuera_de_rango = compilar_programa("""fn main() -> i32 {
    let datos = [[1, 2], [3, 4]];
    let referencia = &datos;
    let fila = 2;
    referencia[fila][0]
}""")

    assert parametros["valido"]
    assert ejecutar_modulo_wasm(parametros["wasm"]) == 25
    assert decimales["valido"]
    assert ejecutar_modulo_wasm(decimales["wasm"]) == pytest.approx(9.5)
    assert indices["valido"]
    assert ejecutar_modulo_wasm(indices["wasm"]) == 45
    assert fuera_de_rango["valido"]
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(fuera_de_rango["wasm"])


def test_borrowing_compuestos_rechaza_escrituras_pero_copia_desreferenciacion():
    compartida = compilar_programa("""fn main() -> i32 {
    let datos = [1, 2]; let r = &datos; r[0] = 3; 0
}""")
    conflicto = compilar_programa("""fn main() -> i32 {
    let mut datos = [[1, 2], [3, 4]];
    let r = &mut datos;
    datos[0][0] = 5;
    r[0][0]
}""")
    desreferenciacion = compilar_programa("""fn main() -> i32 {
    let datos = (1, true); let r = &datos; let copia = *r; copia.0
}""")

    assert not compartida["valido"]
    assert compartida["wasm"] is None
    assert not conflicto["valido"]
    assert conflicto["wasm"] is None
    assert desreferenciacion["valido"]
    wasmtime.Module(wasmtime.Engine(), desreferenciacion["wasm"])
    assert ejecutar_modulo_wasm(desreferenciacion["wasm"]) == 1


@pytest.mark.parametrize(
    "codigo",
    [
        "enum E { A } fn main() -> i32 { let valor = E::B; return 0; }",
    ],
)
def test_enumeraciones_no_admitidas_o_invalidas_no_generan_wasm(codigo):
    resultado = compilar_programa(codigo)

    assert not resultado["valido"]
    assert resultado["wasm"] is None


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


def test_constante_global_compuesta_se_materializa_en_memoria():
    resultado = compilar_programa("""const DATOS: [i32; 2] = [1, 2];

fn main() -> i32 { return 0; }""")

    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 0


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


def test_matrices_de_tres_dimensiones_generan_wasm():
    resultado = compilar_programa("""fn main() -> i32 {
    let valores: [[[i32; 1]; 1]; 1] = [[[1]]];
    return valores[0][0][0];
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 1


def test_escrituras_compuestas_en_arreglos_tridimensionales():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut datos = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]];
    datos[1][0][1] = 9;
    datos[0][1][0] += 5;
    return datos[1][0][1] + datos[0][1][0];
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 17


def test_matriz_de_estructuras_lee_y_modifica_campos():
    resultado = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let mut datos = [[Punto { x: 1 }, Punto { x: 2 }], [Punto { x: 3 }, Punto { x: 4 }]];
    datos[1][0].x += 6;
    return datos[1][0].x;
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 9


def test_matriz_de_tuplas_lee_y_modifica_componentes():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut datos = [[(1, true), (2, false)], [(3, true), (4, false)]];
    datos[1][0].0 += 6;
    return datos[1][0].0;
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 9


def test_accesos_profundos_comparten_ruta_de_lectura_y_escritura():
    estructuras = compilar_programa("""struct Punto { x: i32 }
struct Datos { puntos: [Punto; 2] }
fn main() -> i32 {
    let mut datos = Datos { puntos: [Punto { x: 1 }, Punto { x: 2 }] };
    datos.puntos[1].x += 5;
    return datos.puntos[1].x;
}""")
    arreglo = compilar_programa("""struct Punto { valores: [i32; 2] }
fn main() -> i32 {
    let mut puntos = [Punto { valores: [1, 2] }, Punto { valores: [3, 4] }];
    puntos[1].valores[0] = 9;
    return puntos[1].valores[0];
}""")
    tupla = compilar_programa("""fn main() -> i32 {
    let mut datos = ([1, 2], [3, 4]);
    datos.1[0] += 5;
    return datos.1[0];
}""")
    decimales = compilar_programa("""struct Punto { valores: [f64; 2] }
struct Datos { puntos: [Punto; 1] }
fn main() -> f64 {
    let mut datos = Datos { puntos: [Punto { valores: [1.5, 2.0] }] };
    datos.puntos[0].valores[1] *= 3.0;
    return datos.puntos[0].valores[1];
}""")

    for resultado, esperado in (
        (estructuras, 7), (arreglo, 9), (tupla, 8), (decimales, pytest.approx(6.0)),
    ):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_accesos_profundos_rechazan_mutabilidad_y_atrapan_indices_invalidos():
    inmutable = compilar_programa("""struct Punto { valores: [i32; 2] }
fn main() -> i32 {
    let punto = Punto { valores: [1, 2] };
    punto.valores[0] = 9;
    return punto.valores[0];
}""")
    fuera_de_rango = compilar_programa("""struct Punto { valores: [i32; 2] }
fn main() -> i32 {
    let mut puntos = [Punto { valores: [1, 2] }];
    let indice = 2;
    puntos[0].valores[indice] = 9;
    return 0;
}""")

    assert not inmutable["valido"]
    assert inmutable["wasm"] is None
    assert fuera_de_rango["valido"]
    wasmtime.Module(wasmtime.Engine(), fuera_de_rango["wasm"])
    with pytest.raises(wasmtime.Trap):
        ejecutar_modulo_wasm(fuera_de_rango["wasm"])


def test_copias_profundas_de_matrices_compuestas_no_comparten_punteros():
    estructuras = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let original = [[Punto { x: 1 }, Punto { x: 2 }], [Punto { x: 3 }, Punto { x: 4 }]];
    let mut copia = original;
    copia[1][0].x = 30;
    return original[1][0].x + copia[1][0].x;
}""")
    tuplas = compilar_programa("""fn main() -> i32 {
    let original = [[(1, true), (2, false)], [(3, true), (4, false)]];
    let mut copia = original;
    copia[1][0].0 = 30;
    return original[1][0].0 + copia[1][0].0;
}""")
    anidado = compilar_programa("""fn main() -> i32 {
    let original = [[[1, 2]], [[3, 4]]];
    let mut copia = original;
    copia[1][0][0] = 30;
    return original[1][0][0] + copia[1][0][0];
}""")
    asignacion = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let original = [[Punto { x: 1 }, Punto { x: 2 }], [Punto { x: 3 }, Punto { x: 4 }]];
    let mut copia = [[Punto { x: 0 }, Punto { x: 0 }], [Punto { x: 0 }, Punto { x: 0 }]];
    copia = original;
    copia[1][0].x = 30;
    return original[1][0].x + copia[1][0].x;
}""")
    decimales = compilar_programa("""fn main() -> f64 {
    let original = [[(1, 1.5), (2, 2.5)], [(3, 3.5), (4, 4.5)]];
    let mut copia = original;
    copia[1][0].1 += 1.0;
    return original[1][0].1 + copia[1][0].1;
}""")

    for resultado, esperado in (
        (estructuras, 33), (tuplas, 33), (anidado, 33), (asignacion, 33),
        (decimales, pytest.approx(8.0)),
    ):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_compuestos_recursivos_copy_en_campos_parametros_y_retornos():
    campos = compilar_programa("""struct Punto { x: i32 }
struct Datos { matriz: [[Punto; 2]; 2] }
fn main() -> i32 {
    let original = Datos { matriz: [[Punto { x: 1 }, Punto { x: 2 }], [Punto { x: 3 }, Punto { x: 4 }]] };
    let mut copia = original;
    copia.matriz[1][0].x = 30;
    return original.matriz[1][0].x + copia.matriz[1][0].x;
}""")
    llamada = compilar_programa("""struct Punto { x: i32 }
fn cambiar(mut datos: [[Punto; 2]; 2]) -> [[Punto; 2]; 2] {
    datos[1][0].x = 30;
    return datos;
}
fn main() -> i32 {
    let original = [[Punto { x: 1 }, Punto { x: 2 }], [Punto { x: 3 }, Punto { x: 4 }]];
    let copia = cambiar(original);
    return original[1][0].x + copia[1][0].x;
}""")

    for resultado, esperado in ((campos, 33), (llamada, 33)):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_arreglo_move_con_string_se_transfiere_sin_copia_automatica():
    valido = compilar_programa("""struct Texto { valor: String }
fn identidad(datos: [Texto; 2]) -> [Texto; 2] { return datos; }
fn main() -> i32 {
    let original = [Texto { valor: "uno" }, Texto { valor: "dos" }];
    let movido = identidad(original);
    if movido[1].valor == "dos" { return 1; }
    return 0;
}""")
    invalido = compilar_programa("""struct Texto { valor: String }
fn identidad(datos: [Texto; 2]) -> [Texto; 2] { return datos; }
fn main() -> i32 {
    let original = [Texto { valor: "uno" }, Texto { valor: "dos" }];
    let movido = identidad(original);
    if original[0].valor == "uno" { return 1; }
    return 0;
}""")
    matriz = compilar_programa("""fn identidad(datos: [[String; 2]; 2]) -> [[String; 2]; 2] {
    return datos;
}
fn main() -> i32 {
    let original = [["a", "b"], ["c", "d"]];
    let movido = identidad(original);
    if movido[1][0] == "c" { return 1; }
    return 0;
}""")
    matriz_invalida = compilar_programa("""fn identidad(datos: [[String; 2]; 2]) -> [[String; 2]; 2] {
    return datos;
}
fn main() -> i32 {
    let original = [["a", "b"], ["c", "d"]];
    let movido = identidad(original);
    if original[1][0] == "c" { return 1; }
    return 0;
}""")

    assert valido["valido"]
    wasmtime.Module(wasmtime.Engine(), valido["wasm"])
    assert ejecutar_modulo_wasm(valido["wasm"]) == 1
    assert not invalido["valido"]
    assert invalido["wasm"] is None
    assert matriz["valido"]
    wasmtime.Module(wasmtime.Engine(), matriz["wasm"])
    assert ejecutar_modulo_wasm(matriz["wasm"]) == 1
    assert not matriz_invalida["valido"]
    assert matriz_invalida["wasm"] is None


def test_enums_admiten_structs_arreglos_y_enums_asociados():
    estructura = compilar_programa("""struct Punto { x: i32 }
enum Dato { Punto(Punto), Vacio }
fn identidad(dato: Dato) -> Dato { return dato; }
fn main() -> i32 {
    let dato = identidad(Dato::Punto(Punto { x: 7 }));
    return match dato { Dato::Punto(punto) => punto.x, Dato::Vacio => 0, };
}""")
    arreglo = compilar_programa("""enum Dato { Valores([i32; 2]), Vacio }
fn identidad(dato: Dato) -> Dato { return dato; }
fn main() -> i32 {
    let dato = identidad(Dato::Valores([7, 2]));
    return match dato { Dato::Valores(valores) => valores[0], Dato::Vacio => 0, };
}""")
    anidado = compilar_programa("""enum Interior { Numero(i32), Vacio }
enum Exterior { Valor(Interior), Ninguno }
fn identidad(valor: Exterior) -> Exterior { return valor; }
fn main() -> i32 {
    let valor = identidad(Exterior::Valor(Interior::Numero(7)));
    return match valor {
        Exterior::Valor(Interior::Numero(numero)) => numero,
        Exterior::Valor(_) => 0,
        Exterior::Ninguno => 0,
    };
}""")
    copia = compilar_programa("""struct Punto { x: i32 }
enum Dato { Punto(Punto), Vacio }
fn main() -> i32 {
    let mut punto = Punto { x: 1 };
    let dato = Dato::Punto(punto);
    punto.x = 2;
    return match dato { Dato::Punto(valor) => valor.x, Dato::Vacio => 0, };
}""")

    for resultado in (estructura, arreglo, anidado, copia):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) in {1, 7}


def test_contenedores_de_enums_y_enum_move_con_string():
    contenedores = compilar_programa("""enum Estado { Codigo(i32), Vacio }
struct Datos { estado: Estado }
fn main() -> i32 {
    let datos = [Datos { estado: Estado::Codigo(7) }, Datos { estado: Estado::Vacio }];
    return match datos[0].estado { Estado::Codigo(codigo) => codigo, Estado::Vacio => 0, };
}""")
    matriz = compilar_programa("""enum Estado { Codigo(i32), Vacio }
fn main() -> i32 {
    let datos = [[Estado::Codigo(7), Estado::Vacio], [Estado::Vacio, Estado::Codigo(2)]];
    return match datos[0][0] { Estado::Codigo(codigo) => codigo, Estado::Vacio => 0, };
}""")
    copia = compilar_programa("""struct Punto { x: i32 }
enum Estado { Punto(Punto), Vacio }
fn main() -> i32 {
    let mut punto = Punto { x: 1 };
    let datos = [Estado::Punto(punto), Estado::Vacio];
    let copia = datos;
    punto.x = 2;
    return match copia[0] { Estado::Punto(valor) => valor.x, Estado::Vacio => 0, };
}""")
    move = compilar_programa("""struct Mensaje { texto: String }
enum Resultado { Error(Mensaje), Vacio }
fn identidad(resultado: Resultado) -> Resultado { return resultado; }
fn main() -> i32 {
    let resultado = identidad(Resultado::Error(Mensaje { texto: "fallo" }));
    return match resultado { Resultado::Error(_) => 1, Resultado::Vacio => 0, };
}""")
    uso_despues = compilar_programa("""struct Mensaje { texto: String }
enum Resultado { Error(Mensaje), Vacio }
fn identidad(resultado: Resultado) -> Resultado { return resultado; }
fn main() -> i32 {
    let original = Resultado::Error(Mensaje { texto: "fallo" });
    let movido = identidad(original);
    return match original { Resultado::Error(_) => 1, Resultado::Vacio => 0, };
}""")
    recursivo = compilar_programa("""enum Nodo { Siguiente(Nodo), Vacio }
fn main() -> i32 { return 0; }""")

    for resultado in (contenedores, matriz, copia, move):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) in {1, 7}
    assert not uso_despues["valido"]
    assert uso_despues["wasm"] is None
    assert not recursivo["valido"]
    assert recursivo["wasm"] is None


def test_reasignacion_desde_literal_de_arreglo():
    resultado = compilar_programa("""fn main() -> i32 {
    let mut valores = [1, 2];
    valores = [3, 4];
    return valores[0];
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 3


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


def test_compuestos_anidados_string_parametros_retorno_y_movimientos():
    valido = compilar_programa("""struct Direccion { codigo: i32, texto: String }
struct Persona { direccion: Direccion, datos: (i32, f64) }
fn actualizar(persona: Persona) -> Persona {
    let mut resultado = persona;
    resultado.direccion.codigo += 2;
    resultado.datos.0 += 3;
    return resultado;
}
fn main() -> i32 {
    let persona = Persona { direccion: Direccion { codigo: 10, texto: "hola" }, datos: (1, 2.5) };
    let resultado = actualizar(persona);
    if resultado.direccion.texto == "hola" { return resultado.direccion.codigo + resultado.datos.0; }
    return 0;
}""")
    invalido = compilar_programa("""struct Texto { valor: String }
fn identidad(valor: Texto) -> Texto { return valor; }
fn main() -> i32 {
    let texto = Texto { valor: "uno" };
    let resultado = identidad(texto);
    if texto.valor == "uno" { return 0; }
    return 1;
}""")
    assert valido["valido"]
    wasmtime.Module(wasmtime.Engine(), valido["wasm"])
    assert ejecutar_modulo_wasm(valido["wasm"]) == 16
    assert not invalido["valido"]
    assert invalido["wasm"] is None


def test_copias_copy_anidadas_no_comparten_memoria():
    resultado = compilar_programa("""struct Punto { x: i32 }
struct Caja { punto: Punto, datos: (i32, bool) }
fn main() -> i32 {
    let original = Caja { punto: Punto { x: 1 }, datos: (2, true) };
    let mut copia = original;
    copia.punto.x = 9;
    copia.datos.0 += 3;
    return original.punto.x + original.datos.0 + copia.punto.x + copia.datos.0;
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 17


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ('fn main() -> i32 { let datos = (1, "texto"); return datos.0; }', 1),
        ('fn main() -> i32 { let datos = (1, (2, true)); return datos.0; }', 1),
        ('struct P { x: String } fn main() -> i32 { let p = P { x: "a" }; if p.x == "a" { return 1; } return 0; }', 1),
        ('struct P { x: i32 } struct Q { p: P } fn main() -> i32 { let q = Q { p: P { x: 1 } }; return q.p.x; }', 1),
    ],
)
def test_compuestos_antes_rechazados_generan_wasm(codigo, esperado):
    resultado = compilar_programa(codigo)
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_constructor_compuesto_copia_campos_copy_anidados():
    resultado = compilar_programa("""struct Punto { x: i32 }
struct Caja { punto: Punto }
fn main() -> i32 {
    let punto = Punto { x: 2 };
    let mut caja = Caja { punto: punto };
    caja.punto.x = 8;
    return punto.x + caja.punto.x;
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 10


def test_arreglos_y_matrices_copy_como_parametros_y_retorno():
    arreglo = compilar_programa("""fn actualizar(datos: [i32; 2]) -> [i32; 2] {
    let mut resultado = datos;
    resultado[0] += 4;
    return resultado;
}
fn main() -> i32 {
    let original = [3, 7];
    let resultado = actualizar(original);
    return original[0] + resultado[0];
}""")
    matriz = compilar_programa("""fn identidad(datos: [[i32; 2]; 2]) -> [[i32; 2]; 2] {
    return datos;
}
fn main() -> i32 {
    let datos = [[1, 2], [3, 4]];
    let resultado = identidad(datos);
    return resultado[1][0];
}""")
    for resultado, esperado in ((arreglo, 10), (matriz, 3)):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_layout_recursivo_struct_con_arreglo_i32():
    resultado = compilar_programa("""struct Datos { valores: [i32; 2] }
fn main() -> i32 {
    let mut datos = Datos { valores: [10, 20] };
    datos.valores[1] += 5;
    return datos.valores[0] + datos.valores[1];
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 35


def test_arreglos_de_estructuras_y_tuplas_copy():
    estructuras = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let mut puntos = [Punto { x: 1 }, Punto { x: 2 }];
    puntos[1].x += 5;
    return puntos[0].x + puntos[1].x;
}""")
    tuplas = compilar_programa("""fn main() -> i32 {
    let mut datos = [(1, true), (2, false)];
    datos[1].0 = 7;
    return datos[0].0 + datos[1].0;
}""")
    for resultado, esperado in ((estructuras, 8), (tuplas, 8)):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_copias_y_funciones_de_arreglos_compuestos_copy():
    resultado = compilar_programa("""struct Punto { x: i32 }
fn cambiar(datos: [Punto; 2]) -> [Punto; 2] {
    let mut copia = datos;
    copia[0].x = 9;
    return copia;
}
fn main() -> i32 {
    let original = [Punto { x: 1 }, Punto { x: 2 }];
    let resultado = cambiar(original);
    return original[0].x + resultado[0].x;
}""")
    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 10


def test_transferencia_move_de_arreglo_de_estructuras_con_string():
    valido = compilar_programa("""struct Texto { valor: String }
fn identidad(datos: [Texto; 1]) -> [Texto; 1] { return datos; }
fn main() -> i32 {
    let origen = [Texto { valor: "hola" }];
    let destino = identidad(origen);
    if destino[0].valor == "hola" { return 1; }
    return 0;
}""")
    invalido = compilar_programa("""struct Texto { valor: String }
fn main() -> i32 {
    let origen = [Texto { valor: "hola" }];
    let destino = origen;
    if origen[0].valor == "hola" { return 0; }
    return 1;
}""")
    assert valido["valido"]
    wasmtime.Module(wasmtime.Engine(), valido["wasm"])
    assert ejecutar_modulo_wasm(valido["wasm"]) == 1
    assert not invalido["valido"]
    assert invalido["wasm"] is None


def test_transferencia_move_de_arreglo_de_tuplas_con_string():
    valido = compilar_programa("""fn identidad(datos: [(String, i32); 1]) -> [(String, i32); 1] {
    return datos;
}
fn main() -> i32 {
    let origen = [("hola", 2)];
    let destino = identidad(origen);
    if destino[0].0 == "hola" { return destino[0].1; }
    return 0;
}""")
    invalido = compilar_programa("""fn main() -> i32 {
    let origen = [("hola", 2)];
    let destino = origen;
    if origen[0].0 == "hola" { return 0; }
    return destino[0].1;
}""")
    assert valido["valido"]
    wasmtime.Module(wasmtime.Engine(), valido["wasm"])
    assert ejecutar_modulo_wasm(valido["wasm"]) == 2
    assert not invalido["valido"]
    assert invalido["wasm"] is None


def test_prestamos_de_enums_y_compuestos_recursivos():
    enum_compartido = compilar_programa("""enum Estado { Valor(i32), Vacio }
fn leer(referencia: &Estado) -> i32 {
    match *referencia { Estado::Valor(numero) => numero, Estado::Vacio => 0 }
}
fn main() -> i32 { let estado = Estado::Valor(7); leer(&estado) }""")
    enum_mutable = compilar_programa("""enum Estado { Valor(i32), Vacio }
fn vaciar(referencia: &mut Estado) { *referencia = Estado::Vacio; }
fn main() -> i32 {
    let mut estado = Estado::Valor(7); vaciar(&mut estado);
    match estado { Estado::Valor(numero) => numero, Estado::Vacio => 9 }
}""")
    struct_arreglo = compilar_programa("""struct Datos { valores: [i32; 2] }
fn cambiar(referencia: &mut Datos) { referencia.valores[1] += 5; }
fn main() -> i32 {
    let mut datos = Datos { valores: [3, 4] }; cambiar(&mut datos); datos.valores[1]
}""")
    arreglo_struct = compilar_programa("""struct Punto { x: i32 }
fn cambiar(referencia: &mut [Punto; 2]) { referencia[1].x = 9; }
fn main() -> i32 {
    let mut puntos = [Punto { x: 3 }, Punto { x: 4 }]; cambiar(&mut puntos); puntos[1].x
}""")
    tupla_arreglo = compilar_programa("""fn cambiar(referencia: &mut ([i32; 2], bool)) {
    referencia.0[1] += 5;
}
fn main() -> i32 {
    let mut datos = ([3, 4], true); cambiar(&mut datos); datos.0[1]
}""")
    string_compartido = compilar_programa("""fn igual(referencia: &String) -> i32 {
    if *referencia == "hola" { return 1; } return 0;
}
fn main() -> i32 { let texto = "hola"; igual(&texto) }""")
    arreglo_string = compilar_programa("""fn main() -> i32 {
    let textos = ["uno", "dos"]; let referencia = &textos;
    if referencia[1] == "dos" { return 1; } return 0;
}""")
    string_mutable = compilar_programa("""fn main() -> i32 {
    let mut texto = "uno"; { let referencia = &mut texto; *referencia = "dos"; }
    if texto == "dos" { return 1; } return 0;
}""")
    conflicto = compilar_programa("""enum Estado { Valor(i32), Vacio }
fn main() -> i32 {
    let mut estado = Estado::Valor(1); let compartida = &estado;
    let exclusiva = &mut estado; match *compartida { Estado::Valor(x) => x, Estado::Vacio => 0 }
}""")

    for resultado, esperado in (
        (enum_compartido, 7), (enum_mutable, 9), (struct_arreglo, 9),
        (arreglo_struct, 9), (tupla_arreglo, 9), (string_compartido, 1),
        (arreglo_string, 1), (string_mutable, 1),
    ):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado
    assert not conflicto["valido"]
    assert conflicto["wasm"] is None


def test_desreferenciacion_copy_de_compuestos_copia_el_bloque():
    estructura = compilar_programa("""struct Punto { x: i32 }
fn main() -> i32 {
    let original = Punto { x: 1 }; let referencia = &original;
    let mut copia = *referencia; copia.x = 9; original.x + copia.x
}""")
    tupla = compilar_programa("""fn main() -> i32 {
    let original = (1, true); let referencia = &original;
    let mut copia = *referencia; copia.0 = 9; original.0 + copia.0
}""")
    arreglo = compilar_programa("""fn main() -> i32 {
    let original = [1, 2]; let referencia = &original;
    let mut copia = *referencia; copia[0] = 9; original[0] + copia[0]
}""")
    movimiento = compilar_programa("""fn main() -> i32 {
    let original = ("texto", 1); let referencia = &original; let copia = *referencia; 0
}""")
    for resultado in (estructura, tupla, arreglo):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == 10
    assert not movimiento["valido"]
    assert movimiento["wasm"] is None


def test_constantes_globales_compuestas_y_igualdad_estructural_enum():
    constantes = compilar_programa("""struct Punto { x: i32 }
enum Estado { Valor(i32), Vacio }
const ARREGLO: [i32; 2] = [3, 4];
const TUPLA: (i32, bool) = (5, true);
const PUNTO: Punto = Punto { x: 6 };
const ESTADO: Estado = Estado::Valor(7);
fn main() -> i32 {
    match ESTADO { Estado::Valor(valor) => ARREGLO[0] + TUPLA.0 + PUNTO.x + valor, Estado::Vacio => 0 }
}""")
    igualdad = compilar_programa("""struct Punto { x: i32, y: f64 }
enum Estado { Punto(Punto), Texto(String), Vacio }
fn main() -> i32 {
    let uno = Estado::Punto(Punto { x: 2, y: 1.5 });
    let dos = Estado::Punto(Punto { x: 2, y: 1.5 });
    let texto = Estado::Texto("ñ");
    if uno == dos && texto == Estado::Texto("ñ") && uno != Estado::Vacio { return 1; }
    return 0;
}""")
    constante_move = compilar_programa("""struct Texto { valor: String }
enum Estado { Error(String), Vacio }
const TEXTO: Texto = Texto { valor: "hola" };
const ESTADO: Estado = Estado::Error("fallo");
fn main() -> i32 {
    if TEXTO.valor == "hola" {
        return match ESTADO { Estado::Error("fallo") => 1, Estado::Error(_) => 0, Estado::Vacio => 0 };
    }
    return 0;
}""")
    for resultado, esperado in ((constantes, 21), (igualdad, 1), (constante_move, 1)):
        assert resultado["valido"]
        wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
        assert ejecutar_modulo_wasm(resultado["wasm"]) == esperado


def test_ejemplo_oficial_con_main_unit_generan_y_ejecutan_wasm():
    resultado = compilar_programa("""struct Punto {
    x: f64,
    y: f64,
}

enum Estado {
    Pendiente,
    Completado(i32),
    Error(String),
}

fn mover_x(p: &mut Punto, dx: f64) {
    p.x = p.x + dx;
}

fn describir(estado: Estado) -> i32 {
    match estado {
        Estado::Pendiente => 0,
        Estado::Completado(codigo) => codigo,
        Estado::Error(_) => -1,
    }
}

fn main() {
    let mut p = Punto { x: 1.0, y: 2.0 };
    mover_x(&mut p, 3.0);

    let estado = Estado::Completado(200);
    let codigo = describir(estado);

    let dimensiones: (f64, f64) = (p.x, p.y);
    let muestras: [i32; 3] = [10, 20, 30];
    let correcto: bool = codigo == 200;
    let inicial: char = 'R';

    if correcto {
        p.y = p.y + 1.0;
    }
}""")

    assert resultado["valido"]
    wasmtime.Module(wasmtime.Engine(), resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) is None
