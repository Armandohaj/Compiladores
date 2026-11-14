"""Pruebas de lectura previa, mutabilidad y tipos en +=, -=, *= y /=.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# Cada prueba contiene:
# nombre, código y fragmento del error esperado.
# None significa que el programa debe ser válido.
PRUEBAS = []

# Probar cada operador con los dos tipos numéricos.
for operador in ("+=", "-=", "*=", "/="):
    for tipo, inicial, valor in (
        ("i32", "12", "2"),
        ("f64", "12.0", "2.0"),
    ):
        PRUEBAS.append((
            f"{operador} con {tipo}",
            f"""
fn main() -> {tipo} {{
    let mut numero = {inicial};
    numero {operador} {valor};
    return numero;
}}
""",
            None,
        ))

PRUEBAS.extend([
    (
        "Variable sin inicializar",
        """
fn main() -> i32 {
    let mut numero: i32;
    numero += 1;
    return 0;
}
""",
        "La variable 'numero' se usa antes de inicializarla.",
    ),
    (
        "Variable sin mut",
        """
fn main() -> i32 {
    let numero = 10;
    numero += 1;
    return numero;
}
""",
        "porque no fue declarada con 'mut'",
    ),
    (
        "Variable no declarada",
        """
fn main() -> i32 {
    numero += 1;
    return 0;
}
""",
        "La variable 'numero' no está declarada.",
    ),
    (
        "Tipos numéricos distintos",
        """
fn main() -> i32 {
    let mut numero = 10;
    numero += 2.5;
    return numero;
}
""",
        "No se puede operar i32 con f64",
    ),
    (
        "Asignación compuesta con bool",
        """
fn main() -> bool {
    let mut activo = true;
    activo += false;
    return activo;
}
""",
        "El operador '+' requiere números.",
    ),
    (
        "Asignación compuesta con String",
        """
fn main() -> String {
    let mut texto = "Hola";
    texto += "mundo";
    return texto;
}
""",
        "El operador '+' requiere números.",
    ),
    (
        "Asignación compuesta con char",
        """
fn main() -> char {
    let mut letra = 'A';
    letra -= 'B';
    return letra;
}
""",
        "El operador '-' requiere números.",
    ),
    (
        "Argumento derecho no declarado",
        """
fn main() -> i32 {
    let mut numero = 10;
    numero *= desconocida;
    return numero;
}
""",
        "La variable 'desconocida' no está declarada.",
    ),
    (
        "Inicialización simple antes de asignación compuesta",
        """
fn main() -> i32 {
    let mut numero: i32;
    numero = 10;
    numero += 2;
    return numero;
}
""",
        None,
    ),
    (
        "Asignación compuesta dentro de while",
        """
fn main() -> i32 {
    let mut numero = 0;
    while numero < 5 {
        numero += 1;
    }
    return numero;
}
""",
        None,
    ),
    (
        "Parámetro mutable",
        """
fn incrementar(mut numero: i32) -> i32 {
    numero += 1;
    return numero;
}

fn main() -> i32 {
    return incrementar(10);
}
""",
        None,
    ),
    (
        "Inicialización en una sola rama",
        """
fn main() -> i32 {
    let mut numero: i32;
    if true {
        numero = 10;
    }
    numero += 1;
    return 0;
}
""",
        "La variable 'numero' se usa antes de inicializarla.",
    ),
])


def ejecutar_pruebas():
    correctas = 0

    for nombre, codigo, esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)

        for error in resultado["errores"]:
            print(
                f"Error {error['fase']} — "
                f"Línea {error['linea']}, "
                f"columna {error['columna']}: "
                f"{error['mensaje']}"
            )

        if esperado is None:
            cumple = (
                resultado["valido"]
                and resultado["arbol"] is not None
                and not resultado["errores"]
            )
        else:
            # Comprobar el error concreto, no cualquier fallo.
            cumple = (
                not resultado["valido"]
                and resultado["arbol"] is None
                and any(
                    error["fase"] == "semantico"
                    and esperado in error["mensaje"]
                    for error in resultado["errores"]
                )
            )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", esperado or "un programa válido")

    print(f"\nResultado: {correctas}/{len(PRUEBAS)} pruebas OK")

    if correctas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()