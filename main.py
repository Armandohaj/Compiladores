from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from generated.RustiQLexer import RustiQLexer
from generated.RustiQParser import RustiQParser


class RecolectorErrores(ErrorListener):
    def __init__(self, categoria):
        super().__init__()
        self.categoria = categoria
        self.errores = []

    def syntaxError(self, recognizer, offendingSymbol,
                    line, column, msg, e):
        self.errores.append(
            f"{self.categoria} — "
            f"Línea {line}, columna {column + 1}: {msg}"
        )


def analizar(codigo):
    errores_lexicos = RecolectorErrores("Error léxico")
    errores_sintacticos = RecolectorErrores("Error sintáctico")

    lexer = RustiQLexer(InputStream(codigo))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errores_lexicos)

    tokens = CommonTokenStream(lexer)

    parser = RustiQParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(errores_sintacticos)

    parser.program()

    errores = (
        errores_lexicos.errores
        + errores_sintacticos.errores
    )

    if errores:
        for error in errores:
            print(error)
        return False

    print("Análisis léxico y sintáctico correcto.")
    return True


if __name__ == "__main__":
    pruebas = [
        (
            "Programa correcto",
            """fn main() -> i32 {
    return 10 + 20;
}""",
            True,
        ),
        (
            "Falta punto y coma",
            """fn main() -> i32 {
    return 10 + 20
}""",
            False,
        ),
        (
            "Símbolo no permitido",
            """fn main() -> i32 {
    return 10 + @20;
}""",
            False,
        ),
        (
            "Variable con tipo",
            """fn main() -> i32 {
    let x: i32 = 10;
    return x + 20;
}""",
            True,
        ),
        (
            "Variable sin tipo explícito",
            """fn main() -> i32 {
    let x = 10;
    return x;
}""",
            True,
        ),
        (
            "Variable mutable y asignación",
            """fn main() -> i32 {
    let mut x: i32 = 10;
    x = x + 5;
    return x;
}""",
            True,
        ),
        (
            "Operaciones y paréntesis",
            """fn main() -> i32 {
    let x = (10 + 20) * 2 - 8 / 4;
    return x % 7;
}""",
            True,
        ),
        (
            "Número negativo",
            """fn main() -> i32 {
    let x = -10;
    return x;
}""",
            True,
        ),
        (
            "Falta nombre de variable",
            """fn main() -> i32 {
    let : i32 = 10;
    return 0;
}""",
            False,
        ),
        (
            "Falta expresión después del igual",
            """fn main() -> i32 {
    let x = ;
    return 0;
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