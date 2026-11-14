"""Pruebas de prioridad y tipos de operaciones lógicas y aritméticas.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# Cada caso contiene:
# nombre, expresión, tipo de retorno y error esperado.
#
# None indica que la expresión debe aceptarse.
PRUEBAS = [
    ("Igualdad de enteros", "10 == 10", "bool", None),
    ("Diferencia de enteros", "10 != 20", "bool", None),
    ("Menor que", "10 < 20", "bool", None),
    ("Menor o igual", "10 <= 20", "bool", None),
    ("Mayor que", "20 > 10", "bool", None),
    ("Mayor o igual", "20 >= 10", "bool", None),
    ("Comparación de decimales", "2.5 < 3.5", "bool", None),
    ("Igualdad de booleanos", "true == false", "bool", None),
    ("Y lógico", "true && false", "bool", None),
    ("O lógico", "true || false", "bool", None),
    ("Negación lógica", "!false", "bool", None),
    (
        "Comparaciones combinadas",
        "(10 < 20) && (30 >= 25)",
        "bool",
        None,
    ),
    (
        "Aritmética dentro de comparación",
        "2 + 3 * 4 == 14",
        "bool",
        None,
    ),
    (
        "Negación de comparación",
        "!(10 > 20)",
        "bool",
        None,
    ),
    (
        "Comparación entre tipos distintos",
        "10 == 10.0",
        "bool",
        "Comparación incompatible",
    ),
    (
        "Orden entre booleanos",
        "true < false",
        "bool",
        "requiere valores numéricos",
    ),
    (
        "Entero en Y lógico",
        "10 && true",
        "bool",
        "requiere dos valores bool",
    ),
    (
        "Entero en O lógico",
        "false || 10",
        "bool",
        "requiere dos valores bool",
    ),
    (
        "Negación de entero",
        "!10",
        "bool",
        "requiere un valor bool",
    ),
    (
        "Comparación retornada como entero",
        "10 < 20",
        "i32",
        "Retorno incompatible",
    ),
]


def ejecutar_pruebas():
    aprobadas = 0

    for nombre, expresion, tipo_retorno, error_esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")

        # Construimos una función con la expresión de la prueba.
        codigo = (
            f"fn main() -> {tipo_retorno} {{\n"
            f"    return {expresion};\n"
            "}"
        )

        resultado = analizar_programa(codigo)
        errores = resultado["errores"]

        try:
            if error_esperado is None:
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

                # Comprobamos que se rechace por la razón esperada.
                assert any(
                    error["fase"] == "semantico"
                    and error_esperado in error["mensaje"]
                    for error in errores
                ), (
                    f"Falta el error '{error_esperado}'. "
                    f"Errores recibidos: {errores}"
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

    # Si alguna prueba falla, el proceso termina con código de error.
    if aprobadas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()