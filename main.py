from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from generated.RustiQLexer import RustiQLexer
from generated.RustiQParser import RustiQParser
from analizador_semantico import AnalizadorSemantico


# =====================================================
# 1. RECOLECCIÓN DE ERRORES
# =====================================================

class RecolectorErrores(ErrorListener):
    """Guarda errores de ANTLR sin imprimirlos directamente."""

    def __init__(self, fase):
        super().__init__()
        self.fase = fase
        self.errores = []

    def syntaxError(
        self, recognizer, offendingSymbol,
        line, column, msg, e
    ):
        self.errores.append({
            "fase": self.fase,
            "mensaje": msg,
            "linea": line,
            # ANTLR cuenta columnas desde cero.
            # Las mostramos desde uno para el usuario.
            "columna": column + 1,
        })


# =====================================================
# 2. ANÁLISIS REUTILIZABLE
# =====================================================

def analizar_programa(codigo):
    """
    Analiza código RustiQ sin imprimir.

    Devuelve:
    - valido: indica si el programa pasó el análisis.
    - arbol: árbol de ANTLR, disponible si es válido.
    - errores: lista de errores estructurados.
    - funciones: firmas de las funciones del programa.
    - tipos_expresiones: relación nodo de ANTLR -> tipo.

    El árbol y los datos semánticos se entregan únicamente
    cuando el programa completo es válido.
    """

    errores_lexicos = RecolectorErrores("lexico")
    errores_sintacticos = RecolectorErrores("sintactico")

    # -------------------------------------------------
    # A. Análisis léxico: convertir texto en tokens.
    # -------------------------------------------------

    lexer = RustiQLexer(InputStream(codigo))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errores_lexicos)

    tokens = CommonTokenStream(lexer)

    # Leer todos los tokens para recoger errores léxicos.
    tokens.fill()
    tokens.seek(0)

    # -------------------------------------------------
    # B. Análisis sintáctico: construir el árbol.
    # -------------------------------------------------

    parser = RustiQParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(errores_sintacticos)

    arbol = parser.program()

    errores = (
        errores_lexicos.errores
        + errores_sintacticos.errores
    )

    # -------------------------------------------------
    # C. Análisis semántico: comprobar significado.
    # -------------------------------------------------

    semantico = None

    # Solo revisar semántica si el código está bien formado.
    if not errores:
        semantico = AnalizadorSemantico()
        semantico.visit(arbol)
        errores.extend(semantico.errores)

    # Ordenar los errores según su posición en el archivo.
    errores.sort(
        key=lambda error: (error["linea"], error["columna"])
    )

    valido = not errores

    # -------------------------------------------------
    # D. Datos que utilizará el backend.
    # -------------------------------------------------

    funciones = {}
    tipos_expresiones = {}

    if valido:
        # Ejemplo de firma:
        # "sumar": {
        #     "parametros": ["i32", "i32"],
        #     "retorno": "i32"
        # }
        funciones = semantico.funciones

        # Las claves son los mismos nodos del árbol devuelto.
        # El backend puede consultar:
        # tipos_expresiones[nodo]
        tipos_expresiones = semantico.tipos_expresiones

    return {
        "valido": valido,
        "arbol": arbol if valido else None,
        "errores": errores,
        "funciones": funciones,
        "tipos_expresiones": tipos_expresiones,
    }


# =====================================================
# 3. SALIDA PARA LA TERMINAL
# =====================================================

def analizar(codigo):
    """Muestra el resultado y devuelve True o False."""

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


# =====================================================
# 4. EJEMPLO AL EJECUTAR ESTE ARCHIVO
# =====================================================

# Este ejemplo solo se ejecuta con python main.py.
# No se ejecuta cuando otro archivo importa las funciones.
if __name__ == "__main__":
    codigo = """
fn sumar(a: i32, b: i32) -> i32 {
    return a + b;
}

fn main() -> i32 {
    let resultado = sumar(10, 20);
    return resultado;
}
"""
    analizar(codigo)