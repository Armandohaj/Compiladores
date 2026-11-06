from generated.RustiQVisitor import RustiQVisitor


class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
        super().__init__()
        self.ambitos = []
        self.errores = []
        self.tipo_retorno = None

    def reportar(self, token, mensaje):
        self.errores.append({
            "fase": "semantico",
            "mensaje": mensaje,
            "linea": token.line,
            "columna": token.column + 1,
        })

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
            "i32" if ctx.I32() is not None else "unit"
        )

        try:
            self.visit(ctx.block())

            if (
                self.tipo_retorno == "i32"
                and not self.bloque_garantiza_retorno(ctx.block())
            ):
                self.reportar(
                    ctx.IDENT().getSymbol(),
                    "La función debe retornar un valor i32."
                )
        finally:
            self.ambitos = ambitos_anteriores
            self.tipo_retorno = retorno_anterior

    def bloque_garantiza_retorno(self, ctx):
        # Esta comprobación cubre nuestras sentencias actuales.
        # Se ampliará cuando agreguemos condiciones y ciclos.
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
        ambito_actual = self.ambitos[-1]

        if ctx.expression() is not None:
            self.visit(ctx.expression())

        if nombre in ambito_actual:
            self.reportar(
                token,
                f"La variable '{nombre}' ya fue declarada "
                "en este ámbito."
            )
            return

        ambito_actual[nombre] = {
            "mutable": ctx.MUT() is not None,
            "inicializada": ctx.expression() is not None,
        }

    def visitAssignment(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        variable = self.buscar_variable(nombre)

        self.visit(ctx.expression())

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

        variable["inicializada"] = True

    def visitReturnStmt(self, ctx):
        expresion = ctx.expression()
        token = ctx.RETURN().getSymbol()

        if expresion is not None:
            self.visit(expresion)

        if self.tipo_retorno == "i32" and expresion is None:
            self.reportar(
                token,
                "La función declara retorno i32, "
                "pero este return no devuelve un valor."
            )

        elif self.tipo_retorno == "unit" and expresion is not None:
            self.reportar(
                token,
                "La función no declara tipo de retorno, "
                "por lo que no puede retornar un entero."
            )

    def visitPrimary(self, ctx):
        if ctx.IDENT() is not None:
            token = ctx.IDENT().getSymbol()
            nombre = token.text
            variable = self.buscar_variable(nombre)

            if variable is None:
                self.reportar(
                    token,
                    f"La variable '{nombre}' no está declarada."
                )

            elif not variable["inicializada"]:
                self.reportar(
                    token,
                    f"La variable '{nombre}' se usa "
                    "antes de inicializarla."
                )

            return

        return self.visitChildren(ctx)