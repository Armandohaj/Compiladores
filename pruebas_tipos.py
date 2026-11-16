"""Pruebas de compatibilidad entre los tipos básicos.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# None significa que el programa debe ser válido.
# Un texto indica parte del error semántico esperado.
PRUEBAS = [
    (
        "Variable y retorno f64",
        """fn main() -> f64 {
    let precio: f64 = 10.5;
    return precio;
}""",
        None,
    ),
    (
        "Variable y retorno bool",
        """fn main() -> bool {
    let activo: bool = true;
    return activo;
}""",
        None,
    ),
    (
        "Inferencia de f64",
        """fn main() -> f64 {
    let numero = 2.5;
    return numero * 2.0;
}""",
        None,
    ),
    (
        "Inferencia de bool",
        """fn main() -> bool {
    let activo = false;
    return activo;
}""",
        None,
    ),
    (
        "Asignación compatible",
        """fn main() -> bool {
    let mut activo = true;
    activo = false;
    return activo;
}""",
        None,
    ),
    (
        "Inicialización posterior de f64",
        """fn main() -> f64 {
    let numero: f64;
    numero = 3.5;
    return numero;
}""",
        None,
    ),
    (
        "Inicializador incompatible",
        """fn main() -> i32 {
    let numero: i32 = true;
    return 0;
}""",
        "Tipos incompatibles",
    ),
    (
        "Asignación incompatible",
        """fn main() -> i32 {
    let mut numero: i32 = 10;
    numero = false;
    return numero;
}""",
        "Tipos incompatibles",
    ),
    (
        "Retorno incompatible",
        """fn main() -> i32 {
    return true;
}""",
        "Retorno incompatible",
    ),
    (
        "Suma de entero y decimal",
        """fn main() -> f64 {
    return 10 + 2.5;
}""",
        "sin una conversión explícita",
    ),
    (
        "Suma de booleanos",
        """fn main() -> bool {
    return true + false;
}""",
        "requiere números",
    ),
    (
        "Negativo de booleano",
        """fn main() -> bool {
    return -true;
}""",
        "requiere un número",
    ),
    (
        "Módulo entre enteros",
        """fn main() -> i32 {
    return 10 % 3;
}""",
        None,
    ),
    (
        "Módulo entre decimales",
        """fn main() -> f64 {
    return 10.5 % 2.0;
}""",
        "solo admite i32",
    ),
    (
        "Variable sin tipo ni inicializador",
        """fn main() -> i32 {
    let numero;
    return 0;
}""",
        "No se puede determinar el tipo",
    ),
    (
        "Paréntesis conservan el tipo",
        """fn main() -> f64 {
    return -(2.5 + 1.5) * 2.0;
}""",
        None,
    ),
]


def ejecutar_pruebas():
    aprobadas = 0

    for nombre, codigo, mensaje_esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        errores = resultado["errores"]

        try:
            if mensaje_esperado is None:
                assert resultado["valido"], (
                    f"Se esperaba un programa válido: {errores}"
                )
                assert errores == []
                assert resultado["arbol"] is not None
            else:
                assert not resultado["valido"], (
                    "El programa debía ser rechazado."
                )
                assert resultado["arbol"] is None

                assert any(
                    error["fase"] == "semantico"
                    and mensaje_esperado in error["mensaje"]
                    for error in errores
                ), (
                    "No apareció el error semántico esperado: "
                    f"'{mensaje_esperado}'. Errores: {errores}"
                )

            for error in errores:
                print(
                    f"Error {error['fase']} — "
                    f"Línea {error['linea']}, "
                    f"columna {error['columna']}: "
                    f"{error['mensaje']}"
                )

            print("Prueba OK")
            aprobadas += 1

        except AssertionError as error:
            print(f"Prueba FALLÓ: {error}")

    print(f"\nResultado: {aprobadas}/{len(PRUEBAS)} pruebas OK")

    if aprobadas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()