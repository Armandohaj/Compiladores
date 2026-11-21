# Evaluación restringida durante compilación. Produce valores para constantes ya tipadas,
# sin ejecutar funciones RustiQ ni sustituir la ejecución WASM del programa.
"""Evaluación durante la compilación de expresiones constantes ya tipadas.

Cada visit devuelve un valor de Python: int, float, bool, str, list, tuple
o un diccionario etiquetado para estructuras. Es una representación para
el compilador; no se usa eval ni se ejecutan funciones del usuario.
Los errores previstos se convierten en ErrorConstante para que main los
entregue con fase, mensaje, línea y columna.
"""
import math

from generated.RustiQVisitor import RustiQVisitor
from tipos_compuestos import accesos_lectura
from match_constante import coincidir


class ErrorConstante(Exception):
    """Representa un error al calcular una expresión constante."""

    def __init__(self, token, mensaje):
        """Guarda el token de origen y el mensaje de un error de evaluación constante."""
        # Inicializa el cálculo con tipos ya comprobados, resolución de nombres y etiquetas
        # de enums; los ámbitos temporales se crean al visitar bloques o patrones.
        super().__init__(mensaje)
        self.token = token
        self.mensaje = mensaje


class EvaluadorConstantes(RustiQVisitor):
    """
    Calcula expresiones cuyo tipo ya fue comprobado.

    resolver_nombre es una función que recibe un token
    de identificador y devuelve el valor de esa constante.

    No utiliza eval ni ejecuta funciones RustiQ.
    """

    def __init__(
        self,
        tipos_expresiones,
        resolver_nombre,
        enumeraciones=None,
    ):
        # Inicializa el cálculo con tipos ya comprobados, resolución de nombres y etiquetas
        # de enums; los ámbitos temporales se crean al visitar bloques o patrones.
        super().__init__()

        # Tipos que ya comprobó el semántico.
        self.tipos_expresiones = tipos_expresiones

        # Función que obtiene el valor de otra constante.
        self.resolver_nombre = resolver_nombre
        # Receptores de patrones y lets del bloque constante actual.
        self.ambitos_locales = []

        # Registro de enums y etiquetas de sus variantes.
        self.enumeraciones = (
            enumeraciones
            if enumeraciones is not None
            else {}
        )

    # =================================================
    # 1. EXPRESIONES Y OPERADORES LÓGICOS
    # =================================================

    def visitExpression(self, ctx):
        """Devuelve el valor calculado de la expresión; no imprime ni modifica variables del usuario."""
        return self.visit(ctx.logicalOr())

    def visitLogicalOr(self, ctx):
        # Cortocircuito: si encontramos true,
        # no necesitamos calcular los demás operandos.
        """Calcula || con cortocircuito: true evita evaluar operandos posteriores."""
        operandos = ctx.logicalAnd()
        valor = self.visit(operandos[0])

        for operando in operandos[1:]:
            if valor:
                return True
            valor = self.visit(operando)

        return valor

    def visitLogicalAnd(self, ctx):
        # Cortocircuito: si encontramos false,
        # no necesitamos calcular los demás operandos.
        """Calcula && con cortocircuito: false evita evaluar operandos posteriores."""
        operandos = ctx.comparison()
        valor = self.visit(operandos[0])

        for operando in operandos[1:]:
            if not valor:
                return False
            valor = self.visit(operando)

        return valor

    # =================================================
    # 2. COMPARACIONES
    # =================================================

    def visitComparison(self, ctx):
        """Compara valores que el semántico ya verificó como compatibles y devuelve bool."""
        operandos = ctx.additive()
        izquierdo = self.visit(operandos[0])

        if ctx.relOp() is None:
            return izquierdo

        derecho = self.visit(operandos[1])
        operador = ctx.relOp().getText()

        if operador == "==":
            return izquierdo == derecho
        if operador == "!=":
            return izquierdo != derecho
        if operador == "<":
            return izquierdo < derecho
        if operador == "<=":
            return izquierdo <= derecho
        if operador == ">":
            return izquierdo > derecho

        return izquierdo >= derecho

    # =================================================
    # 3. OPERACIONES ARITMÉTICAS
    # =================================================

    def comprobar_rango(self, valor, tipo, token):
        # Una constante i32 debe caber en 32 bits con signo.
        """Rechaza resultados i32 que no caben en 32 bits con signo; devuelve el valor si es válido."""
        if tipo == "i32" and not -(2**31) <= valor <= 2**31 - 1:
            raise ErrorConstante(
                token,
                "El resultado de la constante está fuera "
                "del rango de i32."
            )

        return valor

    def visitAdditive(self, ctx):
        """Calcula sumas y restas en orden y comprueba desbordamiento i32 después de cada operación."""
        operandos = ctx.multiplicative()
        valor = self.visit(operandos[0])
        tipo = self.tipos_expresiones[ctx]

        for indice, operando in enumerate(operandos[1:], start=1):
            token = ctx.getChild(2 * indice - 1).getSymbol()
            derecho = self.visit(operando)

            if token.text == "+":
                valor += derecho
            else:
                valor -= derecho

            self.comprobar_rango(valor, tipo, token)

        return valor

    def division_entera(self, izquierdo, derecho):
        # Truncar hacia cero, evitando convertir a float.
        """Divide enteros truncando hacia cero, sin convertirlos primero a float."""
        cociente = abs(izquierdo) // abs(derecho)

        if (izquierdo < 0) != (derecho < 0):
            cociente = -cociente

        return cociente

    def division_decimal(self, izquierdo, derecho):
        # Representar también los resultados IEEE 754
        # cuando el divisor decimal es cero.
        """Calcula división f64 y representa infinito o NaN cuando corresponde a divisor cero."""
        if derecho != 0.0:
            return izquierdo / derecho

        if izquierdo == 0.0 or math.isnan(izquierdo):
            return math.nan

        signo = (
            math.copysign(1.0, izquierdo)
            * math.copysign(1.0, derecho)
        )
        return math.copysign(math.inf, signo)

    def visitMultiplicative(self, ctx):
        """Calcula productos, divisiones y residuos; rechaza división entera por cero y comprueba rango."""
        operandos = ctx.unary()
        valor = self.visit(operandos[0])
        tipo = self.tipos_expresiones[ctx]

        for indice, operando in enumerate(operandos[1:], start=1):
            token = ctx.getChild(2 * indice - 1).getSymbol()
            derecho = self.visit(operando)

            if token.text == "*":
                valor *= derecho

            elif tipo == "i32":
                if derecho == 0:
                    raise ErrorConstante(
                        token,
                        "División o residuo entre cero "
                        "en una constante i32."
                    )

                cociente = self.division_entera(valor, derecho)

                if token.text == "/":
                    valor = cociente
                else:
                    # El residuo conserva el signo del dividendo.
                    valor = valor - cociente * derecho

            else:
                # El semántico ya rechaza % con f64.
                valor = self.division_decimal(valor, derecho)

            self.comprobar_rango(valor, tipo, token)

        return valor

    # =================================================
    # 4. OPERADORES UNARIOS
    # =================================================

    def visitUnary(self, ctx):
        # La gramática aplica los unarios al resultado de postfix,
        # que también puede contener uno o varios accesos a arreglos.
        """Evalúa postfix y aplica - o !. Después comprueba el rango del resultado."""
        # Evalúa la estructura actual de la regla unary; no presupone que su operando siga
        # siendo primary después de cambios de gramática.
        valor = self.visit(ctx.postfix())

        if ctx.MINUS() is not None:
            valor = -valor
        elif ctx.NOT() is not None:
            valor = not valor

        return self.comprobar_rango(
            valor,
            self.tipos_expresiones[ctx],
            ctx.start,
        )

    # =================================================
    # 5. LITERALES Y REFERENCIAS
    # =================================================

    def visitPostfix(self, ctx):
        """Evalúa accesos mezclados. Convierte índices o campos inválidos en ErrorConstante, evitando excepciones de Python."""
        valor = self.visit(ctx.primary())
        for clase, nodo in accesos_lectura(ctx):
            if clase == "nombre":
                nombre = nodo.IDENT().getText()
                if not isinstance(valor, dict) or "campos" not in valor or nombre not in valor["campos"]:
                    raise ErrorConstante(nodo.start, f"No se puede acceder al campo '{nombre}' en esta constante.")
                valor = valor["campos"][nombre]
                continue
            if clase == "campo":
                posicion = int(nodo.getText()[1:])
                if not isinstance(valor, tuple):
                    raise ErrorConstante(nodo.start, "Solo se pueden acceder campos de una tupla constante.")
                if posicion >= len(valor):
                    raise ErrorConstante(nodo.start, f"Campo {posicion} fuera de rango para una tupla de {len(valor)} elementos.")
                valor = valor[posicion]
                continue
            indice = self.visit(nodo)
            if not isinstance(valor, list):
                raise ErrorConstante(nodo.start, "Solo se pueden indexar arreglos en una constante.")
            if type(indice) is not int:
                raise ErrorConstante(nodo.start, "El índice de un arreglo debe ser i32.")
            # No permitir los índices negativos que Python sí acepta.
            if indice < 0 or indice >= len(valor):
                raise ErrorConstante(nodo.start, f"Índice {indice} fuera de rango para un arreglo de tamaño {len(valor)}.")
            valor = valor[indice]
        return valor

    def visitStructLiteral(self, ctx):
        # Conservar el nombre nominal además de los valores de sus campos.
        """Construye un diccionario etiquetado con el nombre nominal y los valores de los campos."""
        return {
            "estructura": ctx.IDENT().getText(),
            "campos": {campo.IDENT().getText(): self.visit(campo.expression()) for campo in ctx.fieldInit()},
        }

    def visitTupleLiteral(self, ctx):
        # tuple preserva la diferencia entre una tupla y un arreglo.
        """Devuelve tuple de Python para conservar la diferencia con los arreglos list."""
        return tuple(self.visit(expresion) for expresion in ctx.expression())

    def visitArrayLiteral(self, ctx):
        # Cada elemento puede ser otra expresión o un arreglo.
        """Evalúa cada elemento y devuelve list; admite valores compuestos anidados."""
        return [self.visit(expresion) for expresion in ctx.expression()]

    def decodificar_texto(self, texto):
        # Quitar las comillas y traducir los escapes
        # admitidos por nuestra gramática.
        """Quita las comillas y traduce únicamente los escapes que acepta la gramática."""
        contenido = texto[1:-1]

        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "0": "\0",
            '"': '"',
            "'": "'",
            "\\": "\\",
        }

        resultado = []
        indice = 0

        while indice < len(contenido):
            caracter = contenido[indice]

            if caracter == "\\":
                indice += 1
                caracter = escapes[contenido[indice]]

            resultado.append(caracter)
            indice += 1

        return "".join(resultado)


    def visitEnumValue(self, ctx):
        """
        Calcula una variante de enumeración constante.

        Conserva:
        - Nombre del enum.
        - Nombre de la variante.
        - Etiqueta numérica.
        - Valores asociados, si la variante recibe datos.

        El semántico ya comprobó los tipos de los argumentos.
        """

        token_tipo = ctx.IDENT(0).getSymbol()
        token_variante = ctx.IDENT(1).getSymbol()

        nombre = token_tipo.text
        variante = token_variante.text

        enumeracion = self.enumeraciones.get(nombre)

        if enumeracion is None:
            raise ErrorConstante(
                token_tipo,
                f"La enumeración '{nombre}' no está declarada."
            )

        variantes = enumeracion["variantes"]

        if variante not in variantes:
            raise ErrorConstante(
                token_variante,
                f"La enumeración '{nombre}' "
                f"no tiene la variante '{variante}'."
            )

        esperados = enumeracion.get(
            "datos_variantes", {}
        ).get(variante, [])

        lista = ctx.argumentList()
        argumentos = (
            lista.expression() if lista is not None else []
        )

        # Estas comprobaciones también protegen al evaluador
        # si se utiliza directamente fuera del flujo habitual.
        if len(argumentos) != len(esperados):
            raise ErrorConstante(
                token_variante,
                f"La variante '{nombre}::{variante}' espera "
                f"{len(esperados)} argumentos, pero recibió "
                f"{len(argumentos)}."
            )

        tiene_parentesis = ctx.LPAREN() is not None

        if bool(esperados) != tiene_parentesis:
            raise ErrorConstante(
                token_variante,
                f"Uso incorrecto de paréntesis en "
                f"'{nombre}::{variante}'."
            )

        resultado = {
            "enumeracion": nombre,
            "variante": variante,
            "etiqueta": variantes[variante],
        }

        if esperados:
            # Cada argumento puede ser otra expresión constante,
            # un arreglo, una tupla, una estructura u otro enum.
            resultado["datos"] = [
                self.visit(argumento)
                for argumento in argumentos
            ]

        # Las variantes sin datos conservan su formato anterior.
        return resultado

    def visitMatchExpr(self, ctx):
        """Evalúa una vez el valor y únicamente el primer brazo compatible."""
        valor = self.visit(ctx.expression())
        for brazo in ctx.matchArm():
            capturas = coincidir(self, brazo.pattern(), valor)
            if capturas is not None:
                self.ambitos_locales.append(capturas)
                try:
                    return self.visit(brazo.expression())
                finally:
                    self.ambitos_locales.pop()
        # Defensa si se utiliza el evaluador sin validar exhaustividad.
        raise ErrorConstante(ctx.start, "Ningún patrón coincide en el match constante.")

    def visitBlock(self, ctx):
        """Calcula un bloque puro, con variables locales limitadas a su ámbito."""
        # El ámbito temporal de esta evaluación contiene valores de compilación, no locales
        # WASM. Se retira con finally incluso cuando el cálculo falla.
        self.ambitos_locales.append({})
        try:
            for sentencia in ctx.statement():
                self.visit(sentencia)
            return self.visit(ctx.expression()) if ctx.expression() is not None else None
        finally:
            self.ambitos_locales.pop()

    def visitLetDecl(self, ctx):
        """Calcula el inicializador antes de introducir el nombre, como el semántico."""
        expresion = ctx.expression()
        valor = self.visit(expresion) if expresion is not None else None
        self.ambitos_locales[-1][ctx.IDENT().getText()] = valor

    def visitPrimary(self, ctx):
        """Calcula valores cuyo tipo ya fue validado."""

        if ctx.INT() is not None:
            return int(ctx.INT().getText())

        if ctx.FLOAT() is not None:
            return float(ctx.FLOAT().getText())

        if ctx.TRUE() is not None:
            return True

        if ctx.FALSE() is not None:
            return False

        if ctx.CHAR_LITERAL() is not None:
            return self.decodificar_texto(
                ctx.CHAR_LITERAL().getText()
            )

        if ctx.STRING_LITERAL() is not None:
            return self.decodificar_texto(
                ctx.STRING_LITERAL().getText()
            )

        if ctx.arrayLiteral() is not None:
            return self.visit(ctx.arrayLiteral())

        if ctx.tupleLiteral() is not None:
            return self.visit(ctx.tupleLiteral())

        if ctx.structLiteral() is not None:
            return self.visit(ctx.structLiteral())

        if ctx.enumValue() is not None:
            return self.visit(ctx.enumValue())

        if ctx.functionCall() is not None:
            raise ErrorConstante(
                ctx.functionCall().IDENT().getSymbol(),
                "Una constante no puede inicializarse "
                "con una llamada a función."
            )

        if ctx.matchExpr() is not None:
            return self.visit(ctx.matchExpr())

        if ctx.block() is not None:
            return self.visit(ctx.block())

        if ctx.IDENT() is not None:
            nombre = ctx.IDENT().getText()
            for ambito in reversed(self.ambitos_locales):
                if nombre in ambito:
                    return ambito[nombre]
            return self.resolver_nombre(
                ctx.IDENT().getSymbol()
            )

        # Expresión entre paréntesis.
        return self.visit(ctx.expression())