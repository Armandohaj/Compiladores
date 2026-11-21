# Resolución de identidades posterior a tipos. declaraciones y referencias vinculan nodos
# con IDs únicos; el sombreado no se resuelve mediante nombres en el backend.
"""Prepara identidades de símbolos para el backend después del semántico.

Dos declaraciones llamadas igual reciben identificadores diferentes.
Los mapas usan nodos del árbol original como claves para vincular lecturas,
destinos y declaraciones sin introducir otro árbol de representación.
"""
from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser
from tipos_compuestos import normalizar_tipo
from flujo_control import salidas_control

class ResolucionVariables(RustiQVisitor):
    """
    Vincula declaraciones y usos de variables y constantes.

    Se ejecuta únicamente después de un análisis semántico
    correcto y utiliza el mismo árbol de ANTLR.
    """

    def __init__(self, tipos_expresiones, valores_constantes=None, constantes_locales=None):
        """Prepara mapas vacíos para un recorrido de resolución independiente."""
        super().__init__()

        self.tipos_expresiones = tipos_expresiones
        self.constantes_locales = constantes_locales or {}

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
        """Usa la misma normalización del semántico para no entregar tipos distintos al backend."""
        nodo = ctx.getTypedRuleContext(RustiQParser.TypeContext, 0)
        return normalizar_tipo(nodo) if nodo is not None else None

    def buscar(self, nombre):
        """Busca el ID visible desde el ámbito interior. Si falla tras validar semántica, señala una inconsistencia interna."""
        for ambito in reversed(self.ambitos):
            if nombre in ambito:
                return ambito[nombre]

        raise RuntimeError(
            f"No se pudo resolver el identificador '{nombre}'."
        )

    def registrar(
        self, ctx, tipo, es_parametro=False, es_constante=False
    ):
        """Crea un ID único y registra nombre, tipo y ubicación; las constantes también guardan su valor calculado."""
        # nombre sirve para buscar en el ámbito; identificador distingue la declaración
        # exacta. El backend usa ese ID para no asignar dos variables sombreadas al mismo
        # almacenamiento.
        token = ctx.IDENT().getSymbol()
        # Ejemplo: dos bloques con let x reciben IDs diferentes. El generador
        # usa esos IDs para elegir el almacenamiento correcto, sin depender
        # del texto del nombre ni repetir la búsqueda de ámbitos.
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
            simbolo["valor"] = (self.constantes_locales[ctx] if ctx in self.constantes_locales
                                else self.valores_constantes[token.text])

        self.simbolos[identificador] = simbolo
        self.ambitos[-1][token.text] = identificador
        self.declaraciones[ctx] = identificador

    # =================================================
    # 2. PROGRAMA Y CONSTANTES GLOBALES
    # =================================================

    def visitProgram(self, ctx):
        """Registra primero todas las constantes y después vincula inicializadores y cuerpos de funciones."""
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
        """Comparte el ámbito global de constantes y crea un ámbito local para parámetros y variables de la función."""
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
                # La expresión final puede leer los parámetros
                # y las variables declaradas en el cuerpo.
            if ctx.block().expression() is not None:
                self.visit(ctx.block().expression())
        finally:
            self.ambitos = ambitos_anteriores
            self.funcion_actual = funcion_anterior

    def visitBlock(self, ctx):
        """Vincula los usos de variables dentro de todo el bloque."""
        self.ambitos.append({})

        try:
            # Registrar declaraciones y resolver las instrucciones.
            for sentencia in ctx.statement():
                self.visit(sentencia)

            # Resolver también las variables de la expresión final.
            # Todavía estamos dentro del ámbito del bloque.
            if ctx.expression() is not None:
                self.visit(ctx.expression())

        finally:
            # Las variables del bloque dejan de estar disponibles.
            self.ambitos.pop()

    # =================================================
    # 4. DECLARACIONES LOCALES
    # =================================================

    def visitConstLocalDecl(self, ctx):
        """Vincula el inicializador antes de introducir la constante de este ámbito."""
        # Se resuelven las lecturas del inicializador con los nombres anteriores antes de
        # registrar la nueva constante. El símbolo conserva es_constante y el valor ya
        # calculado.
        # El inicializador aún ve el ámbito anterior. Registrar primero el
        # nombre haría que un sombreado apuntara por error a sí mismo.
        self.visit(ctx.expression())
        self.registrar(ctx, self.obtener_tipo_declarado(ctx), es_constante=True)

    def visitLetDecl(self, ctx):
        """Resuelve el inicializador antes de registrar la variable."""
        expresion = ctx.expression()
        tipo = self.obtener_tipo_declarado(ctx)

        if expresion is not None:
            # Vincular primero las lecturas del inicializador.
            self.visit(expresion)

            # Coincide con el semántico: si hay un salto
            # incondicional, no se crea esta declaración.
            if "normal" not in salidas_control(expresion):
                return

            if tipo is None:
                tipo = self.tipos_expresiones[expresion]

        self.registrar(ctx, tipo)

    # =================================================
    # 5. LECTURAS Y ASIGNACIONES
    # =================================================

    def visitAssignment(self, ctx):
        """Vincula el destino con su símbolo y recorre las variables leídas en índices y en el valor derecho."""
        if ctx.dereferenceTarget() is not None:
            destino = ctx.dereferenceTarget()
            identificador = self.buscar(destino.IDENT().getText())
            self.referencias[destino] = identificador
            self.referencias[ctx] = identificador
            self.visit(ctx.expression())
            return
        nombre = ctx.IDENT().getText()
        self.referencias[ctx] = self.buscar(nombre)
        # Un índice puede leer otras variables: datos[posicion] = valor.
        for acceso in ctx.indexAccess():
            self.visit(acceso.expression())
        self.visit(ctx.expression())

    def visitStructLiteral(self, ctx):
        # El nombre del tipo y los nombres de campo no son variables.
        # Sus expresiones sí pueden leer variables o constantes.
        """Recorre valores de campos; el nombre del tipo y los nombres de campos no son variables."""
        for campo in ctx.fieldInit():
            self.visit(campo.expression())

    def visitPrimary(self, ctx):
        """Vincula lecturas de identificadores; en otros valores sigue recorriendo hijos para encontrar lecturas interiores."""
        if ctx.IDENT() is not None:
            nombre = ctx.IDENT().getText()
            self.referencias[ctx] = self.buscar(nombre)
        else:
            return self.visitChildren(ctx)

    def visitMatchExpr(self, ctx):
        """Resuelve primero el valor y limita cada variable al brazo que la declara."""
        self.visit(ctx.expression())
        for brazo in ctx.matchArm():
            self.ambitos.append({})
            try:
                self.registrar_patron(brazo.pattern())
                self.visit(brazo.expression())
            finally:
                self.ambitos.pop()

    def registrar_patron(self, ctx):
        """Asigna identidades a receptores; los nombres de variantes no son variables."""
        if ctx.DOUBLE_COLON() is not None:
            lista = ctx.patternList()
            if lista is not None:
                for hijo in lista.pattern():
                    self.registrar_patron(hijo)
        elif ctx.LPAREN() is not None:
            for hijo in ctx.pattern():
                self.registrar_patron(hijo)
        elif ctx.IDENT():
            token = ctx.IDENT(0).getSymbol()
            identificador = self.siguiente_id
            self.siguiente_id += 1
            self.simbolos[identificador] = {
                "nombre": token.text, "tipo": self.tipos_expresiones[ctx],
                "mutable": False, "funcion": self.funcion_actual,
                "es_parametro": False, "es_constante": False,
                "linea": token.line, "columna": token.column + 1,
            }
            self.ambitos[-1][token.text] = identificador
            self.declaraciones[ctx] = identificador
