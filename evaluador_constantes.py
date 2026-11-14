import math

from generated.RustiQVisitor import RustiQVisitor


class ErrorConstante(Exception):
    """Representa un error al calcular una expresión constante."""

    def __init__(self, token, mensaje):
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

    def __init__(self, tipos_expresiones, resolver_nombre):
        super().__init__()
        self.tipos_expresiones = tipos_expresiones
        self.resolver_nombre = resolver_nombre

    # =================================================
    # 1. EXPRESIONES Y OPERADORES LÓGICOS
    # =================================================

    def visitExpression(self, ctx):
        return self.visit(ctx.logicalOr())

    def visitLogicalOr(self, ctx):
        # Cortocircuito: si encontramos true,
        # no necesitamos calcular los demás operandos.
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
        if tipo == "i32" and not -(2**31) <= valor <= 2**31 - 1:
            raise ErrorConstante(
                token,
                "El resultado de la constante está fuera "
                "del rango de i32."
            )

        return valor

    def visitAdditive(self, ctx):
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
        cociente = abs(izquierdo) // abs(derecho)

        if (izquierdo < 0) != (derecho < 0):
            cociente = -cociente

        return cociente

    def division_decimal(self, izquierdo, derecho):
        # Representar también los resultados IEEE 754
        # cuando el divisor decimal es cero.
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
        valor = self.visit(ctx.primary())

        for expresion_indice in ctx.expression():
            indice = self.visit(expresion_indice)

            # El semántico comprueba los tipos antes de evaluar.
            # Estas guardas evitan filtrar excepciones de Python
            # si se utiliza el evaluador directamente.
            if not isinstance(valor, list):
                raise ErrorConstante(
                    expresion_indice.start,
                    "Solo se pueden indexar arreglos en una constante."
                )

            if type(indice) is not int:
                raise ErrorConstante(
                    expresion_indice.start,
                    "El índice de un arreglo debe ser i32."
                )

            # Python acepta índices negativos; RustiQ los rechaza.
            # También comprobar índices calculados como 1 + 2.
            if indice < 0 or indice >= len(valor):
                raise ErrorConstante(
                    expresion_indice.start,
                    f"Índice {indice} fuera de rango "
                    f"para un arreglo de tamaño {len(valor)}."
                )

            valor = valor[indice]

        return valor

    def visitArrayLiteral(self, ctx):
        # Cada elemento puede ser otra expresión o un arreglo.
        return [self.visit(expresion) for expresion in ctx.expression()]

    def decodificar_texto(self, texto):
        # Quitar las comillas y traducir los escapes
        # admitidos por nuestra gramática.
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

    def visitPrimary(self, ctx):
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

        if ctx.functionCall() is not None:
            raise ErrorConstante(
                ctx.functionCall().IDENT().getSymbol(),
                "Una constante no puede inicializarse "
                "con una llamada a función."
            )

        if ctx.IDENT() is not None:
            return self.resolver_nombre(ctx.IDENT().getSymbol())

        return self.visit(ctx.expression())
