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