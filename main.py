from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from generated.RustiQLexer import RustiQLexer
from generated.RustiQParser import RustiQParser
from analizador_semantico import AnalizadorSemantico


class RecolectorErrores(ErrorListener):
    def __init__(self, fase):
        super().__init__()
        self.fase = fase
        self.errores = []

    def syntaxError(self, recognizer, offendingSymbol,
                    line, column, msg, e):
        self.errores.append({
            "fase": self.fase,
            "mensaje": msg,
            "linea": line,
            "columna": column + 1,
        })


def analizar_programa(codigo):
    """Analiza el código y devuelve los resultados sin imprimir."""
    errores_lexicos = RecolectorErrores("lexico")
    errores_sintacticos = RecolectorErrores("sintactico")

    lexer = RustiQLexer(InputStream(codigo))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errores_lexicos)

    tokens = CommonTokenStream(lexer)

    # Leer todos los tokens para recoger los errores léxicos.
    tokens.fill()
    tokens.seek(0)

    parser = RustiQParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(errores_sintacticos)

    arbol = parser.program()

    errores = (
        errores_lexicos.errores
        + errores_sintacticos.errores
    )

    # No ejecutar la semántica sobre un programa mal formado.
    if not errores:
        semantico = AnalizadorSemantico()
        semantico.visit(arbol)
        errores.extend(semantico.errores)

    errores.sort(
        key=lambda error: (error["linea"], error["columna"])
    )

    return {
        "valido": not errores,
        "arbol": arbol if not errores else None,
        "errores": errores,
    }


def analizar(codigo):
    """Muestra el resultado en terminal y devuelve True o False."""
    resultado = analizar_programa(codigo)

    if resultado["valido"]:
        print(
            "Análisis léxico, sintáctico "
            "y semántico básico correcto."
        )
    else:
        for error in resultado["errores"]:
            print(
                f"Error {error['fase']} — "
                f"Línea {error['linea']}, "
                f"columna {error['columna']}: "
                f"{error['mensaje']}"
            )

    return resultado["valido"]


if __name__ == "__main__":
    codigo = """fn main() -> i32 {
    let x = 10;
    return x + 20;
}"""
    analizar(codigo)