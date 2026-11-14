"""Pruebas de tipos devueltos y ausencia de retornos.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar


pruebas = [
    (
        "Función i32 con retorno correcto",
        """fn main() -> i32 {
    return 10;
}""",
        True,
    ),
    (
        "Función i32 con return sin valor",
        """fn main() -> i32 {
    return;
}""",
        False,
    ),
    (
        "Función i32 sin return",
        """fn main() -> i32 {
    let x = 10;
}""",
        False,
    ),
    (
        "Función sin tipo que retorna un entero",
        """fn main() {
    return 10;
}""",
        False,
    ),
    (
        "Función sin tipo con return vacío",
        """fn main() {
    return;
}""",
        True,
    ),
    (
        "Función sin tipo con bloque vacío",
        """fn main() {
}""",
        True,
    ),
    (
        "Retorno dentro de un bloque interior",
        """fn main() -> i32 {
    {
        return 10;
    }
}""",
        True,
    ),
    (
        "Retorno con variable no declarada",
        """fn main() -> i32 {
    return desconocida;
}""",
        False,
    ),
]

aprobadas = 0

for nombre, codigo, esperado in pruebas:
    print(f"\n--- {nombre} ---")
    resultado = analizar(codigo)

    if resultado == esperado:
        print("Prueba OK")
        aprobadas += 1
    else:
        print("Prueba FALLÓ")

print(f"\nResultado: {aprobadas}/{len(pruebas)} pruebas OK")

if aprobadas != len(pruebas):
    raise SystemExit(1)