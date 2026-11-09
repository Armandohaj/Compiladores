from copy import deepcopy

from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser


class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
        super().__init__()
        self.ambitos = []
        self.errores = []
        self.tipo_retorno = None
        self.tipos_expresiones = {}

        # Cada entrada indica cuántos ámbitos existían
        # antes de entrar en el cuerpo de un ciclo.
        self.limites_ciclos = []

    # =================================================
    # 1. HERRAMIENTAS DE APOYO
    # =================================================

    def reportar(self, token, mensaje):
        self.errores.append({
            "fase": "semantico",
            "mensaje": mensaje,
            "linea": token.line,
            "columna": token.column + 1,
        })

    def obtener_tipo_declarado(self, ctx):
        nodo = ctx.getTypedRuleContext(
            RustiQParser.TypeContext, 0
        )
        return nodo.getText() if nodo is not None else None

    def guardar_tipo(self, ctx, tipo):
        self.tipos_expresiones[ctx] = tipo
        return tipo

    def buscar_variable_con_ambito(self, nombre):
        """Devuelve la variable y el índice de su ámbito."""
        for indice in range(len(self.ambitos) - 1, -1, -1):
            if nombre in self.ambitos[indice]:
                return self.ambitos[indice][nombre], indice

        return None, None

    def buscar_variable(self, nombre):
        variable, _ = self.buscar_variable_con_ambito(nombre)
        return variable

    # =================================================
    # 2. FUNCIONES Y RETORNOS
    # =================================================

    def visitFunctionDecl(self, ctx):
        anteriores = self.ambitos
        retorno_anterior = self.tipo_retorno
        ciclos_anteriores = self.limites_ciclos

        self.ambitos = []
        self.limites_ciclos = []
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
                    f"{self.tipo_retorno} en todos los caminos."
                )
        finally:
            self.ambitos = anteriores
            self.tipo_retorno = retorno_anterior
            self.limites_ciclos = ciclos_anteriores

    def bloque_garantiza_retorno(self, ctx):
        for sentencia in ctx.statement():
            if sentencia.returnStmt() is not None:
                return True

            # Un salto impide alcanzar las sentencias siguientes.
            if (
                sentencia.breakStmt() is not None
                or sentencia.continueStmt() is not None
            ):
                return False

            if sentencia.block() is not None:
                if self.bloque_garantiza_retorno(sentencia.block()):
                    return True

            if sentencia.ifStmt() is not None:
                if self.if_garantiza_retorno(sentencia.ifStmt()):
                    return True

            # Un while no garantiza retorno:
            # su cuerpo podría ejecutarse cero veces.

        return False

    def if_garantiza_retorno(self, ctx):
        if ctx.ELSE() is None:
            return False

        bloques = ctx.block()

        if not self.bloque_garantiza_retorno(bloques[0]):
            return False

        if ctx.ifStmt() is not None:
            return self.if_garantiza_retorno(ctx.ifStmt())

        return self.bloque_garantiza_retorno(bloques[1])

    def visitReturnStmt(self, ctx):
        expresion = ctx.expression()
        tipo = (
            self.visit(expresion)
            if expresion is not None
            else "unit"
        )

        if tipo is not None and tipo != self.tipo_retorno:
            self.reportar(
                ctx.RETURN().getSymbol(),
                "Retorno incompatible: "
                f"se esperaba {self.tipo_retorno}, "
                f"pero se recibió {tipo}."
            )

    # =================================================
    # 3. BLOQUES Y CONDICIONALES
    # =================================================

    def visitBlock(self, ctx):
        self.ambitos.append({})

        try:
            for sentencia in ctx.statement():
                self.visit(sentencia)
        finally:
            self.ambitos.pop()

    def visitIfStmt(self, ctx):
        tipo = self.visit(ctx.expression())

        if tipo is not None and tipo != "bool":
            self.reportar(
                ctx.IF().getSymbol(),
                "La condición del if debe ser bool."
            )

        # Las dos ramas parten del mismo estado.
        inicial = deepcopy(self.ambitos)
        bloques = ctx.block()

        self.ambitos = deepcopy(inicial)
        self.visit(bloques[0])
        estado_then = deepcopy(self.ambitos)
        retorna_then = self.bloque_garantiza_retorno(bloques[0])

        self.ambitos = deepcopy(inicial)
        retorna_else = False

        if ctx.ifStmt() is not None:
            self.visit(ctx.ifStmt())
            retorna_else = self.if_garantiza_retorno(ctx.ifStmt())
        elif ctx.ELSE() is not None:
            self.visit(bloques[1])
            retorna_else = self.bloque_garantiza_retorno(bloques[1])

        estado_else = deepcopy(self.ambitos)
        caminos = []

        if not retorna_then:
            caminos.append(estado_then)

        if not retorna_else:
            caminos.append(estado_else)

        self.ambitos = deepcopy(inicial)

        if not caminos:
            return

        for indice, ambito in enumerate(self.ambitos):
            for nombre, variable in ambito.items():
                estados = [
                    camino[indice][nombre]
                    for camino in caminos
                ]
                variable["inicializada"] = all(
                    estado["inicializada"] for estado in estados
                )
                variable["puede_inicializada"] = any(
                    estado["puede_inicializada"] for estado in estados
                )

    # =================================================
    # 4. CICLOS Y SALTOS
    # =================================================

    def visitWhileStmt(self, ctx):
        tipo = self.visit(ctx.expression())

        if tipo is not None and tipo != "bool":
            self.reportar(
                ctx.WHILE().getSymbol(),
                "La condición del while debe ser bool."
            )

        inicial = deepcopy(self.ambitos)
        self.limites_ciclos.append(len(self.ambitos))

        try:
            self.visit(ctx.block())
        finally:
            self.limites_ciclos.pop()

            # El ciclo podría no ejecutarse.
            # Conservamos el estado anterior para las variables externas.
            self.ambitos = inicial

    def visitBreakStmt(self, ctx):
        if not self.limites_ciclos:
            self.reportar(
                ctx.BREAK().getSymbol(),
                "'break' solo puede usarse dentro de un ciclo."
            )

    def visitContinueStmt(self, ctx):
        if not self.limites_ciclos:
            self.reportar(
                ctx.CONTINUE().getSymbol(),
                "'continue' solo puede usarse dentro de un ciclo."
            )

    # =================================================
    # 5. VARIABLES Y ASIGNACIONES
    # =================================================

    def visitLetDecl(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        ambito = self.ambitos[-1]
        declarado = self.obtener_tipo_declarado(ctx)
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

        if declarado is None and expresion is None:
            self.reportar(
                token,
                f"No se puede determinar el tipo de '{nombre}': "
                "indicá un tipo o un valor inicial."
            )

        if (
            declarado is not None
            and tipo_valor is not None
            and declarado != tipo_valor
        ):
            self.reportar(
                token,
                f"Tipos incompatibles en '{nombre}': "
                f"se esperaba {declarado}, "
                f"pero se recibió {tipo_valor}."
            )

        inicializada = (
            expresion is not None
            and tipo_valor is not None
            and len(self.errores) == errores_antes
        )

        ambito[nombre] = {
            "tipo": declarado or tipo_valor,
            "mutable": ctx.MUT() is not None,
            "inicializada": inicializada,
            "puede_inicializada": inicializada,
        }

    def visitAssignment(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        variable, indice_ambito = self.buscar_variable_con_ambito(
            nombre
        )

        errores_antes = len(self.errores)
        tipo_valor = self.visit(ctx.expression())

        if variable is None:
            self.reportar(
                token,
                f"La variable '{nombre}' no está declarada."
            )
            return

        if variable["puede_inicializada"] and not variable["mutable"]:
            self.reportar(
                token,
                f"No se puede modificar '{nombre}' "
                "porque no fue declarada con 'mut'."
            )
            return

        # Regla conservadora inicial:
        # asignar dentro de un ciclo a una variable externa exige mut,
        # porque esa asignación podría repetirse.
        if (
            not variable["mutable"]
            and self.limites_ciclos
            and indice_ambito < self.limites_ciclos[-1]
        ):
            self.reportar(
                token,
                f"La variable externa '{nombre}' debe declararse "
                "con 'mut' para asignarla dentro de un ciclo."
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
            variable["puede_inicializada"] = True

    # =================================================
    # 6. EXPRESIONES LÓGICAS
    # =================================================

    def visitExpression(self, ctx):
        return self.guardar_tipo(ctx, self.visit(ctx.logicalOr()))

    def comprobar_logica(self, izquierdo, derecho, token):
        if izquierdo is None or derecho is None:
            return None

        if izquierdo != "bool" or derecho != "bool":
            self.reportar(
                token,
                f"El operador '{token.text}' requiere "
                "dos valores bool."
            )
            return None

        return "bool"

    def visitLogicalOr(self, ctx):
        operandos = ctx.logicalAnd()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            derecho = self.visit(operandos[indice])
            tipo = self.comprobar_logica(
                tipo, derecho, ctx.OR(indice - 1).getSymbol()
            )

        return self.guardar_tipo(ctx, tipo)

    def visitLogicalAnd(self, ctx):
        operandos = ctx.comparison()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            derecho = self.visit(operandos[indice])
            tipo = self.comprobar_logica(
                tipo, derecho, ctx.AND(indice - 1).getSymbol()
            )

        return self.guardar_tipo(ctx, tipo)

    # =================================================
    # 7. COMPARACIONES
    # =================================================

    def visitComparison(self, ctx):
        operandos = ctx.additive()
        izquierdo = self.visit(operandos[0])

        if ctx.relOp() is None:
            return self.guardar_tipo(ctx, izquierdo)

        derecho = self.visit(operandos[1])
        operador = ctx.relOp().start

        if izquierdo is None or derecho is None:
            return self.guardar_tipo(ctx, None)

        if izquierdo != derecho:
            self.reportar(
                operador,
                "Comparación incompatible entre "
                f"{izquierdo} y {derecho}."
            )
            return self.guardar_tipo(ctx, None)

        if (
            operador.text not in ("==", "!=")
            and izquierdo not in ("i32", "f64")
        ):
            self.reportar(
                operador,
                f"El operador '{operador.text}' "
                "requiere valores numéricos."
            )
            return self.guardar_tipo(ctx, None)

        return self.guardar_tipo(ctx, "bool")

    # =================================================
    # 8. OPERACIONES ARITMÉTICAS
    # =================================================

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

    # =================================================
    # 9. OPERADORES UNARIOS Y VALORES
    # =================================================

    def visitUnary(self, ctx):
        tipo = self.visit(ctx.primary())

        if tipo is not None:
            if (
                ctx.MINUS() is not None
                and tipo not in ("i32", "f64")
            ):
                self.reportar(
                    ctx.MINUS().getSymbol(),
                    "El signo negativo requiere un número."
                )
                tipo = None

            elif ctx.NOT() is not None and tipo != "bool":
                self.reportar(
                    ctx.NOT().getSymbol(),
                    "El operador '!' requiere un valor bool."
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