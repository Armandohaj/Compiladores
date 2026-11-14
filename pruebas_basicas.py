"""Pruebas de léxico, sintaxis, declaración de variables y ámbitos.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


PRUEBAS = [
    (
        "Programa correcto",
        """fn main() -> i32 {
    return 10 + 20;
}""",
        None,
    ),
    (
        "Falta punto y coma",
        """fn main() -> i32 {
    return 10 + 20
}""",
        "sintactico",
    ),
    (
        "Símbolo no permitido",
        """fn main() -> i32 {
    return 10 + @20;
}""",
        "lexico",
    ),
    (
        "Variable con tipo",
        """fn main() -> i32 {
    let x: i32 = 10;
    return x + 20;
}""",
        None,
    ),
    (
        "Variable sin tipo explícito",
        """fn main() -> i32 {
    let x = 10;
    return x;
}""",
        None,
    ),
    (
        "Variable mutable y asignación",
        """fn main() -> i32 {
    let mut x: i32 = 10;
    x = x + 5;
    return x;
}""",
        None,
    ),
    (
        "Operaciones y paréntesis",
        """fn main() -> i32 {
    let x = (10 + 20) * 2 - 8 / 4;
    return x % 7;
}""",
        None,
    ),
    (
        "Número negativo",
        """fn main() -> i32 {
    let x = -10;
    return x;
}""",
        None,
    ),
    (
        "Falta nombre de variable",
        """fn main() -> i32 {
    let : i32 = 10;
    return 0;
}""",
        "sintactico",
    ),
    (
        "Falta expresión después del igual",
        """fn main() -> i32 {
    let x = ;
    return 0;
}""",
        "sintactico",
    ),
    (
        "Uso de variable no declarada",
        """fn main() -> i32 {
    return x;
}""",
        "semantico",
    ),
    (
        "Variable duplicada en el mismo ámbito",
        """fn main() -> i32 {
    let x = 10;
    let x = 20;
    return x;
}""",
        "semantico",
    ),
    (
        "Uso antes de inicializar",
        """fn main() -> i32 {
    let x: i32;
    return x;
}""",
        "semantico",
    ),
    (
        "Modificación sin mut",
        """fn main() -> i32 {
    let x = 10;
    x = 20;
    return x;
}""",
        "semantico",
    ),
    (
        "Primera asignación a variable sin inicializar",
        """fn main() -> i32 {
    let x: i32;
    x = 10;
    return x;
}""",
        None,
    ),
    (
        "Variable fuera de su ámbito",
        """fn main() -> i32 {
    {
        let x = 10;
    }
    return x;
}""",
        "semantico",
    ),
    (
        "Mismo nombre en un ámbito interior",
        """fn main() -> i32 {
    let x = 10;
    {
        let x = 20;
    }
    return x;
}""",
        None,
    ),
    (
        "Asignación a variable no declarada",
        """fn main() -> i32 {
    x = 10;
    return 0;
}""",
        "semantico",
    ),
]


def ejecutar_pruebas():
    aprobadas = 0

    for nombre, codigo, fase_esperada in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)

        try:
            errores = resultado["errores"]

            if fase_esperada is None:
                assert resultado["valido"], (
                    "Se esperaba un programa válido."
                )
                assert errores == [], (
                    "Un programa válido no debe tener errores."
                )
                assert resultado["arbol"] is not None, (
                    "Falta el árbol del programa válido."
                )
            else:
                assert not resultado["valido"], (
                    "Se esperaba que el programa fuera rechazado."
                )
                assert resultado["arbol"] is None, (
                    "No debe entregarse un árbol válido con errores."
                )
                assert any(
                    error["fase"] == fase_esperada
                    for error in errores
                ), f"Falta un error de fase '{fase_esperada}'."

            for error in errores:
                assert isinstance(error["mensaje"], str)
                assert error["mensaje"]
                assert isinstance(error["linea"], int)
                assert error["linea"] >= 1
                assert isinstance(error["columna"], int)
                assert error["columna"] >= 1

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
            print(f"Resultado recibido: {resultado}")

    print(f"\nResultado: {aprobadas}/{len(PRUEBAS)} pruebas OK")

    if aprobadas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()