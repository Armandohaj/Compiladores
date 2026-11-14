"""Regresión de arreglos e índices; no ejecuta el backend Wasm.

Ejecutar con: python pruebas_arreglos.py
Los arreglos vacíos siguen siendo un caso rechazado de forma controlada.
"""

from main import analizar_programa
from generated.RustiQParser import RustiQParser


# En los casos válidos comprobamos los valores de las constantes,
# no solamente que el analizador acepte el programa.
VALIDAS = [
    ("Constante escalar tras el cambio a postfix",
     "const LIMITE: i32 = 10; fn main() -> i32 { return LIMITE; }",
     {"LIMITE": 10}),
    ("Arreglo constante de enteros",
     "const NUMEROS: [i32; 2] = [10, 20];", {"NUMEROS": [10, 20]}),
    ("Elementos calculados y coma final",
     "const A: [i32; 2] = [2 + 3, 4 * 2,];", {"A": [5, 8]}),
    ("Arreglo constante de decimales",
     "const A: [f64; 2] = [1.5, 2.5];", {"A": [1.5, 2.5]}),
    ("Arreglo constante de booleanos",
     "const A: [bool; 2] = [true, !true];", {"A": [True, False]}),
    ("Arreglo constante de caracteres",
     "const A: [char; 2] = ['ñ', '中'];", {"A": ["ñ", "中"]}),
    ("Arreglo constante de cadenas y escapes",
     r'const A: [String; 2] = ["Hola", "mundo\n"];',
     {"A": ["Hola", "mundo\n"]}),
    ("Arreglo constante anidado",
     "const M: [[i32; 2]; 2] = [[1, 2], [3, 4]];",
     {"M": [[1, 2], [3, 4]]}),
    ("Referencia adelantada e índice calculado",
     "const X: i32 = A[0 + 1]; const A: [i32; 2] = [10, 20];",
     {"X": 20, "A": [10, 20]}),
    ("Índices anidados y signo negativo",
     "const M: [[i32; 2]; 2] = [[1, 2], [3, 4]]; const X: i32 = -M[1][0];",
     {"M": [[1, 2], [3, 4]], "X": -3}),
    ("Indexar un literal entre paréntesis",
     "const X: i32 = ([10, 20])[1];", {"X": 20}),
    ("Arreglo constante referido por otra constante",
     "const B: [i32; 2] = A; const A: [i32; 2] = [10, 20];",
     {"B": [10, 20], "A": [10, 20]}),
    ("Arreglo local con tipo explícito",
     "fn main() -> i32 { let a: [i32; 2] = [10, 20]; return a[0]; }", {}),
    ("Arreglo local inferido e índice variable",
     "fn main() -> i32 { let a = [10, 20]; let i = 1; return a[i]; }", {}),
    ("Parámetro y retorno de arreglo",
     "fn identidad(a: [i32; 2]) -> [i32; 2] { return a; } "
     "fn main() -> i32 { return identidad([10, 20])[1]; }", {}),
    ("Reasignación completa de arreglo mutable",
     "fn main() -> i32 { let mut a = [1, 2]; a = [3, 4]; return a[1]; }", {}),
    ("Arreglo local anidado",
     "fn main() -> i32 { let m = [[1, 2], [3, 4]]; return m[1][0]; }", {}),
    ("Negación lógica de elemento",
     "const A: [bool; 2] = [true, false]; const X: bool = !A[0];",
     {"A": [True, False], "X": False}),
    ("Cortocircuito evita evaluar un acceso calculado inválido",
     "const A: [i32; 2] = [10, 20]; const X: bool = false && A[1 + 1] == 0;",
     {"A": [10, 20], "X": False}),
]


# Todos estos errores deben ser semánticos y no excepciones de Python.
INVALIDAS = [
    ("Elementos de tipos distintos",
     "fn main() { let a = [1, true]; }", "El elemento 2"),
    ("Tamaño declarado incorrecto",
     "const A: [i32; 3] = [10, 20];", "Tipos incompatibles"),
    ("Tipo declarado incorrecto",
     "const A: [bool; 2] = [10, 20];", "Tipos incompatibles"),
    ("Tamaños anidados distintos",
     "fn main() { let m = [[1, 2], [3]]; }", "El elemento 2"),
    ("Índice literal negativo",
     "fn main() -> i32 { let a = [1, 2]; return a[-1]; }", "fuera de rango"),
    ("Índice literal igual al tamaño",
     "fn main() -> i32 { let a = [1, 2]; return a[2]; }", "fuera de rango"),
    ("Índice calculado fuera de rango en constante",
     "const A: [i32; 2] = [1, 2]; const X: i32 = A[1 + 1];", "fuera de rango"),
    ("Índice calculado negativo en constante",
     "const A: [i32; 2] = [1, 2]; const X: i32 = A[0 - 1];", "fuera de rango"),
    ("Índice constante fuera de rango",
     "const I: i32 = 2; const A: [i32; 2] = [1, 2]; const X: i32 = A[I];",
     "fuera de rango"),
    ("Índice interior calculado fuera de rango",
     "const M: [[i32; 2]; 1] = [[1, 2]]; const X: i32 = M[0][1 + 1];",
     "fuera de rango"),
    ("Índice booleano",
     "fn main() -> i32 { let a = [1, 2]; return a[true]; }", "debe ser i32"),
    ("Índice decimal",
     "fn main() -> i32 { let a = [1, 2]; return a[1.0]; }", "debe ser i32"),
    ("Indexar un entero",
     "fn main() -> i32 { return 10[0]; }", "No se puede indexar"),
    ("Llamada dentro de un arreglo constante",
     "const A: [i32; 1] = [obtener()]; fn obtener() -> i32 { return 1; }",
     "no puede inicializarse con una llamada"),
    ("Ciclo de dependencias con arreglo",
     "const A: [i32; 1] = [X]; const X: i32 = A[0];", "Dependencia circular"),
    ("Arreglo vacío aún no admitido",
     "fn main() { let a: [i32; 0] = []; }", "arreglo vacío"),
    ("Desbordamiento en un elemento constante",
     "const A: [i32; 1] = [2147483647 + 1];", "fuera del rango de i32"),
    ("Arreglo sin inicializar",
     "fn main() -> i32 { let a: [i32; 2]; return a[0]; }",
     "antes de inicializarla"),
    ("Argumento con tamaño incorrecto",
     "fn primero(a: [i32; 2]) -> i32 { return a[0]; } "
     "fn main() -> i32 { return primero([1]); }", "Argumento 1"),
]


def recorrer(nodo):
    yield nodo
    for hijo in nodo.getChildren():
        if hasattr(hijo, "getChildren"):
            yield from recorrer(hijo)


def comprobar_referencias():
    """Verificar identidad de símbolos y tipos del mismo árbol del backend."""
    resultado = analizar_programa(
        "const A: [i32; 2] = [10, 20]; "
        "fn main() -> i32 { let i = 1; return A[i]; }"
    )
    assert resultado["valido"], resultado["errores"]
    simbolos = resultado["simbolos"]
    tipos = resultado["tipos_expresiones"]
    vistos = set()
    for nodo in recorrer(resultado["arbol"]):
        if isinstance(nodo, RustiQParser.PrimaryContext) and nodo.IDENT():
            nombre = nodo.IDENT().getText()
            identificador = resultado["referencias"][nodo]
            assert simbolos[identificador]["nombre"] == nombre
            assert tipos[nodo] == simbolos[identificador]["tipo"]
            vistos.add(nombre)
        if isinstance(nodo, RustiQParser.PostfixContext) and nodo.expression():
            assert tipos[nodo] == "i32"
    assert vistos == {"A", "i"}


def ejecutar_pruebas():
    correctas = 0
    for nombre, codigo, esperados in VALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        constantes = {
            simbolo["nombre"]: simbolo["valor"]
            for simbolo in resultado["simbolos"].values()
            if simbolo.get("es_constante", False)
        }
        cumple = (
            resultado["valido"] and resultado["arbol"] is not None
            and not resultado["errores"] and constantes == esperados
        )
        if cumple:
            correctas += 1
        print("Prueba OK" if cumple else f"PRUEBA FALLIDA: {resultado['errores']}, {constantes}")

    for nombre, codigo, fragmento in INVALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        cumple = (
            not resultado["valido"] and resultado["arbol"] is None
            and any(
                e["fase"] == "semantico" and fragmento in e["mensaje"]
                for e in resultado["errores"]
            )
            and all(resultado[campo] == {} for campo in (
                "funciones", "tipos_expresiones", "simbolos", "declaraciones", "referencias"
            ))
        )
        if cumple:
            correctas += 1
        print("Prueba OK" if cumple else f"PRUEBA FALLIDA: {resultado['errores']}")

    print("\n--- Referencias y tipos entregados al backend ---")
    comprobar_referencias()
    correctas += 1
    print("Prueba OK")
    total = len(VALIDAS) + len(INVALIDAS) + 1
    print(f"\nResultado: {correctas}/{total} pruebas OK")
    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()
