"""Punto de entrada del frontend RustiQ y API reutilizable por el servidor.

El flujo es texto -> tokens -> árbol de ANTLR -> análisis semántico ->
datos para el backend. analizar_programa no imprime y analizar sí muestra
mensajes en terminal. Importar este módulo no ejecuta el ejemplo final.
"""
from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from generated.RustiQLexer import RustiQLexer
from generated.RustiQParser import RustiQParser
from analizador_semantico import AnalizadorSemantico
from resolucion_variables import ResolucionVariables


# =====================================================
# 1. RECOLECCIÓN DE ERRORES
# =====================================================

class RecolectorErrores(ErrorListener):
    """Guarda los errores de ANTLR sin imprimirlos."""

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
            # ANTLR cuenta desde cero; mostramos desde uno.
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
    - arbol: árbol de ANTLR.
    - errores: errores léxicos, sintácticos o semánticos.
    - funciones: firmas de las funciones.
    - estructuras: nombre de estructura -> campos y tipos.
    - tipos_expresiones: nodo de expresión -> tipo.
    - simbolos: identificador de variable -> información.
    - declaraciones: nodo de declaración -> identificador.
    - referencias: nodo de lectura/asignación -> identificador.

    Si hay errores, el árbol será None y los diccionarios
    destinados al backend estarán vacíos.
    """

    errores_lexicos = RecolectorErrores("lexico")
    errores_sintacticos = RecolectorErrores("sintactico")

    # -------------------------------------------------
    # A. Análisis léxico: texto -> tokens.
    # -------------------------------------------------

    lexer = RustiQLexer(InputStream(codigo))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errores_lexicos)

    tokens = CommonTokenStream(lexer)

    # Recoger todos los errores léxicos antes de continuar.
    tokens.fill()
    tokens.seek(0)

    # -------------------------------------------------
    # B. Análisis sintáctico: tokens -> árbol.
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
    # C. Análisis semántico.
    # -------------------------------------------------

    semantico = None

    if not errores:
        semantico = AnalizadorSemantico()
        semantico.visit(arbol)
        errores.extend(semantico.errores)

    errores.sort(
        key=lambda error: (error["linea"], error["columna"])
    )

    valido = not errores

    # -------------------------------------------------
    # D. Preparar información para el backend.
    # -------------------------------------------------

    funciones = {}
    tipos_expresiones = {}
    simbolos = {}
    declaraciones = {}
    referencias = {}
    estructuras = {}

    if valido:
        estructuras = semantico.estructuras
        funciones = semantico.funciones
        tipos_expresiones = semantico.tipos_expresiones

        # Vincular cada uso de una variable con su declaración.
        # Se ejecuta únicamente sobre un programa válido.
        resolucion = ResolucionVariables(
            tipos_expresiones,
            semantico.valores_constantes,
        )
        resolucion.visit(arbol)

        simbolos = resolucion.simbolos
        declaraciones = resolucion.declaraciones
        referencias = resolucion.referencias

    # Estos mapas contienen nodos de ANTLR: se consumen dentro de Python.
    # El servidor puede enviar errores como JSON, pero no serializar el
    # árbol ni los mapas con nodos como claves directamente al navegador.
    return {
        "valido": valido,
        "arbol": arbol if valido else None,
        "errores": errores,
        "funciones": funciones,
        "tipos_expresiones": tipos_expresiones,
        "simbolos": simbolos,
        "declaraciones": declaraciones,
        "referencias": referencias,
        "estructuras": estructuras,
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