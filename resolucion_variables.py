from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser


class ResolucionVariables(RustiQVisitor):
    """
    Vincula declaraciones y usos de variables.

    Debe ejecutarse después de un análisis semántico correcto.
    No comprueba errores: utiliza un programa ya validado.
    """

    def __init__(self, tipos_expresiones):
        super().__init__()

        # Tipos calculados por el análisis semántico.
        self.tipos_expresiones = tipos_expresiones

        # Pila de diccionarios: nombre -> identificador.
        self.ambitos = []

        # Identificador -> información de la variable.
        self.simbolos = {}

        # Nodo de declaración -> identificador.
        self.declaraciones = {}

        # Nodo de lectura o asignación -> identificador.
        self.referencias = {}

        self.funcion_actual = None
        self.siguiente_id = 0

    # =================================================
    # 1. HERRAMIENTAS DE APOYO
    # =================================================

    def obtener_tipo_declarado(self, ctx):
        nodo = ctx.getTypedRuleContext(
            RustiQParser.TypeContext, 0
        )
        return nodo.getText() if nodo is not None else None

    def buscar(self, nombre):
        # El ámbito interior tiene prioridad.
        for ambito in reversed(self.ambitos):
            if nombre in ambito:
                return ambito[nombre]

        # Si ocurre, hay una inconsistencia entre este recorrido
        # y el análisis semántico que ya validó el programa.
        raise RuntimeError(
            f"No se pudo resolver la variable '{nombre}'."
        )

    def registrar(self, ctx, tipo, es_parametro):
        token = ctx.IDENT().getSymbol()
        identificador = self.siguiente_id
        self.siguiente_id += 1

        self.simbolos[identificador] = {
            "nombre": token.text,
            "tipo": tipo,
            "mutable": ctx.MUT() is not None,
            "funcion": self.funcion_actual,
            "es_parametro": es_parametro,
            "linea": token.line,
            "columna": token.column + 1,
        }

        self.ambitos[-1][token.text] = identificador
        self.declaraciones[ctx] = identificador

    # =================================================
    # 2. FUNCIONES Y ÁMBITOS
    # =================================================

    def visitFunctionDecl(self, ctx):
        ambitos_anteriores = self.ambitos
        funcion_anterior = self.funcion_actual

        self.ambitos = [{}]
        self.funcion_actual = ctx.IDENT().getText()

        try:
            lista = ctx.parameterList()

            if lista is not None:
                for parametro in lista.parameter():
                    self.registrar(
                        parametro,
                        self.obtener_tipo_declarado(parametro),
                        es_parametro=True,
                    )

            # Parámetros y variables del cuerpo principal
            # comparten el mismo ámbito.
            for sentencia in ctx.block().statement():
                self.visit(sentencia)
        finally:
            self.ambitos = ambitos_anteriores
            self.funcion_actual = funcion_anterior

    def visitBlock(self, ctx):
        self.ambitos.append({})

        try:
            for sentencia in ctx.statement():
                self.visit(sentencia)
        finally:
            self.ambitos.pop()

    # =================================================
    # 3. DECLARACIONES
    # =================================================

    def visitLetDecl(self, ctx):
        expresion = ctx.expression()
        tipo = self.obtener_tipo_declarado(ctx)

        # El inicializador se analiza antes de registrar
        # la nueva variable, igual que en el semántico.
        if expresion is not None:
            self.visit(expresion)

            if tipo is None:
                tipo = self.tipos_expresiones[expresion]

        self.registrar(
            ctx,
            tipo,
            es_parametro=False,
        )

    # =================================================
    # 4. LECTURAS Y ASIGNACIONES
    # =================================================

    def visitAssignment(self, ctx):
        nombre = ctx.IDENT().getText()

        # Vincular el destino de la asignación.
        self.referencias[ctx] = self.buscar(nombre)

        # Vincular también las variables del valor asignado.
        self.visit(ctx.expression())

    def visitPrimary(self, ctx):
        if ctx.IDENT() is not None:
            nombre = ctx.IDENT().getText()
            self.referencias[ctx] = self.buscar(nombre)
        else:
            # Visitar paréntesis y llamadas, incluyendo
            # las variables utilizadas en sus argumentos.
            return self.visitChildren(ctx)