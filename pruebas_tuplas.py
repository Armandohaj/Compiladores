"""Pruebas de tipos, valores constantes y destinos de tuplas.

La gramática del proyecto exige dos o más campos. (x) sigue siendo
agrupación; no se agrega desempaquetado ni una tupla de un solo campo.
"""
from main import analizar_programa
from generated.RustiQParser import RustiQParser


# Código válido y valores constantes esperados. Las tuplas se representan
# con tuple de Python, los arreglos con list; no son intercambiables.
VALIDAS = [
    ("Tupla local inferida", 'fn main() -> i32 { let t = (10, true, "Hola"); return t.0; }', {}),
    ("Tupla local anotada", "fn main() -> bool { let t: (i32, bool) = (10, true); return t.1; }", {}),
    ("Tupla constante", 'const T: (i32, bool, String) = (10, true, "Hola");', {"T": (10, True, "Hola")}),
    ("Campo de constante", "const T: (i32, bool) = (10, true); const N: i32 = T.0;", {"T": (10, True), "N": 10}),
    ("Referencia adelantada", "const N: i32 = T.0; const T: (i32, bool) = (10, true);", {"N": 10, "T": (10, True)}),
    ("Tuplas anidadas", "const T: (i32, (bool, char)) = (10, (true, 'ñ')); const B: bool = T.1.0;", {"T": (10, (True, "ñ")), "B": True}),
    ("Tupla que contiene un arreglo", "const T: ([i32; 2], bool) = ([10, 20], true); const N: i32 = T.0[1];", {"T": ([10, 20], True), "N": 20}),
    ("Arreglo de tuplas", "const A: [(i32, bool); 2] = [(1, true), (2, false)]; const B: bool = A[1].1;", {"A": [(1, True), (2, False)], "B": False}),
    ("Tupla con arreglo vacío contextual", "const T: ([i32; 0], bool) = ([], true);", {"T": ([], True)}),
    ("Arreglo vacío de tuplas", "const A: [(i32, bool); 0] = [];", {"A": []}),
    ("Contexto anidado en tuplas y arreglos", "const T: (([i32; 0], bool), [char; 0]) = (([], true), []);", {"T": (([], True), [])}),
    ("Coma final en tipo y literal", "const T: (i32, bool,) = (10, true,);", {"T": (10, True)}),
    ("Paréntesis siguen agrupando", "const N: i32 = (10 + 20);", {"N": 30}),
    ("Literales decimales conservados", "const T: (f64, f64) = (1.5, 2.5); const X: f64 = T.0 + T.1;", {"T": (1.5, 2.5), "X": 4.0}),
    ("Unario después del campo", "const T: (i32, bool) = (10, true); const X: i32 = -T.0; const B: bool = !T.1;", {"T": (10, True), "X": -10, "B": False}),
    ("Campo con espacios", "const T: (i32, bool) = (10, true); const N: i32 = T . 0;", {"T": (10, True), "N": 10}),
    ("Inicialización diferida", "fn main() -> bool { let t: (i32, bool); t = (1, true); return t.1; }", {}),
    ("Reasignación completa", "fn main() { let mut t = (1, true); t = (2, false); }", {}),
    ("Asignación a un campo", "fn main() -> i32 { let mut t = (1, true); t.0 = 2; return t.0; }", {}),
    ("Asignación a campo bool", "fn main() { let mut t = (1, true); t.1 = false; }", {}),
    ("Asignación anidada", "fn main() { let mut t = (1, (true, 'a')); t.1.1 = 'b'; }", {}),
    ("Reemplazo de subtupla", "fn main() { let mut t = (1, (true, 'a')); t.1 = (false, 'b'); }", {}),
    ("Escritura mezclada con índices", "fn main() { let mut t = ([(1, true)], false); t.0[0].1 = false; }", {}),
    ("Reemplazo contextual de arreglo vacío", "fn main() { let mut t: ([i32; 0], bool) = ([], true); t.0 = []; }", {}),
    ("Reemplazo contextual de subtupla", "fn main() { let mut t: (i32, ([bool; 0], char)) = (1, ([], 'a')); t.1 = ([], 'b'); }", {}),
    ("Parámetro y retorno", "fn f(t: (i32, bool)) -> (i32, bool) { return t; } fn main() -> i32 { return f((1, true)).0; }", {}),
    ("Parámetro con contexto vacío", "fn f(t: ([i32; 0], bool)) {} fn main() { f(([], true)); }", {}),
    ("Retorno con contexto vacío", "fn f() -> ([i32; 0], bool) { return ([], true); }", {}),
    ("Parámetro mutable", "fn f(mut t: (i32, bool)) -> i32 { t.0 += 1; return t.0; }", {}),
    ("Tupla local oculta constante", "const T: (i32, bool) = (1, true); fn main() { let mut T = (2, false); T.0 = 3; }", {"T": (1, True)}),
    ("Campo como condición", "fn main() -> i32 { let t = (1, true); if t.1 { return t.0; } else { return 0; } }", {}),
    ("Campo dentro de un ciclo", "fn main() { let mut t = (0, true); while t.0 < 2 { t.0 += 1; } }", {}),
    ("Tupla local en loop", "fn main() { loop { let mut t = (0, true); t.0 += 1; break; } }", {}),
    ("Normalización recursiva de tamaños", "const T: ([i32; 00], bool) = ([], true);", {"T": ([], True)}),
]
for operador in ("+=", "-=", "*=", "/="):
    VALIDAS.append((f"Asignación compuesta {operador}", f"fn main() {{ let mut t = (12, true); t.0 {operador} 2; }}", {}))


# nombre, código, fase y fragmento de diagnóstico esperado.
INVALIDAS = [
    ("Tipo del campo incorrecto", "fn main() { let t: (i32, bool) = (true, 1); }", "semantico", "Tipos incompatibles"),
    ("Cantidad de campos incorrecta", "const T: (i32, bool) = (1, true, 'a');", "semantico", "Tipos incompatibles"),
    ("Campo fuera de rango", "fn main() { let t = (1, true); let x = t.2; }", "semantico", "fuera de rango"),
    ("Campo fuera de rango en constante", "const T: (i32, bool) = (1, true); const X: i32 = T.2;", "semantico", "fuera de rango"),
    ("Campo en entero", "fn main() { let x = (1).0; }", "semantico", "No se puede acceder"),
    ("Campo en arreglo", "fn main() { let a = [1, 2]; let x = a.0; }", "semantico", "No se puede acceder"),
    ("Índice de arreglo en tupla", "fn main() { let t = (1, true); let x = t[0]; }", "semantico", "No se puede indexar"),
    ("Campo interior en escalar", "fn main() { let t = (1, true); let x = t.0.0; }", "semantico", "No se puede acceder"),
    ("Tupla sin inicializar", "fn main() { let t: (i32, bool); let x = t.0; }", "semantico", "antes de inicializarla"),
    ("Escritura sin mut", "fn main() { let t = (1, true); t.0 = 2; }", "semantico", "No se puede modificar"),
    ("Compuesta sin mut", "fn main() { let t = (1, true); t.0 += 2; }", "semantico", "No se puede modificar"),
    ("Escritura de constante", "const T: (i32, bool) = (1, true); fn main() { T.0 = 2; }", "semantico", "No se puede modificar"),
    ("Escritura sin inicializar", "fn main() { let mut t: (i32, bool); t.0 = 2; }", "semantico", "antes de inicializarla"),
    ("Destino inexistente", "fn main() { t.0 = 2; }", "semantico", "no está declarada"),
    ("Campo destino fuera de rango", "fn main() { let mut t = (1, true); t.2 = 2; }", "semantico", "fuera de rango"),
    ("Tipo incorrecto al escribir campo", "fn main() { let mut t = (1, true); t.0 = false; }", "semantico", "Tipos incompatibles"),
    ("Compuesta de booleanos", "fn main() { let mut t = (1, true); t.1 += false; }", "semantico", "requiere números"),
    ("Compuesta de subtupla", "fn main() { let mut t = (1, (2, true)); t.1 += (3, false); }", "semantico", "requiere números"),
    ("Subarreglo con tamaño incorrecto", "fn main() { let mut t = ([1, 2], true); t.0 = [3]; }", "semantico", "Tipos incompatibles"),
    ("Argumento incompatible", "fn f(t: (i32, bool)) {} fn main() { f((true, 1)); }", "semantico", "Argumento 1"),
    ("Retorno incompatible", "fn f() -> (i32, bool) { return (true, 1); }", "semantico", "Retorno incompatible"),
    ("Arreglo de tuplas heterogéneas", "fn main() { let a = [(1, true), (false, 2)]; }", "semantico", "El elemento 2"),
    ("Campo unit", "fn f() {} fn main() { let t = (f(), 1); }", "semantico", "valores unit"),
    ("Vacío interior sin contexto", "fn main() { let t = ([], true); }", "semantico", "arreglo vacío"),
    ("Llamada en constante tupla", "const T: (i32, bool) = (f(), true); fn f() -> i32 { return 1; }", "semantico", "no puede inicializarse con una llamada"),
    ("Dependencia circular", "const T: (i32, bool) = (N, true); const N: i32 = T.0;", "semantico", "Dependencia circular"),
    ("Condición no bool", "fn main() { let t = (1, true); if t.0 {} }", "semantico", "debe ser bool"),
    ("Tupla de un solo campo fuera de gramática", "fn main() { let t = (1,); }", "sintactico", None),
    ("Campo negativo", "fn main() { let t = (1, true); let x = t.-1; }", "sintactico", None),
]


def recorrer(nodo):
    yield nodo
    for hijo in nodo.getChildren():
        if hasattr(hijo, "getChildren"):
            yield from recorrer(hijo)


def comprobar_backend():
    r = analizar_programa(
        "fn main() { let mut t = ([(1, true)], false); let i = 0; let x = false; t.0[i].1 = x; }"
    )
    assert r["valido"], r["errores"]
    destino = next(n for n in recorrer(r["arbol"]) if isinstance(n, RustiQParser.AssignmentContext))
    assert r["simbolos"][r["referencias"][destino]]["nombre"] == "t"
    assert r["tipos_expresiones"][destino] == "bool"
    campos = destino.tupleAccess()
    assert [r["tipos_expresiones"][n] for n in campos] == ["[(i32,bool);1]", "bool"]
    assert r["tipos_expresiones"][destino.indexAccess(0)] == "(i32,bool)"
    lecturas = [n for n in recorrer(destino) if isinstance(n, RustiQParser.PrimaryContext) and n.IDENT()]
    assert {r["simbolos"][r["referencias"][n]]["nombre"] for n in lecturas} == {"i", "x"}


def ejecutar_pruebas():
    correctas = 0
    for nombre, codigo, esperados in VALIDAS:
        r = analizar_programa(codigo)
        valores = {s["nombre"]: s["valor"] for s in r["simbolos"].values() if s["es_constante"]}
        cumple = r["valido"] and r["arbol"] is not None and not r["errores"] and valores == esperados
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple:
            correctas += 1
        else:
            print(r["errores"], valores)
    for nombre, codigo, fase, fragmento in INVALIDAS:
        r = analizar_programa(codigo)
        cumple = (
            not r["valido"] and r["arbol"] is None
            and any(e["fase"] == fase and (fragmento is None or fragmento in e["mensaje"]) for e in r["errores"])
            and all(r[c] == {} for c in ("simbolos", "referencias", "declaraciones", "tipos_expresiones", "funciones"))
        )
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple:
            correctas += 1
        else:
            print(r["errores"])
    comprobar_backend()
    correctas += 1
    print("Referencias y tipos para el backend: OK")
    total = len(VALIDAS) + len(INVALIDAS) + 1
    print(f"\nResultado: {correctas}/{total} pruebas OK")
    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()
