"""Pruebas de arreglos vacíos con contexto y escritura de elementos.

Estos casos validan el frontend y sus datos para el backend. No verifican
la ejecución de Wasm ni sustituyen las guardas de índices dinámicos.
"""
from main import analizar_programa
from generated.RustiQParser import RustiQParser


VALIDAS = [
    ("Arreglo vacío local anotado", "fn main() { let a: [i32; 0] = []; }"),
    ("Arreglo vacío con paréntesis", "fn main() { let a: [bool; 0] = (([])); }"),
    ("Arreglos vacíos anidados", "fn main() { let a: [[i32; 0]; 2] = [[], []]; }"),
    ("Arreglo vacío de arreglos", "fn main() { let a: [[i32; 2]; 0] = []; }"),
    ("Retorno de arreglo vacío", "fn vacio() -> [i32; 0] { return []; }"),
    ("Argumento de arreglo vacío", "fn aceptar(a: [i32; 0]) {} fn main() { aceptar([]); }"),
    ("Inicialización diferida con arreglo vacío", "fn main() { let a: [i32; 0]; a = []; }"),
    ("Reasignación de arreglo vacío", "fn main() { let mut a: [i32; 0] = []; a = []; }"),
    ("Constante vacía", "const A: [char; 0] = [];"),
    ("Constante anidada vacía", "const A: [[i32; 0]; 2] = [[], []];"),
    ("Tamaños con ceros iniciales", "const A: [i32; 00] = []; fn main() { let a: [i32; 00] = A; }"),
    ("Asignación a elemento", "fn main() -> i32 { let mut a = [1, 2]; a[0] = 3; return a[0]; }"),
    ("Asignación con índice variable", "fn main() { let mut a = [1, 2]; let i = 1; a[i] = 4; }"),
    ("Asignación con índice calculado", "fn main() { let mut a = [1, 2]; a[0 + 1] = 4; }"),
    ("Asignación anidada", "fn main() { let mut a = [[1, 2], [3, 4]]; a[1][0] = 7; }"),
    ("Reemplazo de subarreglo", "fn main() { let mut a = [[1, 2], [3, 4]]; a[0] = [5, 6]; }"),
    ("Reemplazo de subarreglo vacío", "fn main() { let mut a: [[i32; 0]; 1] = [[]]; a[0] = []; }"),
    ("Elemento String", 'fn main() { let mut a = ["uno", "dos"]; a[0] = "tres"; }'),
    ("Elemento char", "fn main() { let mut a = ['a', 'b']; a[0] = 'ñ'; }"),
    ("Elemento bool", "fn main() { let mut a = [true, false]; a[0] = false; }"),
    ("Parámetro mutable", "fn cambiar(mut a: [i32; 2]) -> i32 { a[0] += 1; return a[0]; }"),
    ("Escritura en while", "fn main() { let mut a = [0, 0]; let mut i = 0; while i < 2 { a[i] = i; i += 1; } }"),
    ("Arreglo mutable local oculta constante", "const A: [i32; 1] = [1]; fn main() { let mut A = [2]; A[0] = 3; }"),
    ("Arreglo local en loop", "fn main() { loop { let mut a = [0]; a[0] += 1; break; } }"),
]

# Probar las cuatro operaciones compuestas en ambos tipos numéricos.
for operador in ("+=", "-=", "*=", "/="):
    for inicial, operando in (("12", "2"), ("12.0", "2.0")):
        VALIDAS.append((
            f"Elemento {inicial} con {operador}",
            f"fn main() {{ let mut a = [{inicial}]; a[0] {operador} {operando}; }}",
        ))

INVALIDAS = [
    ("Vacío sin contexto", "fn main() { let a = []; }", "arreglo vacío"),
    ("Vacío no satisface tamaño uno", "fn main() { let a: [i32; 1] = []; }", "Tipos incompatibles"),
    ("Vacío no satisface elemento interior", "fn main() { let a: [[i32; 1]; 1] = [[]]; }", "Tipos incompatibles"),
    ("Constante vacía de tamaño incorrecto", "const A: [i32; 1] = [];", "Tipos incompatibles"),
    ("Retorno vacío de tamaño incorrecto", "fn f() -> [i32; 1] { return []; }", "Retorno incompatible"),
    ("Argumento vacío de tamaño incorrecto", "fn f(a: [i32; 1]) {} fn main() { f([]); }", "Argumento 1"),
    ("Escritura sin mut", "fn main() { let a = [1]; a[0] = 2; }", "porque no fue declarada con 'mut'"),
    ("Compuesta sin mut", "fn main() { let a = [1]; a[0] += 2; }", "porque no fue declarada con 'mut'"),
    ("Escritura de constante", "const A: [i32; 1] = [1]; fn main() { A[0] = 2; }", "No se puede modificar"),
    ("Escritura sin inicializar arreglo", "fn main() { let mut a: [i32; 1]; a[0] = 1; }", "antes de inicializarla"),
    ("Escritura de variable inexistente", "fn main() { a[0] = 1; }", "no está declarada"),
    ("Indexar destino escalar", "fn main() { let mut a = 1; a[0] = 2; }", "No se puede indexar"),
    ("Índice negativo", "fn main() { let mut a = [1]; a[-1] = 2; }", "fuera de rango"),
    ("Índice igual al tamaño", "fn main() { let mut a = [1]; a[1] = 2; }", "fuera de rango"),
    ("Índice interior inválido", "fn main() { let mut a = [[1]]; a[0][1] = 2; }", "fuera de rango"),
    ("Índice bool", "fn main() { let mut a = [1]; a[true] = 2; }", "debe ser i32"),
    ("Índice f64", "fn main() { let mut a = [1]; a[0.0] = 2; }", "debe ser i32"),
    ("Índice inexistente", "fn main() { let mut a = [1]; a[i] = 2; }", "no está declarada"),
    ("Índice sin inicializar", "fn main() { let mut a = [1]; let i: i32; a[i] = 2; }", "antes de inicializarla"),
    ("Elemento de tipo incorrecto", "fn main() { let mut a = [1]; a[0] = true; }", "Tipos incompatibles"),
    ("Subarreglo de tamaño incorrecto", "fn main() { let mut a = [[1, 2]]; a[0] = [3]; }", "Tipos incompatibles"),
    ("Compuesta entre tipos distintos", "fn main() { let mut a = [1]; a[0] += 2.5; }", "sin una conversión explícita"),
    ("Compuesta de booleanos", "fn main() { let mut a = [true]; a[0] += false; }", "requiere números"),
    ("Compuesta de subarreglos", "fn main() { let mut a = [[1]]; a[0] += [2]; }", "requiere números"),
    ("Acceso a arreglo vacío con índice variable", "fn main() { let a: [i32; 0] = []; let i = 0; let x = a[i]; }", "fuera de rango"),
    ("Escritura a arreglo vacío", "fn main() { let mut a: [i32; 0] = []; a[0] = 1; }", "fuera de rango"),
    ("Variable índice fuera de ámbito", "fn main() { let mut a = [1]; { let i = 0; } a[i] = 2; }", "no está declarada"),
]


def recorrer(nodo):
    yield nodo
    for hijo in nodo.getChildren():
        if hasattr(hijo, "getChildren"):
            yield from recorrer(hijo)


def comprobar_backend():
    """Los destinos, sus índices y el RHS deben conservar sus referencias."""
    r = analizar_programa(
        "fn main() { let mut a = [[1, 2]]; let i = 0; let j = 1; let x = 3; a[i][j] += x; }"
    )
    assert r["valido"], r["errores"]
    destino = next(n for n in recorrer(r["arbol"]) if isinstance(n, RustiQParser.AssignmentContext))
    simbolo = r["simbolos"][r["referencias"][destino]]
    assert simbolo["nombre"] == "a" and simbolo["tipo"] == "[[i32;2];1]"
    assert destino.assignmentOp().getText() == "+="
    assert r["tipos_expresiones"][destino] == "i32"
    assert [r["tipos_expresiones"][n] for n in destino.indexAccess()] == ["[i32;2]", "i32"]
    lecturas = [n for n in recorrer(destino) if isinstance(n, RustiQParser.PrimaryContext) and n.IDENT()]
    assert {r["simbolos"][r["referencias"][n]]["nombre"] for n in lecturas} == {"i", "j", "x"}


def comprobar_constantes_vacias():
    r = analizar_programa("const A: [i32; 0] = []; const M: [[bool; 0]; 2] = [[], []];")
    assert r["valido"], r["errores"]
    valores = {s["nombre"]: (s["tipo"], s["valor"]) for s in r["simbolos"].values()}
    assert valores == {"A": ("[i32;0]", []), "M": ("[[bool;0];2]", [[], []])}


def ejecutar_pruebas():
    correctas = 0
    for nombre, codigo in VALIDAS:
        r = analizar_programa(codigo)
        cumple = r["valido"] and r["arbol"] is not None and not r["errores"]
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple:
            correctas += 1
        else:
            print(r["errores"])
    for nombre, codigo, mensaje in INVALIDAS:
        r = analizar_programa(codigo)
        cumple = (
            not r["valido"] and r["arbol"] is None
            and any(e["fase"] == "semantico" and mensaje in e["mensaje"] for e in r["errores"])
            and all(r[c] == {} for c in ("simbolos", "referencias", "declaraciones", "funciones", "tipos_expresiones"))
        )
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple:
            correctas += 1
        else:
            print(r["errores"])
    for prueba in (comprobar_backend, comprobar_constantes_vacias):
        prueba()
        correctas += 1
        print(f"{prueba.__name__}: OK")
    total = len(VALIDAS) + len(INVALIDAS) + 2
    print(f"\nResultado: {correctas}/{total} pruebas OK")
    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()
