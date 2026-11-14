"""Pruebas de contrato de analizar_programa y datos para backend.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


def ejecutar_pruebas():
    # Programa válido con parámetros y una llamada.
    codigo = """
fn sumar(a: i32, b: i32) -> i32 {
    return a + b;
}

fn main() -> i32 {
    return sumar(10, 20);
}
"""

    resultado = analizar_programa(codigo)
    comprobaciones = []

    comprobaciones.append((
        "Programa válido con árbol y sin errores",
        resultado["valido"]
        and resultado["arbol"] is not None
        and resultado["errores"] == [],
    ))

    comprobaciones.append((
        "Firma de sumar",
        resultado["funciones"].get("sumar") == {
            "parametros": ["i32", "i32"],
            "retorno": "i32",
        },
    ))

    comprobaciones.append((
        "Firma de main",
        resultado["funciones"].get("main") == {
            "parametros": [],
            "retorno": "i32",
        },
    ))

    # Recorremos el árbol devuelto para encontrar llamadas.
    # Así verificamos que las claves del mapa de tipos
    # pertenecen a ese mismo árbol.
    def buscar_llamadas(nodo):
        llamadas = []

        if type(nodo).__name__ == "FunctionCallContext":
            llamadas.append(nodo)

        for hijo in nodo.getChildren():
            if hasattr(hijo, "getChildren"):
                llamadas.extend(buscar_llamadas(hijo))

        return llamadas

    llamadas = buscar_llamadas(resultado["arbol"])

    comprobaciones.append((
        "Tipo de la llamada sumar(10, 20)",
        len(llamadas) == 1
        and resultado["tipos_expresiones"].get(llamadas[0]) == "i32",
    ))

    # Un error semántico debe impedir entregar datos al backend.
    invalido = analizar_programa("""
fn main() -> i32 {
    return desconocida;
}
""")

    comprobaciones.append((
        "Error semántico bloquea los datos del backend",
        not invalido["valido"]
        and invalido["arbol"] is None
        and invalido["funciones"] == {}
        and invalido["tipos_expresiones"] == {}
        and any(
            error["fase"] == "semantico"
            for error in invalido["errores"]
        ),
    ))

    # Lo mismo debe ocurrir ante errores sintácticos.
    mal_formado = analizar_programa("""
fn main() -> i32 {
    return 10
}
""")

    comprobaciones.append((
        "Error sintáctico bloquea los datos del backend",
        not mal_formado["valido"]
        and mal_formado["arbol"] is None
        and mal_formado["funciones"] == {}
        and mal_formado["tipos_expresiones"] == {}
        and any(
            error["fase"] == "sintactico"
            for error in mal_formado["errores"]
        ),
    ))

    # Cada análisis debe tener su propio registro de funciones.
    independiente = analizar_programa("""
fn otra() -> bool {
    return true;
}
""")

    comprobaciones.append((
        "Los análisis no comparten funciones",
        independiente["valido"]
        and set(independiente["funciones"]) == {"otra"}
        and set(resultado["funciones"]) == {"sumar", "main"},
    ))

    correctas = 0

    for nombre, cumple in comprobaciones:
        print(f"\n--- {nombre} ---")

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")

    print(
        f"\nResultado: {correctas}/{len(comprobaciones)} pruebas OK"
    )

    if correctas != len(comprobaciones):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()