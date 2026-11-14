from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser
from tipos_compuestos import normalizar_tipo


class ResolucionVariables(RustiQVisitor):
    """
    Vincula declaraciones y usos de variables y constantes.

    Se ejecuta únicamente después de un análisis semántico
    correcto y utiliza el mismo árbol de ANTLR.
    """

    def __init__(self, tipos_expresiones, valores_constantes=None):
        super().__init__()

        self.tipos_expresiones = tipos_expresiones

        # Nombre de constante -> valor calculado.
        self.valores_constantes = (
            valores_constantes
            if valores_constantes is not None
            else {}
        )

        # Ámbito global: nombre de constante -> identificador.
        self.globales = {}

        # Pila de ámbitos locales y globales.
        self.ambitos = []

        # Identificador -> información para el backend.
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
        nodo = ctx.getTypedRuleContext(RustiQParser.TypeContext, 0)
        return normalizar_tipo(nodo) if nodo is not None else None

    def buscar(self, nombre):
        for ambito in reversed(self.ambitos):
            if nombre in ambito:
                return ambito[nombre]

        raise RuntimeError(
            f"No se pudo resolver el identificador '{nombre}'."
        )

    def registrar(
        self, ctx, tipo, es_parametro=False, es_constante=False
    ):
        token = ctx.IDENT().getSymbol()
        identificador = self.siguiente_id
        self.siguiente_id += 1

        # Las constantes no tienen la opción mut en su gramática.
        mutable = (
            False
            if es_constante
            else ctx.MUT() is not None
        )

        simbolo = {
            "nombre": token.text,
            "tipo": tipo,
            "mutable": mutable,
            "funcion": self.funcion_actual,
            "es_parametro": es_parametro,
            "es_constante": es_constante,
            "linea": token.line,
            "columna": token.column + 1,
        }

        if es_constante:
            # Una constante incluye su valor ya calculado.
            simbolo["valor"] = self.valores_constantes[token.text]

        self.simbolos[identificador] = simbolo
        self.ambitos[-1][token.text] = identificador
        self.declaraciones[ctx] = identificador

    # =================================================
    # 2. PROGRAMA Y CONSTANTES GLOBALES
    # =================================================

    def visitProgram(self, ctx):
        self.ambitos = [self.globales]

        # Registrar todas las constantes antes de recorrer
        # sus expresiones, permitiendo referencias adelantadas.
        for constante in ctx.constDecl():
            self.registrar(
                constante,
                self.obtener_tipo_declarado(constante),
                es_constante=True,
            )

        # Vincular las referencias entre constantes.
        for constante in ctx.constDecl():
            self.visit(constante.expression())

        # Recorrer los cuerpos de las funciones.
        for funcion in ctx.functionDecl():
            self.visit(funcion)

    # =================================================
    # 3. FUNCIONES Y ÁMBITOS
    # =================================================

    def visitFunctionDecl(self, ctx):
        ambitos_anteriores = self.ambitos
        funcion_anterior = self.funcion_actual

        # El ámbito local tiene prioridad sobre el global.
        self.ambitos = [self.globales, {}]
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
            # comparten el mismo ámbito local.
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
    # 4. DECLARACIONES LOCALES
    # =================================================

    def visitLetDecl(self, ctx):
        expresion = ctx.expression()
        tipo = self.obtener_tipo_declarado(ctx)

        # Resolver el inicializador antes de registrar
        # la nueva variable.
        if expresion is not None:
            self.visit(expresion)

            if tipo is None:
                tipo = self.tipos_expresiones[expresion]

        self.registrar(ctx, tipo)

    # =================================================
    # 5. LECTURAS Y ASIGNACIONES
    # =================================================

    def visitAssignment(self, ctx):
        nombre = ctx.IDENT().getText()
        self.referencias[ctx] = self.buscar(nombre)
        # Un índice puede leer otras variables: datos[posicion] = valor.
        for acceso in ctx.indexAccess():
            self.visit(acceso.expression())
        self.visit(ctx.expression())

    def visitPrimary(self, ctx):
        if ctx.IDENT() is not None:
            nombre = ctx.IDENT().getText()
            self.referencias[ctx] = self.buscar(nombre)
        else:
            return self.visitChildren(ctx)