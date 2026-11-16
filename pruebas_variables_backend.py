"""Pruebas de identidad de variables y referencias al mismo árbol.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from generated.RustiQParser import RustiQParser
from main import analizar_programa


def recorrer(nodo):
    """Recorre los nodos del árbol de ANTLR."""
    yield nodo

    for hijo in nodo.getChildren():
        if hasattr(hijo, "getChildren"):
            yield from recorrer(hijo)


def comprobar(condicion, mensaje):
    if not condicion:
        raise AssertionError(mensaje)


def analizar_valido(codigo):
    resultado = analizar_programa(codigo)
    comprobar(
        resultado["valido"],
        f"El programa debía ser válido: {resultado['errores']}",
    )
    return resultado


def declaraciones_de(resultado, nombre):
    """Busca declaraciones por nombre en orden de aparición."""
    return [
        nodo
        for nodo in recorrer(resultado["arbol"])
        if nodo in resultado["declaraciones"]
        and nodo.IDENT().getText() == nombre
    ]


def lecturas_de(resultado, nombre):
    """Busca usos de una variable como expresión."""
    return [
        nodo
        for nodo in recorrer(resultado["arbol"])
        if isinstance(nodo, RustiQParser.PrimaryContext)
        and nodo.IDENT() is not None
        and nodo.IDENT().getText() == nombre
    ]


def prueba_parametro():
    resultado = analizar_valido("""
fn identidad(numero: i32) -> i32 {
    return numero;
}
""")

    declaracion = declaraciones_de(resultado, "numero")[0]
    lectura = lecturas_de(resultado, "numero")[0]
    identificador = resultado["declaraciones"][declaracion]
    simbolo = resultado["simbolos"][identificador]

    comprobar(
        resultado["referencias"][lectura] == identificador,
        "La lectura no apunta al parámetro.",
    )
    comprobar(
        simbolo["es_parametro"]
        and simbolo["tipo"] == "i32"
        and simbolo["funcion"] == "identidad",
        "Los datos del parámetro son incorrectos.",
    )


def prueba_variables_anidadas():
    resultado = analizar_valido("""
fn main() -> i32 {
    let numero = 10;
    {
        let numero = 20;
        let copia = numero;
    }
    return numero;
}
""")

    declaraciones = declaraciones_de(resultado, "numero")
    lecturas = lecturas_de(resultado, "numero")

    exterior = resultado["declaraciones"][declaraciones[0]]
    interior = resultado["declaraciones"][declaraciones[1]]

    comprobar(exterior != interior, "Los identificadores se repiten.")
    comprobar(
        resultado["referencias"][lecturas[0]] == interior,
        "La lectura interior debe apuntar a la variable interior.",
    )
    comprobar(
        resultado["referencias"][lecturas[1]] == exterior,
        "Al salir del bloque debe recuperarse la variable exterior.",
    )


def prueba_asignacion():
    resultado = analizar_valido("""
fn main() -> i32 {
    let mut numero = 1;
    numero = numero + 1;
    return numero;
}
""")

    declaracion = declaraciones_de(resultado, "numero")[0]
    identificador = resultado["declaraciones"][declaracion]

    asignacion = next(
        nodo
        for nodo in recorrer(resultado["arbol"])
        if isinstance(nodo, RustiQParser.AssignmentContext)
    )

    comprobar(
        resultado["referencias"][asignacion] == identificador,
        "El destino de la asignación es incorrecto.",
    )
    comprobar(
        all(
            resultado["referencias"][lectura] == identificador
            for lectura in lecturas_de(resultado, "numero")
        ),
        "Las lecturas no apuntan a la misma variable.",
    )
    comprobar(
        resultado["simbolos"][identificador]["mutable"],
        "La variable debe estar marcada como mutable.",
    )


def prueba_tipos_inferidos():
    resultado = analizar_valido("""
fn main() {
    let decimal = 2.5;
    let activo = true;
}
""")

    tipos = {
        simbolo["nombre"]: simbolo["tipo"]
        for simbolo in resultado["simbolos"].values()
    }

    comprobar(
        tipos == {"decimal": "f64", "activo": "bool"},
        f"Tipos inferidos incorrectos: {tipos}",
    )


def prueba_funciones_separadas():
    resultado = analizar_valido("""
fn primera() -> i32 {
    let numero = 1;
    return numero;
}

fn segunda() -> i32 {
    let numero = 2;
    return numero;
}
""")

    declaraciones = declaraciones_de(resultado, "numero")
    lecturas = lecturas_de(resultado, "numero")

    identificadores = [
        resultado["declaraciones"][nodo]
        for nodo in declaraciones
    ]

    comprobar(
        len(set(identificadores)) == 2,
        "Las variables de funciones distintas deben tener IDs distintos.",
    )

    for lectura, identificador in zip(lecturas, identificadores):
        comprobar(
            resultado["referencias"][lectura] == identificador,
            "Una lectura apunta a otra función.",
        )

    comprobar(
        [
            resultado["simbolos"][identificador]["funcion"]
            for identificador in identificadores
        ] == ["primera", "segunda"],
        "La función asociada a cada variable es incorrecta.",
    )


def prueba_argumento_de_llamada():
    resultado = analizar_valido("""
fn identidad(numero: i32) -> i32 {
    return numero;
}

fn main() -> i32 {
    let valor = 10;
    return identidad(valor);
}
""")

    declaracion = declaraciones_de(resultado, "valor")[0]
    lectura = lecturas_de(resultado, "valor")[0]

    comprobar(
        resultado["referencias"][lectura]
        == resultado["declaraciones"][declaracion],
        "La variable del argumento no está vinculada correctamente.",
    )


def prueba_inicializador_con_variable_exterior():
    resultado = analizar_valido("""
fn main() -> i32 {
    let numero = 10;
    {
        let numero = numero + 1;
    }
    return numero;
}
""")

    declaraciones = declaraciones_de(resultado, "numero")
    lecturas = lecturas_de(resultado, "numero")
    exterior = resultado["declaraciones"][declaraciones[0]]

    # La variable interior todavía no está declarada
    # mientras se analiza su inicializador.
    comprobar(
        resultado["referencias"][lecturas[0]] == exterior,
        "El inicializador debe leer la variable exterior.",
    )


def prueba_programa_invalido():
    resultado = analizar_programa("""
fn main() -> i32 {
    return desconocida;
}
""")

    comprobar(not resultado["valido"], "Debía detectarse un error.")
    comprobar(
        all(
            resultado[campo] == {}
            for campo in (
                "simbolos",
                "declaraciones",
                "referencias",
            )
        ),
        "Un programa inválido no debe entregar mapas de variables.",
    )


PRUEBAS = [
    ("Parámetro vinculado a su lectura", prueba_parametro),
    ("Variables con igual nombre en bloques", prueba_variables_anidadas),
    ("Asignación y lecturas de variable mutable", prueba_asignacion),
    ("Tipos inferidos en los símbolos", prueba_tipos_inferidos),
    ("Variables de funciones distintas", prueba_funciones_separadas),
    ("Variable dentro de un argumento", prueba_argumento_de_llamada),
    (
        "Inicializador que lee la variable exterior",
        prueba_inicializador_con_variable_exterior,
    ),
    ("Programa inválido sin mapas de variables", prueba_programa_invalido),
]


def ejecutar_pruebas():
    correctas = 0

    for nombre, prueba in PRUEBAS:
        print(f"\n--- {nombre} ---")

        try:
            prueba()
        except AssertionError as error:
            print(f"PRUEBA FALLIDA: {error}")
        else:
            correctas += 1
            print("Prueba OK")

    print(f"\nResultado: {correctas}/{len(PRUEBAS)} pruebas OK")

    if correctas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()