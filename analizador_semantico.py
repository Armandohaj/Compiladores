from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser


class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
        super().__init__()
        self.ambitos = []
        self.errores = []
        self.tipo_retorno = None
        self.tipos_expresiones = {}

    def reportar(self, token, mensaje):
        self.errores.append({
            "fase": "semantico",
            "mensaje": mensaje,
            "linea": token.line,
            "columna": token.column + 1,
        })

    def obtener_tipo_declarado(self, ctx):
        nodo_tipo = ctx.getTypedRuleContext(
            RustiQParser.TypeContext, 0
        )
        return nodo_tipo.getText() if nodo_tipo else None

    def guardar_tipo(self, ctx, tipo):
        self.tipos_expresiones[ctx] = tipo
        return tipo

    def buscar_variable(self, nombre):
        for ambito in reversed(self.ambitos):
            if nombre in ambito:
                return ambito[nombre]
        return None

    def visitFunctionDecl(self, ctx):
        ambitos_anteriores = self.ambitos
        retorno_anterior = self.tipo_retorno

        self.ambitos = []
        self.tipo_retorno = (
            self.obtener_tipo_declarado(ctx) or "unit"
        )

        try:
            self.visit(ctx.block())

            if (
                self.tipo_retorno != "unit"
                and not self.bloque_garantiza_retorno(ctx.block())
            ):
                self.reportar(
                    ctx.IDENT().getSymbol(),
                    "La función debe retornar un valor "
                    f"{self.tipo_retorno}."
                )
        finally:
            self.ambitos = ambitos_anteriores
            self.tipo_retorno = retorno_anterior

    def bloque_garantiza_retorno(self, ctx):
        # Válido para los bloques secuenciales actuales.
        # Se ampliará al agregar condiciones y ciclos.
        for sentencia in ctx.statement():
            if sentencia.returnStmt() is not None:
                return True

            if sentencia.block() is not None:
                if self.bloque_garantiza_retorno(sentencia.block()):
                    return True

        return False

    def visitBlock(self, ctx):
        self.ambitos.append({})

        try:
            for sentencia in ctx.statement():
                self.visit(sentencia)
        finally:
            self.ambitos.pop()

    def visitLetDecl(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        ambito = self.ambitos[-1]
        tipo_declarado = self.obtener_tipo_declarado(ctx)
        expresion = ctx.expression()

        errores_antes = len(self.errores)
        tipo_valor = (
            self.visit(expresion)
            if expresion is not None
            else None
        )

        if nombre in ambito:
            self.reportar(
                token,
                f"La variable '{nombre}' ya fue declarada "
                "en este ámbito."
            )
            return

        if tipo_declarado is None and expresion is None:
            self.reportar(
                token,
                f"No se puede determinar el tipo de '{nombre}': "
                "indicá un tipo o un valor inicial."
            )

        if (
            tipo_declarado is not None
            and tipo_valor is not None
            and tipo_declarado != tipo_valor
        ):
            self.reportar(
                token,
                f"Tipos incompatibles en '{nombre}': "
                f"se esperaba {tipo_declarado}, "
                f"pero se recibió {tipo_valor}."
            )

        ambito[nombre] = {
            "tipo": tipo_declarado or tipo_valor,
            "mutable": ctx.MUT() is not None,
            "inicializada": (
                expresion is not None
                and tipo_valor is not None
                and len(self.errores) == errores_antes
            ),
        }

    def visitAssignment(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        variable = self.buscar_variable(nombre)

        errores_antes = len(self.errores)
        tipo_valor = self.visit(ctx.expression())

        if variable is None:
            self.reportar(
                token,
                f"La variable '{nombre}' no está declarada."
            )
            return

        if variable["inicializada"] and not variable["mutable"]:
            self.reportar(
                token,
                f"No se puede modificar '{nombre}' "
                "porque no fue declarada con 'mut'."
            )
            return

        if (
            variable["tipo"] is not None
            and tipo_valor is not None
            and variable["tipo"] != tipo_valor
        ):
            self.reportar(
                token,
                f"Tipos incompatibles en '{nombre}': "
                f"se esperaba {variable['tipo']}, "
                f"pero se recibió {tipo_valor}."
            )
            return

        if (
            tipo_valor is not None
            and len(self.errores) == errores_antes
        ):
            variable["inicializada"] = True

    def visitReturnStmt(self, ctx):
        expresion = ctx.expression()
        token = ctx.RETURN().getSymbol()

        tipo_valor = (
            self.visit(expresion)
            if expresion is not None
            else "unit"
        )

        if (
            tipo_valor is not None
            and tipo_valor != self.tipo_retorno
        ):
            self.reportar(
                token,
                "Retorno incompatible: "
                f"se esperaba {self.tipo_retorno}, "
                f"pero se recibió {tipo_valor}."
            )

    def visitExpression(self, ctx):
        tipo = self.visit(ctx.additive())
        return self.guardar_tipo(ctx, tipo)

    def comprobar_operacion(self, izquierdo, derecho, token):
        if izquierdo is None or derecho is None:
            return None

        if (
            izquierdo not in ("i32", "f64")
            or derecho not in ("i32", "f64")
        ):
            self.reportar(
                token,
                f"El operador '{token.text}' requiere números."
            )
            return None

        if izquierdo != derecho:
            self.reportar(
                token,
                f"No se puede operar {izquierdo} con {derecho} "
                "sin una conversión explícita."
            )
            return None

        # Regla inicial de RustiQ: módulo solo entre enteros.
        if token.text == "%" and izquierdo != "i32":
            self.reportar(
                token,
                "El operador '%' solo admite i32."
            )
            return None

        return izquierdo

    def visitAdditive(self, ctx):
        operandos = ctx.multiplicative()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            operador = ctx.getChild(2 * indice - 1).getSymbol()
            derecho = self.visit(operandos[indice])
            tipo = self.comprobar_operacion(
                tipo, derecho, operador
            )

        return self.guardar_tipo(ctx, tipo)

    def visitMultiplicative(self, ctx):
        operandos = ctx.unary()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            operador = ctx.getChild(2 * indice - 1).getSymbol()
            derecho = self.visit(operandos[indice])
            tipo = self.comprobar_operacion(
                tipo, derecho, operador
            )

        return self.guardar_tipo(ctx, tipo)

    def visitUnary(self, ctx):
        tipo = self.visit(ctx.primary())

        if (
            ctx.MINUS() is not None
            and tipo is not None
            and tipo not in ("i32", "f64")
        ):
            self.reportar(
                ctx.MINUS().getSymbol(),
                "El signo negativo requiere un número."
            )
            tipo = None

        return self.guardar_tipo(ctx, tipo)

    def visitPrimary(self, ctx):
        if ctx.INT() is not None:
            tipo = "i32"

        elif ctx.FLOAT() is not None:
            tipo = "f64"

        elif ctx.TRUE() is not None or ctx.FALSE() is not None:
            tipo = "bool"

        elif ctx.IDENT() is not None:
            token = ctx.IDENT().getSymbol()
            variable = self.buscar_variable(token.text)

            if variable is None:
                self.reportar(
                    token,
                    f"La variable '{token.text}' no está declarada."
                )
                tipo = None

            elif not variable["inicializada"]:
                self.reportar(
                    token,
                    f"La variable '{token.text}' se usa "
                    "antes de inicializarla."
                )
                tipo = None

            else:
                tipo = variable["tipo"]

        else:
            tipo = self.visit(ctx.expression())

        return self.guardar_tipo(ctx, tipo)