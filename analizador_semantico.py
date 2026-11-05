from generated.RustiQVisitor import RustiQVisitor


class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
        self.ambitos = []
        self.errores = []

    def reportar(self, token, mensaje):
        self.errores.append(
            f"Error semántico — "
            f"Línea {token.line}, "
            f"columna {token.column + 1}: {mensaje}"
        )

    def buscar_variable(self, nombre):
        # Buscar desde el ámbito más cercano al más externo.
        for ambito in reversed(self.ambitos):
            if nombre in ambito:
                return ambito[nombre]

        return None

    def visitFunctionDecl(self, ctx):
        # Cada función se analiza con sus propios ámbitos.
        anteriores = self.ambitos
        self.ambitos = []

        self.visit(ctx.block())

        self.ambitos = anteriores

    def visitBlock(self, ctx):
        # Entrar en un ámbito.
        self.ambitos.append({})

        for sentencia in ctx.statement():
            self.visit(sentencia)

        # Salir del ámbito.
        self.ambitos.pop()

    def visitLetDecl(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        ambito_actual = self.ambitos[-1]

        # Analizar el inicializador antes de declarar la variable.
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

        # Comprobar también las variables usadas a la derecha.
        self.visit(ctx.expression())

        if variable is None:
            self.reportar(
                token,
                f"La variable '{nombre}' no está declarada."
            )
            return

        # Una variable sin inicializar puede recibir su primer valor.
        if variable["inicializada"] and not variable["mutable"]:
            self.reportar(
                token,
                f"No se puede modificar '{nombre}' "
                "porque no fue declarada con 'mut'."
            )
            return

        variable["inicializada"] = True

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

        # Permite recorrer expresiones entre paréntesis.
        return self.visitChildren(ctx)