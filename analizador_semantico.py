"""Análisis semántico: comprueba qué significa un programa ya bien formado.

ANTLR entrega el árbol; este visitor lo recorre y calcula tipos, busca
identificadores, controla ámbitos, mutabilidad e inicialización y comprueba
retornos. Los errores son datos estructurados, no mensajes impresos.
No ejecuta el programa RustiQ ni genera WebAssembly.
"""
from copy import copy, deepcopy
from semantica_match import analizar_match
from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser
from gestor_constantes import GestorConstantes
from gestor_estructuras import GestorEstructuras
from tipos_compuestos import (
    normalizar_tipo, separar_tipo_tupla, accesos_lectura, accesos_escritura,
)
from gestor_enumeraciones import GestorEnumeraciones
from flujo_control import salidas_control
from tipos_referencias import separar_referencia, identificador_simple

class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
        """Prepara el estado de un análisis independiente. No reutilizar símbolos entre programas."""
        super().__init__()

        # Pila de ámbitos: cada diccionario contiene variables.
        self.ambitos = []

        # Errores encontrados durante el análisis.
        self.errores = []

        # Tipo que debe devolver la función actual.
        self.tipo_retorno = None

        # Tipo calculado para cada nodo de expresión.
        self.tipos_expresiones = {}

        # Tipo contextual de arreglos y tuplas, incluidos arreglos vacíos.
        # Las claves son nodos del mismo árbol, sin crear un AST adicional.
        self.tipos_esperados = {}

        # Firmas de funciones: parámetros y tipo de retorno.
        self.funciones = {}

        # Reutilizamos la validación de firmas de las funciones normales.
        # Este registro interno no altera el mapa público de funciones del usuario.
        self.incorporadas = {
            "read": {"parametros": [], "retorno": "i32"},
            "print": {"parametros": ["i32"], "retorno": "unit"},
        }
        # El backend identifica cada operación en el mismo árbol de ANTLR.
        self.llamadas_incorporadas = {}

        # Nombre de estructura -> campos y sus tipos.
        self.estructuras = {}

        # Cantidad de ámbitos existentes antes de cada ciclo.
        self.limites_ciclos = []

    # =================================================
    # 1. HERRAMIENTAS DE APOYO
    # =================================================

    def reportar(self, token, mensaje):
        """Agrega un diagnóstico semántico. Convierte la columna de ANTLR (base cero) a base uno."""
        self.errores.append({
            "fase": "semantico",
            "mensaje": mensaje,
            "linea": token.line,
            "columna": token.column + 1,
        })

    def obtener_tipo_declarado(self, ctx):
        """Lee la anotación type del nodo; devuelve su nombre canónico o None si se omitió."""
        nodo = ctx.getTypedRuleContext(RustiQParser.TypeContext, 0)
        return self.normalizar_tipo(nodo) if nodo is not None else None

    def normalizar_tipo(self, nodo):
        """Unifica representaciones de tipos compuestos y tamaños, para compararlos como cadenas."""
        return normalizar_tipo(nodo)

    def visitar_con_tipo(self, ctx, esperado=None):
        """Propaga el contexto a literales, bloques y match que producen el valor.

        No lo propaga a operandos, índices ni argumentos de llamadas: allí
        el tipo esperado se determina por las reglas propias de cada operación.
        """
        if esperado is not None:
            nodo = ctx
            destinos = (
                RustiQParser.ArrayLiteralContext,
                RustiQParser.TupleLiteralContext,
                RustiQParser.BlockContext,
                RustiQParser.MatchExprContext,
            )
            while nodo is not None:
                if isinstance(nodo, destinos):
                    self.tipos_esperados[nodo] = esperado
                    break
                # Solo atravesar envoltorios de una expresión, no operaciones
                # con varios hijos. Esto también incluye los paréntesis.
                if isinstance(nodo, RustiQParser.PrimaryContext):
                    if nodo.expression() is not None:
                        nodo = nodo.expression()
                    elif nodo.getChildCount() == 1 and hasattr(nodo.getChild(0), "getChildren"):
                        nodo = nodo.getChild(0)
                    else:
                        break
                elif nodo.getChildCount() == 1 and hasattr(nodo.getChild(0), "getChildren"):
                    nodo = nodo.getChild(0)
                else:
                    break
        return self.visit(ctx)

    def guardar_tipo(self, ctx, tipo):
        """Asocia un nodo con su tipo y devuelve ese mismo tipo. None representa un error previo."""
        self.tipos_expresiones[ctx] = tipo
        return tipo

    def buscar_variable_con_ambito(self, nombre):
        # Primero buscar variables y parámetros locales.
        """Busca desde el bloque interior hacia afuera; después consulta constantes globales. Devuelve símbolo e índice de ámbito."""
        for indice in range(len(self.ambitos) - 1, -1, -1):
            if nombre in self.ambitos[indice]:
                return self.ambitos[indice][nombre], indice

        # Si no existe una variable local, buscar una constante.
        constantes = getattr(self, "constantes", {})

        if nombre in constantes:
            # -1 identifica el nivel global.
            # Las constantes ya están inicializadas y son inmutables.
            return constantes[nombre], -1

        return None, None

    def buscar_variable(self, nombre):
        """Devuelve los datos del identificador visible, o None si no fue declarado."""
        variable, _ = self.buscar_variable_con_ambito(nombre)
        return variable

    def obtener_parametros(self, ctx):
        """Devuelve nodos de parámetros; una función sin lista produce una lista vacía."""
        lista = ctx.parameterList()
        return lista.parameter() if lista is not None else []

    # =================================================
    # 2. REGISTRO DE FUNCIONES
    # =================================================

    def visitProgram(self, ctx):
        """
        Registra las declaraciones globales antes de revisar cuerpos.

        Orden:
        1. Enumeraciones.
        2. Estructuras y sus tipos.
        3. Firmas de funciones.
        4. Constantes.
        5. Cuerpos de funciones.
        """

        # Conocer primero los enums permite utilizarlos
        # en campos de estructuras y firmas de funciones.
        gestor_enumeraciones = GestorEnumeraciones(self)
        self.enumeraciones = gestor_enumeraciones.registrar(ctx)

        # Registrar estructuras antes de validar los tipos
        # permite referencias a estructuras declaradas después.
        gestor_estructuras = GestorEstructuras(self)
        self.estructuras = gestor_estructuras.registrar(ctx)
        gestor_estructuras.validar(ctx)

        # Registrar todas las firmas antes de visitar cuerpos.
        # Esto permite llamadas adelantadas y recursión.
        for funcion in ctx.functionDecl():
            token = funcion.IDENT().getSymbol()
            nombre = token.text

            if self.nombre_incorporado(token):
                continue

            if nombre in self.funciones:
                self.reportar(
                    token,
                    f"La función '{nombre}' ya fue declarada."
                )
                continue

            self.funciones[nombre] = {
                "parametros": [
                    self.obtener_tipo_declarado(parametro)
                    for parametro in self.obtener_parametros(funcion)
                ],
                "retorno": (
                    self.obtener_tipo_declarado(funcion) or "unit"
                ),
            }

        # Registrar, comprobar y calcular constantes.
        gestor_constantes = GestorConstantes(self)
        gestor_constantes.registrar(ctx.constDecl())

        self.constantes = gestor_constantes.simbolos

        gestor_constantes.validar_y_calcular()
        self.valores_constantes = gestor_constantes.valores

        # Primera versión acotada: no se almacenan referencias en compuestos,
        # ni se retornan referencias. Evita prometer vidas útiles no comprobadas.
        for funcion in ctx.functionDecl():
            if '&' in (self.obtener_tipo_declarado(funcion) or ''):
                self.reportar(funcion.start, "Esta versión no admite devolver referencias.")
        for constante in ctx.constDecl():
            if '&' in (self.obtener_tipo_declarado(constante) or ''):
                self.reportar(constante.start, "Las constantes globales no admiten referencias.")
        for declaracion in ctx.structDecl() + ctx.enumDecl():
            for nodo in gestor_estructuras.recorrer(declaracion):
                if isinstance(nodo, RustiQParser.TypeContext) and nodo.AMP() is not None:
                    self.reportar(nodo.start, "No se admiten referencias almacenadas en estructuras o enums.")
        for nodo in gestor_estructuras.recorrer(ctx):
            if isinstance(nodo, RustiQParser.TypeContext) and nodo.AMP() is not None:
                interior = self.normalizar_tipo(nodo.getTypedRuleContext(RustiQParser.TypeContext, 0))
                if '&' in interior:
                    self.reportar(nodo.start, "Las referencias anidadas no se admiten en esta versión.")
                padre = nodo.parentCtx
                if isinstance(padre, RustiQParser.TypeContext) and padre.AMP() is None:
                    self.reportar(nodo.start, "No se admiten referencias dentro de arreglos o tuplas.")

        # Con los registros disponibles, revisar cada función.
        for funcion in ctx.functionDecl():
            self.visit(funcion)

    # =================================================
    # 3. CUERPOS DE FUNCIONES Y PARÁMETROS
    # =================================================
    def visitFunctionDecl(self, ctx):
        """Analiza parámetros, instrucciones y retorno de una función."""
        anteriores = self.ambitos
        retorno_anterior = self.tipo_retorno
        ciclos_anteriores = self.limites_ciclos

        # Cada función tiene sus propias variables y ciclos.
        # Los parámetros comparten ámbito con el cuerpo principal.
        self.ambitos = [{}]
        self.limites_ciclos = []
        self.tipo_retorno = (
            self.obtener_tipo_declarado(ctx) or "unit"
        )

        try:
            for parametro in self.obtener_parametros(ctx):
                token = parametro.IDENT().getSymbol()
                nombre = token.text

                # read y print no pueden usarse como parámetros.
                if self.nombre_incorporado(token):
                    continue

                if nombre in self.ambitos[-1]:
                    self.reportar(
                        token,
                        f"El parámetro '{nombre}' ya fue declarado."
                    )
                    continue

                # Los parámetros reciben un valor al llamar la función.
                self.ambitos[-1][nombre] = {
                    "tipo": self.obtener_tipo_declarado(parametro),
                    "mutable": parametro.MUT() is not None,
                    "inicializada": True,
                    "puede_inicializada": True,
                }

            # No llamamos a visitBlock porque crearía otro ámbito
            # entre los parámetros y las variables del cuerpo.
            for sentencia in ctx.block().statement():
                self.visit(sentencia)

            expresion_final = ctx.block().expression()
            tipo_final = "unit"

            if expresion_final is not None:
                # La expresión final funciona como retorno implícito.
                # El tipo esperado también permite analizar literales
                # compuestos que necesitan contexto, como un arreglo vacío.
                tipo_final = self.visitar_con_tipo(
                    expresion_final,
                    self.tipo_retorno,
                )

                if (
                    tipo_final is not None
                    and tipo_final != self.tipo_retorno
                    and "normal" in salidas_control(expresion_final)
                ):
                    self.reportar(
                        expresion_final.start,
                        "Retorno implícito incompatible: "
                        f"se esperaba {self.tipo_retorno}, "
                        f"pero se recibió {tipo_final}.",
                    )

            # Registrar el tipo de la expresión final del cuerpo.
            self.guardar_tipo(ctx.block(), tipo_final)

            # Sin expresión final, seguimos exigiendo retornos
            # explícitos en todos los caminos de una función con valor.
            if (
                self.tipo_retorno != "unit"
                and expresion_final is None
                and not self.bloque_garantiza_retorno(ctx.block())
            ):
                self.reportar(
                    ctx.IDENT().getSymbol(),
                    "La función debe retornar un valor "
                    f"{self.tipo_retorno} en todos los caminos."
                )

        finally:
            # Restaurar el contexto que existía antes de esta función.
            self.ambitos = anteriores
            self.tipo_retorno = retorno_anterior
            self.limites_ciclos = ciclos_anteriores

    # =================================================
    # 4. LLAMADAS A FUNCIONES
    # =================================================

    def nombre_incorporado(self, token):
        """Impide que declaraciones del usuario oculten las operaciones de E/S."""
        if token.text not in self.incorporadas:
            return False
        self.reportar(token, f"El nombre '{token.text}' está reservado para una función incorporada.")
        return True

    def visitFunctionCall(self, ctx):
        """Comprueba existencia, cantidad y tipos de argumentos; devuelve el tipo de retorno. Visita argumentos aunque haya otros errores."""
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        lista = ctx.argumentList()

        argumentos = (
            lista.expression() if lista is not None else []
        )

        # Revisamos todos los argumentos, aunque la función
        # no exista, para detectar errores dentro de ellos.
        tipos_esperados = self.funciones.get(nombre, self.incorporadas.get(nombre, {})).get("parametros", [])
        tipos = [
            self.visitar_con_tipo(
                argumento,
                tipos_esperados[indice] if indice < len(tipos_esperados) else None,
            )
            for indice, argumento in enumerate(argumentos)
        ]

        # Una variable local con este nombre oculta la función.
        if self.buscar_variable(nombre) is not None:
            self.reportar(
                token,
                f"'{nombre}' es una variable y no puede "
                "llamarse como función."
            )
            return self.guardar_tipo(ctx, None)

        funcion = self.funciones.get(nombre, self.incorporadas.get(nombre))

        if funcion is None:
            self.reportar(
                token,
                f"La función '{nombre}' no está declarada."
            )
            return self.guardar_tipo(ctx, None)

        esperados = funcion["parametros"]
        llamada_valida = True

        if len(argumentos) != len(esperados):
            self.reportar(
                token,
                f"La función '{nombre}' espera "
                f"{len(esperados)} argumentos, pero recibió "
                f"{len(argumentos)}."
            )
            llamada_valida = False

        for indice, (recibido, esperado) in enumerate(
            zip(tipos, esperados), start=1
        ):
            if recibido is None:
                llamada_valida = False
            elif (
                    "normal" in salidas_control(argumentos[indice - 1])
                    and recibido != esperado
                ):
                self.reportar(
                    argumentos[indice - 1].start,
                    f"Argumento {indice} de '{nombre}': "
                    f"se esperaba {esperado}, "
                    f"pero se recibió {recibido}."
                )
                llamada_valida = False

        # print no produce un valor. Solo se permite esta llamada
        # como sentencia directa, nunca como argumento, retorno o inicializador.
        if (
                nombre in self.incorporadas
                and funcion["retorno"] == "unit"
                and "normal" in salidas_control(ctx)
                and not isinstance(
                    ctx.parentCtx,
                    RustiQParser.StatementContext,
                )
            ):
            self.reportar(token, "Una función unit no puede utilizarse como valor; usala como instrucción independiente.")
            llamada_valida = False

        if llamada_valida and nombre in self.incorporadas:
            self.llamadas_incorporadas[ctx] = nombre

        tipo = funcion["retorno"] if llamada_valida else None
        return self.guardar_tipo(ctx, tipo)

    # =================================================
    # 5. RETORNOS
    # =================================================

    def bloque_garantiza_retorno(self, ctx):
        """Comprueba que todos los caminos terminen con return."""
        # No basta encontrar un return: no debe existir otro camino
        # que continúe normalmente, haga break o haga continue.
        return salidas_control(ctx) == {"return"}
    def if_garantiza_retorno(self, ctx):
        """Exige else y retorno garantizado en ambas ramas, incluyendo cadenas else if."""
        if ctx.ELSE() is None:
            return False

        bloques = ctx.block()

        if not self.bloque_garantiza_retorno(bloques[0]):
            return False

        if ctx.ifStmt() is not None:
            return self.if_garantiza_retorno(ctx.ifStmt())

        return self.bloque_garantiza_retorno(bloques[1])

    def visitReturnStmt(self, ctx):
        """Comprueba el valor retornado si su evaluación termina normalmente."""
        expresion = ctx.expression()

        tipo = (
            self.visitar_con_tipo(expresion, self.tipo_retorno)
            if expresion is not None
            else "unit"
        )

        # Una expresión puede contener otro return o un salto.
        # Solo comparamos el valor si llega hasta este return exterior.
        continua = "normal" in salidas_control(expresion)

        if (
            continua
            and tipo is not None
            and tipo != self.tipo_retorno
        ):
            self.reportar(
                ctx.RETURN().getSymbol(),
                "Retorno incompatible: "
                f"se esperaba {self.tipo_retorno}, "
                f"pero se recibió {tipo}."
            )

    # =================================================
    # 6. BLOQUES Y CONDICIONALES
    # =================================================

    def visitBlock(self, ctx):
        """Analiza el bloque y obtiene el tipo de su expresión final."""
        self.ambitos.append({})

        try:
            # Primero analizamos las instrucciones.
            # Las variables declaradas aquí siguen visibles
            # mientras analizamos la expresión final.
            for sentencia in ctx.statement():
                self.visit(sentencia)

            expresion = ctx.expression()

            # Sin expresión final, el bloque no produce un valor.
            tipo = (
                self.visitar_con_tipo(expresion, self.tipos_esperados.get(ctx))
                if expresion is not None
                else "unit"
            )

            # Guardamos el tipo del bloque para el backend.
            return self.guardar_tipo(ctx, tipo)

        finally:
            # Al salir, desaparecen las variables locales.
            # Esto también ocurre si se produce una excepción.
            self.ambitos.pop()

    def visitIfStmt(self, ctx):
        """Analiza ambas ramas desde copias del mismo estado. Una variable solo queda inicializada si lo está en todos los caminos que continúan."""
        tipo = self.visit(ctx.expression())

        if (
                tipo is not None
                and tipo != "bool"
                and "normal" in salidas_control(ctx.expression())
        ):
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

        # Una variable está definitivamente inicializada
        # si lo está en todos los caminos que continúan.
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
    # 7. CICLOS Y SALTOS
    # =================================================

    def visitWhileStmt(self, ctx):
        """Exige condición bool y analiza el cuerpo en contexto de ciclo. Restaura inicialización externa porque puede ejecutarse cero veces."""
        tipo = self.visit(ctx.expression())

        if (
                tipo is not None
                and tipo != "bool"
                and "normal" in salidas_control(ctx.expression())
        ):
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

            # El cuerpo podría no ejecutarse.
            self.ambitos = inicial

    def visitLoopStmt(self, ctx):
        # Guardar el estado de las variables externas.
        """Habilita break y continue dentro del cuerpo. La inicialización al salir sigue siendo conservadora hasta modelar todos los caminos de break."""
        inicial = deepcopy(self.ambitos)

        # Registrar que estamos dentro de un ciclo.
        # Así se permiten break y continue en su cuerpo.
        self.limites_ciclos.append(len(self.ambitos))

        try:
            self.visit(ctx.block())
        finally:
            self.limites_ciclos.pop()

            # Por ahora conservamos el estado anterior.
            # Determinar qué variables quedan inicializadas
            # al salir requiere analizar los caminos de break.
            self.ambitos = inicial

    def visitBreakStmt(self, ctx):
        """Rechaza break si no existe un ciclo envolvente."""
        if not self.limites_ciclos:
            self.reportar(
                ctx.BREAK().getSymbol(),
                "'break' solo puede usarse dentro de un ciclo."
            )

    def visitContinueStmt(self, ctx):
        """Rechaza continue si no existe un ciclo envolvente."""
        if not self.limites_ciclos:
            self.reportar(
                ctx.CONTINUE().getSymbol(),
                "'continue' solo puede usarse dentro de un ciclo."
            )

    # =================================================
    # 8. VARIABLES Y ASIGNACIONES
    # =================================================

    def visitLetDecl(self, ctx):
        """Analiza el valor antes de registrar el nombre, infiere o comprueba el tipo y registra mutabilidad e inicialización."""
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        if self.nombre_incorporado(token):
            return
        ambito = self.ambitos[-1]
        declarado = self.obtener_tipo_declarado(ctx)
        expresion = ctx.expression()

        errores_antes = len(self.errores)
        tipo_valor = (
            self.visitar_con_tipo(expresion, declarado)
            if expresion is not None
            else None
        )
        # El inicializador puede contener visitantes que sustituyan
        # los mapas de ámbitos. Usamos el que sigue vigente.
        ambito = self.ambitos[-1]
        if nombre in ambito:
            self.reportar(
                token,
                f"La variable '{nombre}' ya fue declarada "
                "en este ámbito."
            )
            return

        # Si el inicializador termina mediante un salto,
        # nunca se llega a crear la variable.
        # No inventamos un tipo para un valor que no existe.
        if (
            expresion is not None
            and "normal" not in salidas_control(expresion)
        ):
            return
        if declarado is None and expresion is None:
            self.reportar(
                token,
                f"No se puede determinar el tipo de '{nombre}': "
                "indicá un tipo o un valor inicial."
            )

        # unit representa la ausencia de un valor.
        # Por ahora no es un tipo admitido para variables.
        if tipo_valor == "unit":
            self.reportar(
                token,
                f"No se puede inicializar '{nombre}' con "
                "una función que no devuelve un valor."
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
            "tipo": (
                declarado
                or (tipo_valor if tipo_valor != "unit" else None)
            ),
            "mutable": ctx.MUT() is not None,
            "inicializada": inicializada,
            "puede_inicializada": inicializada,
        }

    def visitBorrowExpr(self, ctx):
        """Comprueba tipo y mutabilidad; los conflictos activos se revisan luego."""
        tipo = self.visit(ctx.unary())
        origen = identificador_simple(ctx.unary())
        if origen is None:
            self.reportar(ctx.start, "Solo se permite prestar una variable completa; no campos ni temporales.")
            return self.guardar_tipo(ctx, None)
        variable = self.buscar_variable(origen.IDENT().getText())
        if tipo is None or variable is None:
            return self.guardar_tipo(ctx, None)
        if separar_referencia(tipo) is not None:
            self.reportar(ctx.start, "Las referencias anidadas y los représtamos no se admiten todavía.")
            return self.guardar_tipo(ctx, None)
        if variable.get('es_constante'):
            self.reportar(ctx.start, "Esta versión solo presta variables, no constantes globales.")
            return self.guardar_tipo(ctx, None)
        mutable = ctx.MUT() is not None
        if mutable and not variable['mutable']:
            self.reportar(ctx.start, "Un préstamo mutable requiere una variable declarada con mut.")
            return self.guardar_tipo(ctx, None)
        return self.guardar_tipo(ctx, ('&mut ' if mutable else '&') + tipo)

    def visitDereferenceExpr(self, ctx):
        """Obtiene el tipo del valor apuntado, conservando el nodo del operando."""
        referencia = separar_referencia(self.visit(ctx.unary()))
        if referencia is None:
            self.reportar(ctx.start, "La desreferenciación requiere un tipo de referencia.")
            return self.guardar_tipo(ctx, None)
        return self.guardar_tipo(ctx, referencia[1])

    def visitar_escritura_referencia(self, ctx):
        """Permite escribir *r cuando r tiene tipo &mut T; r no requiere let mut."""
        destino = ctx.dereferenceTarget()
        token = destino.IDENT().getSymbol()
        variable = self.buscar_variable(token.text)
        referencia = separar_referencia(variable['tipo']) if variable else None
        if referencia is None:
            self.reportar(token, "La escritura desreferenciada requiere una referencia.")
            self.visit(ctx.expression())
            return
        mutable, interior = referencia
        recibido = self.visitar_con_tipo(ctx.expression(), interior)
        self.guardar_tipo(destino, interior)
        self.guardar_tipo(ctx, interior)
        if not variable['inicializada']:
            self.reportar(token, f"La variable '{token.text}' se usa antes de inicializarla.")
        if not mutable:
            self.reportar(token, "No se puede escribir mediante una referencia inmutable.")
        if recibido is None or 'normal' not in salidas_control(ctx.expression()):
            return
        operador = ctx.assignmentOp().start
        if operador.text == '=':
            if recibido != interior:
                self.reportar(token, f"Asignación desreferenciada incompatible: se esperaba {interior}, pero se recibió {recibido}.")
        else:
            aritmetico = copy(operador)
            aritmetico.text = operador.text[:-1]
            self.comprobar_operacion(interior, recibido, aritmetico)

    def visitAssignment(self, ctx):
        # Conservar el comportamiento de las asignaciones simples.
        """Distingue reemplazo completo de escritura de un campo o elemento. Comprueba lectura previa en asignaciones compuestas."""
        if ctx.dereferenceTarget() is not None:
            return self.visitar_escritura_referencia(ctx)
        if ctx.indexAccess() or ctx.tupleAccess() or ctx.fieldAccess():
            return self.visitar_asignacion_elemento(ctx)

        token = ctx.IDENT().getSymbol()
        nombre = token.text

        variable, indice_ambito = self.buscar_variable_con_ambito(
            nombre
        )

        # El operador puede ser =, +=, -=, *= o /=.
        operador = ctx.assignmentOp().start
        es_compuesta = operador.text != "="

        errores_antes = len(self.errores)
        tipo_valor = self.visitar_con_tipo(
            ctx.expression(), variable["tipo"] if variable is not None else None
        )

        # El valor derecho puede contener bloques y condicionales.
        # Recuperamos el destino desde los ámbitos que siguen vigentes.
        variable, indice_ambito = self.buscar_variable_con_ambito(
            nombre
        )

        if variable is None:
            self.reportar(
                token,
                f"La variable '{nombre}' no está declarada."
            )
            return

        # Si evaluar el valor derecho provoca un salto,
        # no se llega a escribir ni a inicializar el destino.
        if "normal" not in salidas_control(ctx.expression()):
            # La asignación compuesta también necesita leer
            # el valor anterior de la variable.
            if es_compuesta and not variable["inicializada"]:
                self.reportar(
                    token,
                    f"La variable '{nombre}' se usa "
                    "antes de inicializarla."
                )
            return



        if es_compuesta:
            # Una asignación compuesta lee el valor anterior.
            # Por eso no sirve para inicializar una variable.
            if not variable["inicializada"]:
                self.reportar(
                    token,
                    f"La variable '{nombre}' se usa "
                    "antes de inicializarla."
                )
                return

            if not variable["mutable"]:
                self.reportar(
                    token,
                    f"No se puede modificar '{nombre}' "
                    "porque no fue declarada con 'mut'."
                )
                return

            # Reutilizar las reglas aritméticas existentes.
            # Eliminar el "=" convierte "+=" en "+", etc.
            #
            # Creamos una copia del token para conservar
            # su posición sin modificar el árbol de ANTLR.
            operador_aritmetico = copy(operador)
            operador_aritmetico.text = operador.text[:-1]

            tipo_resultado = self.comprobar_operacion(
                variable["tipo"],
                tipo_valor,
                operador_aritmetico,
            )

            # Si la operación es válida, conserva el tipo
            # de la variable y su estado de inicialización.
            if (
                tipo_resultado is not None
                and len(self.errores) == errores_antes
            ):
                variable["inicializada"] = True
                variable["puede_inicializada"] = True

            return

        # -------------------------------------------------
        # Asignación simple: =
        # -------------------------------------------------

        # Una variable sin mut admite su primera asignación,
        # pero no una posible segunda asignación.
        if variable["puede_inicializada"] and not variable["mutable"]:
            self.reportar(
                token,
                f"No se puede modificar '{nombre}' "
                "porque no fue declarada con 'mut'."
            )
            return

        # Dentro de un ciclo, una asignación a una variable
        # externa podría repetirse; por ahora exige mut.
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

        # Solo marcar como inicializada si el valor es válido.
        if (
            tipo_valor is not None
            and len(self.errores) == errores_antes
        ):
            variable["inicializada"] = True
            variable["puede_inicializada"] = True

    # =================================================
    # 9. EXPRESIONES LÓGICAS
    # =================================================

    def visitExpression(self, ctx):
        """Devuelve y registra el tipo que calcula la expresión de menor prioridad, logicalOr."""
        return self.guardar_tipo(ctx, self.visit(ctx.logicalOr()))

    def comprobar_logica(self, izquierdo, derecho, token):
        """Exige dos operandos bool y devuelve bool. Propaga None sin duplicar errores de operandos."""
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

    def visitar_operando_condicional(self, nodo):
        """Analiza un operando que puede omitirse por cortocircuito."""
        originales = self.ambitos
        antes = deepcopy(originales)

        try:
            # Revisamos el operando para detectar errores,
            # aunque durante la ejecución podría omitirse.
            self.ambitos = deepcopy(antes)
            tipo = self.visit(nodo)
            despues = deepcopy(self.ambitos)

        finally:
            # Conservamos la identidad de los ámbitos originales.
            self.ambitos = originales

        # Hay dos caminos: ejecutar el operando u omitirlo.
        # Una asignación opcional no garantiza inicialización.
        for indice, ambito in enumerate(originales):
            for nombre, variable in ambito.items():
                previo = antes[indice][nombre]
                posterior = despues[indice][nombre]

                variable["inicializada"] = (
                    previo["inicializada"]
                    and posterior["inicializada"]
                )

                # Sí puede haber recibido valor. Esto impide
                # una posible segunda asignación sin mut.
                variable["puede_inicializada"] = (
                    previo["puede_inicializada"]
                    or posterior["puede_inicializada"]
                )

        return tipo

    def visitLogicalOr(self, ctx):
        """El primer operando se evalúa; los siguientes pueden omitirse."""
        operandos = ctx.logicalAnd()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            derecho = self.visitar_operando_condicional(
                operandos[indice]
            )
            tipo = self.comprobar_logica(
                tipo,
                derecho,
                ctx.OR(indice - 1).getSymbol(),
            )

        return self.guardar_tipo(ctx, tipo)

    def visitLogicalAnd(self, ctx):
        """Comprueba booleanos y contempla el cortocircuito de AND."""
        operandos = ctx.comparison()
        tipo = self.visit(operandos[0])

        for indice in range(1, len(operandos)):
            derecho = self.visitar_operando_condicional(
                operandos[indice]
            )
            tipo = self.comprobar_logica(
                tipo,
                derecho,
                ctx.AND(indice - 1).getSymbol(),
            )

        return self.guardar_tipo(ctx, tipo)

    # =================================================
    # 10. COMPARACIONES
    # =================================================

    def visitComparison(self, ctx):
        """Exige tipos compatibles; las comparaciones de orden siguen limitadas a números. Una comparación válida produce bool."""
        operandos = ctx.additive()
        izquierdo = self.visit(operandos[0])

        # Sin operador, conservar el tipo de la expresión.
        if ctx.relOp() is None:
            return self.guardar_tipo(ctx, izquierdo)

        derecho = self.visit(operandos[1])
        operador = ctx.relOp().start

        # Evitar errores adicionales si un operando ya falló.
        if izquierdo is None or derecho is None:
            return self.guardar_tipo(ctx, None)

        # Ambos operandos deben tener exactamente el mismo tipo.
        if izquierdo != derecho:
            self.reportar(
                operador,
                "Comparación incompatible entre "
                f"{izquierdo} y {derecho}."
            )
            return self.guardar_tipo(ctx, None)

        # unit representa la ausencia de un valor.
        if izquierdo == "unit":
            self.reportar(
                operador,
                "No se pueden comparar llamadas "
                "que no devuelven un valor."
            )
            return self.guardar_tipo(ctx, None)

        # Igualdad y diferencia admiten los tipos disponibles:
        # i32, f64, bool, char y String.
        #
        # Conservamos por ahora la regla existente:
        # las comparaciones de orden solo admiten números.
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
    # 11. OPERACIONES ARITMÉTICAS
    # =================================================

    def comprobar_operacion(self, izquierdo, derecho, token):
        """Valida aritmética: números del mismo tipo y módulo solo i32. No introduce conversiones implícitas."""
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

    def visitar_operacion_numerica(self, ctx, operandos):
        """Comprueba aritmética teniendo en cuenta los saltos."""
        # Revisamos todos los operandos para conservar los errores
        # de nombres y las validaciones internas.
        tipos = [self.visit(operando) for operando in operandos]
        tipo = tipos[0]

        # Sin operador, esta regla únicamente transmite el tipo.
        if len(operandos) == 1:
            return self.guardar_tipo(ctx, tipo)

        continua = "normal" in salidas_control(operandos[0])

        for indice in range(1, len(operandos)):
            derecho_continua = (
                "normal" in salidas_control(operandos[indice])
            )

            # Solo se realiza la operación si ambos lados
            # pueden terminar normalmente y entregar valores.
            if continua and derecho_continua:
                tipo = self.comprobar_operacion(
                    tipo,
                    tipos[indice],
                    ctx.getChild(2 * indice - 1).getSymbol(),
                )

            continua = continua and derecho_continua

        # unit representa ausencia de resultado.
        # salidas_control distingue un salto de un bloque
        # unit que sí termina normalmente.
        return self.guardar_tipo(
            ctx, tipo if continua else "unit"
        )

    def visitAdditive(self, ctx):
        """Comprueba sumas y restas considerando los saltos."""
        return self.visitar_operacion_numerica(
            ctx, ctx.multiplicative()
        )

    def visitMultiplicative(self, ctx):
        """Comprueba multiplicación, división y residuo."""
        return self.visitar_operacion_numerica(
            ctx, ctx.unary()
        )
    # =================================================
    # 12. OPERADORES UNARIOS Y VALORES
    # =================================================

    def visitUnary(self, ctx):
        # Primero resolver el valor y sus accesos:
        # por ejemplo, numeros[0].
        """Calcula el tipo tras los accesos y después comprueba - o !. No calcula el valor numérico."""
        operando = ctx.postfix() or ctx.borrowExpr() or ctx.dereferenceExpr()
        tipo = self.visit(operando)
        # Si el operando abandona el contexto, el operador
        # negativo o lógico no llega a aplicarse.
        if (
            (ctx.MINUS() is not None or ctx.NOT() is not None)
            and "normal" not in salidas_control(operando)
        ):
            return self.guardar_tipo(ctx, "unit")
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

    def separar_tipo_arreglo(self, tipo):
        """
        Devuelve el tipo del elemento y el tamaño.
        Ejemplo: [i32;3] -> ("i32", 3).
        También admite arreglos anidados.
        """
        if (
            tipo is None
            or not tipo.startswith("[")
            or not tipo.endswith("]")
        ):
            return None

        contenido = tipo[1:-1]
        elemento, cantidad = contenido.rsplit(";", 1)
        return elemento, int(cantidad)

    def comprobar_indices(self, tipo, expresiones, nodos=None):
        """Comprueba lecturas y destinos con las mismas reglas de índices."""
        for posicion, expresion_indice in enumerate(expresiones):
            tipo_indice = self.visit(expresion_indice)
            if tipo is None:
                continue
            arreglo = self.separar_tipo_arreglo(tipo)
            if arreglo is None:
                self.reportar(
                    expresion_indice.start,
                    f"No se puede indexar un valor de tipo {tipo}."
                )
                tipo = None
                continue
            if tipo_indice is None:
                tipo = None
                continue

            # Si evaluar el índice provoca un salto, no se llega
            # a acceder al elemento ni a comprobar sus límites.
            # Conservamos el tipo nominal del elemento.
            if "normal" not in salidas_control(expresion_indice):
                tipo = arreglo[0]

                if nodos is not None:
                    self.guardar_tipo(nodos[posicion], tipo)

                continue
            if tipo_indice != "i32":
                self.reportar(expresion_indice.start, "El índice de un arreglo debe ser i32.")
                tipo = None
                continue
            elemento, cantidad = arreglo
            texto = expresion_indice.getText()
            digitos = texto[1:] if texto.startswith("-") else texto
            if cantidad == 0 or (digitos.isdigit() and not 0 <= int(texto) < cantidad):
                self.reportar(
                    expresion_indice.start,
                    f"Índice {texto} fuera de rango para un arreglo de tamaño {cantidad}."
                )
                tipo = None
                continue
            # Los índices dinámicos requieren una guarda en el backend.
            tipo = elemento
            if nodos is not None:
                self.guardar_tipo(nodos[posicion], tipo)
        return tipo

    def comprobar_accesos(self, tipo, accesos):
        """Aplica accesos de arreglo y de tupla en el orden escrito."""
        for clase, nodo in accesos:
            # Un acceso sobre &T o &mut T consulta el valor apuntado.
            # Conservamos el tipo de la base: el backend necesita saber que
            # primero debe cargar una dirección y después acceder al campo.
            referencia = separar_referencia(tipo)
            if referencia is not None:
                tipo = referencia[1]
            if clase == "indice":
                es_destino = isinstance(nodo, RustiQParser.IndexAccessContext)
                expresion = nodo.expression() if es_destino else nodo
                tipo = self.comprobar_indices(
                    tipo, [expresion], [nodo] if es_destino else None,
                )
            elif clase == "nombre" and tipo is not None:
                nombre = nodo.IDENT().getText()
                campos = self.estructuras.get(tipo)
                if campos is None:
                    self.reportar(nodo.start, f"No se puede acceder al campo '{nombre}' en un valor de tipo {tipo}.")
                    tipo = None
                elif nombre not in campos:
                    self.reportar(nodo.IDENT().getSymbol(), f"La estructura '{tipo}' no tiene el campo '{nombre}'.")
                    tipo = None
                else:
                    tipo = campos[nombre]
                    self.guardar_tipo(nodo, tipo)
            elif clase == "campo" and tipo is not None:
                campos = separar_tipo_tupla(tipo)
                posicion = int(nodo.getText()[1:])
                if campos is None:
                    self.reportar(nodo.start, f"No se puede acceder a un campo de tupla en un valor de tipo {tipo}.")
                    tipo = None
                elif posicion >= len(campos):
                    self.reportar(
                        nodo.start,
                        f"Campo {posicion} fuera de rango para una tupla de {len(campos)} elementos."
                    )
                    tipo = None
                else:
                    tipo = campos[posicion]
                    self.guardar_tipo(nodo, tipo)
        return tipo

    def visitPostfix(self, ctx):
        """Comprueba accesos cuando la base puede producir un valor."""
        base = ctx.primary()
        tipo_base = self.visit(base)
        accesos = list(accesos_lectura(ctx))

        if accesos and "normal" not in salidas_control(base):
            # La base termina mediante un salto.
            # Visitamos los índices para detectar errores internos,
            # pero no exigimos campos de un valor que no se produce.
            self.comprobar_accesos(None, accesos)
            return self.guardar_tipo(ctx, "unit")

        tipo = self.comprobar_accesos(tipo_base, accesos)
        return self.guardar_tipo(ctx, tipo)

    def visitar_asignacion_elemento(self, ctx):
        """Exige un valor completo inicializado y mutable; comprueba tipo del destino y del valor. No inicializa parcialmente por campos."""
        token = ctx.IDENT().getSymbol()
        variable = self.buscar_variable(token.text)
        errores_antes = len(self.errores)
        tipo_destino = self.comprobar_accesos(
            variable["tipo"] if variable is not None else None,
            accesos_escritura(ctx),
        )
        tipo_valor = self.visitar_con_tipo(ctx.expression(), tipo_destino)
        # También registrar el tipo del destino completo para el backend.
        self.guardar_tipo(ctx, tipo_destino)

        if variable is None:
            self.reportar(token, f"La variable '{token.text}' no está declarada.")
            return
        # Escribir un elemento o campo exige inicializar el valor completo.
        # No se deduce inicialización parcial por elementos o campos.
        if not variable["inicializada"]:
            self.reportar(token, f"La variable '{token.text}' se usa antes de inicializarla.")
            return
        # Si un índice o el valor derecho provoca un salto,
        # no se llega a escribir el elemento o campo.
        if "normal" not in salidas_control(ctx):
            return

        # Para p.campo mediante &mut T importa la capacidad del préstamo,
        # no si el binding p fue declarado como let mut. &T nunca permite escribir.
        referencia = separar_referencia(variable["tipo"])
        permite_escribir = referencia[0] if referencia is not None else variable["mutable"]
        if not permite_escribir:
            self.reportar(
                token,
                "No se puede escribir mediante una referencia inmutable."
                if referencia is not None else
                f"No se puede modificar '{token.text}' porque no fue declarada con 'mut'."
            )
            return
        if tipo_destino is None or tipo_valor is None or len(self.errores) != errores_antes:
            return
        operador = ctx.assignmentOp().start
        if operador.text == "=":
            if tipo_destino != tipo_valor:
                self.reportar(
                    token,
                    f"Tipos incompatibles en el elemento de '{token.text}': "
                    f"se esperaba {tipo_destino}, pero se recibió {tipo_valor}."
                )
        else:
            aritmetico = copy(operador)
            aritmetico.text = operador.text[:-1]
            self.comprobar_operacion(tipo_destino, tipo_valor, aritmetico)


    def visitArrayLiteral(self, ctx):
        """Infiere el elemento del arreglo sin confundir un salto con unit."""
        expresiones = ctx.expression()
        esperado = self.separar_tipo_arreglo(self.tipos_esperados.get(ctx))
        if not expresiones:
            if esperado is None:
                self.reportar(ctx.start, "No se puede inferir el tipo de un arreglo vacío: indicá un tipo.")
                return self.guardar_tipo(ctx, None)
            return self.guardar_tipo(ctx, f"[{esperado[0]};0]")

        contextual = esperado[0] if esperado is not None else None
        tipos = [self.visitar_con_tipo(e, contextual) for e in expresiones]
        if any(tipo is None for tipo in tipos):
            return self.guardar_tipo(ctx, None)

        if any('&' in tipo for tipo in tipos if tipo is not None):
            self.reportar(ctx.start, "No se admiten referencias dentro de arreglos o tuplas.")
            return self.guardar_tipo(ctx, None)
        # Un elemento que salta no produce un valor para comparar.
        # Conservamos la posición original para ubicar los errores.
        normales = [
            (indice, tipo)
            for indice, (expresion, tipo) in enumerate(zip(expresiones, tipos))
            if "normal" in salidas_control(expresion)
        ]
        valido = True
        elemento = normales[0][1] if normales else None
        for indice, tipo in normales:
            if tipo == "unit":
                self.reportar(expresiones[indice].start, "Un arreglo no puede contener valores unit.")
                valido = False
            elif tipo != elemento:
                self.reportar(
                    expresiones[indice].start,
                    f"El elemento {indice + 1} del arreglo debe ser {elemento}, pero se recibió {tipo}.",
                )
                valido = False
        if not valido:
            return self.guardar_tipo(ctx, None)
        if "normal" not in salidas_control(ctx):
            # No se termina de construir el arreglo: no inventar su elemento.
            return self.guardar_tipo(ctx, "unit")
        return self.guardar_tipo(ctx, f"[{elemento};{len(expresiones)}]")

    def visitTupleLiteral(self, ctx):
        """Comprueba posiciones de una tupla y conserva el contexto de tipos."""
        esperados = separar_tipo_tupla(self.tipos_esperados.get(ctx)) or []
        expresiones = ctx.expression()
        tipos = [
            self.visitar_con_tipo(e, esperados[i] if i < len(esperados) else None)
            for i, e in enumerate(expresiones)
        ]
        if any(tipo is None for tipo in tipos):
            return self.guardar_tipo(ctx, None)
        if any('&' in tipo for tipo in tipos if tipo is not None):
            self.reportar(ctx.start, "No se admiten referencias dentro de arreglos o tuplas.")
            return self.guardar_tipo(ctx, None)
        for expresion, tipo in zip(expresiones, tipos):
            # Un unit normal es inválido como elemento; un salto no es un valor.
            if "normal" in salidas_control(expresion) and tipo == "unit":
                self.reportar(expresion.start, "Una tupla no puede contener valores unit.")
                return self.guardar_tipo(ctx, None)
        if "normal" not in salidas_control(ctx):
            return self.guardar_tipo(ctx, "unit")
        return self.guardar_tipo(ctx, "(" + ",".join(tipos) + ")")

    def visitStructLiteral(self, ctx):
        """Comprueba un constructor y devuelve su tipo nominal.

        Aunque el orden puede variar, cada campo debe aparecer una vez.
        Se visitan todos los valores para no ocultar errores en ellos.
        """
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        campos = self.estructuras.get(nombre)
        errores_antes = len(self.errores)
        if campos is None:
            self.reportar(token, f"La estructura '{nombre}' no está declarada.")
        vistos = set()
        for campo in ctx.fieldInit():
            identificador = campo.IDENT().getSymbol()
            esperado = campos.get(identificador.text) if campos is not None else None
            tipo = self.visitar_con_tipo(campo.expression(), esperado)
            if identificador.text in vistos:
                self.reportar(identificador, f"El campo '{identificador.text}' está repetido al construir '{nombre}'.")
            vistos.add(identificador.text)
            if campos is not None:
                if identificador.text not in campos:
                    self.reportar(identificador, f"La estructura '{nombre}' no tiene el campo '{identificador.text}'.")
                elif (tipo is not None and tipo != esperado
                      and "normal" in salidas_control(campo.expression())):
                    # Solo un campo que entrega un valor debe coincidir en tipo.
                    self.reportar(identificador, f"Tipo incompatible en '{nombre}.{identificador.text}': se esperaba {esperado}, pero se recibió {tipo}.")
        if campos is not None:
            # Mantener el orden de declaración en los diagnósticos.
            for faltante in campos:
                if faltante not in vistos:
                    self.reportar(token, f"Falta el campo '{faltante}' al construir '{nombre}'.")
        valido = campos is not None and len(self.errores) == errores_antes
        return self.guardar_tipo(ctx, nombre if valido else None)


    def visitEnumValue(self, ctx):
        """
        Comprueba un constructor como Resultado::Correcto(10).

        Verifica:
        - Existencia del enum y de la variante.
        - Uso correcto de los paréntesis.
        - Cantidad de argumentos.
        - Tipo de cada argumento.

        Devuelve el nombre del enum si todo es correcto.
        """

        token_tipo = ctx.IDENT(0).getSymbol()
        token_variante = ctx.IDENT(1).getSymbol()

        nombre = token_tipo.text
        variante = token_variante.text

        enumeracion = self.enumeraciones.get(nombre)
        lista = ctx.argumentList()

        argumentos = (
            lista.expression() if lista is not None else []
        )

        if enumeracion is None:
            # Revisar también los argumentos para recoger
            # errores dentro de sus expresiones.
            for argumento in argumentos:
                self.visit(argumento)

            self.reportar(
                token_tipo,
                f"La enumeración '{nombre}' no está declarada."
            )
            return self.guardar_tipo(ctx, None)

        if variante not in enumeracion["variantes"]:
            for argumento in argumentos:
                self.visit(argumento)

            self.reportar(
                token_variante,
                f"La enumeración '{nombre}' "
                f"no tiene la variante '{variante}'."
            )
            return self.guardar_tipo(ctx, None)

        # Los enums antiguos no necesitan datos_variantes.
        # Una variante sin datos espera una lista vacía.
        esperados = enumeracion.get(
            "datos_variantes", {}
        ).get(variante, [])

        errores_antes = len(self.errores)
        tiene_parentesis = ctx.LPAREN() is not None

        if esperados and not tiene_parentesis:
            self.reportar(
                token_variante,
                f"La variante '{nombre}::{variante}' "
                "requiere argumentos entre paréntesis."
            )

        elif not esperados and tiene_parentesis:
            self.reportar(
                token_variante,
                f"La variante '{nombre}::{variante}' "
                "no recibe argumentos ni utiliza paréntesis."
            )

        if len(argumentos) != len(esperados):
            self.reportar(
                token_variante,
                f"La variante '{nombre}::{variante}' espera "
                f"{len(esperados)} argumentos, pero recibió "
                f"{len(argumentos)}."
            )

        for indice, argumento in enumerate(argumentos):
            esperado = (
                esperados[indice]
                if indice < len(esperados)
                else None
            )

            # El contexto permite, por ejemplo, pasar []
            # si la variante espera un arreglo [i32;0].
            recibido = self.visitar_con_tipo(
                argumento,
                esperado,
            )

            if (
                esperado is not None
                and recibido is not None
                and recibido != esperado
                and "normal" in salidas_control(argumento)
            ):
                self.reportar(
                    argumento.start,
                    f"Argumento {indice + 1} de "
                    f"'{nombre}::{variante}': "
                    f"se esperaba {esperado}, "
                    f"pero se recibió {recibido}."
                )

        valido = len(self.errores) == errores_antes

        return self.guardar_tipo(
            ctx,
            nombre if valido else None,
        )

    def visitMatchExpr(self, ctx):
        """Delega patrones, ámbitos de brazos, tipos y exhaustividad."""
        return analizar_match(self, ctx)

    def visitPrimary(self, ctx):
        """
        Determina el tipo de un valor básico o compuesto.

        Los literales tienen tipos conocidos.
        Las variables se buscan en los ámbitos.
        Los constructores se comprueban en sus propios métodos.
        """

        if ctx.INT() is not None:
            tipo = "i32"

        elif ctx.FLOAT() is not None:
            tipo = "f64"

        elif ctx.TRUE() is not None or ctx.FALSE() is not None:
            tipo = "bool"

        elif ctx.CHAR_LITERAL() is not None:
            tipo = "char"

        elif ctx.STRING_LITERAL() is not None:
            tipo = "String"

        elif ctx.arrayLiteral() is not None:
            tipo = self.visit(ctx.arrayLiteral())

        elif ctx.tupleLiteral() is not None:
            tipo = self.visit(ctx.tupleLiteral())

        elif ctx.structLiteral() is not None:
            tipo = self.visit(ctx.structLiteral())

        elif ctx.enumValue() is not None:
            tipo = self.visit(ctx.enumValue())

        elif ctx.block() is not None:
            # Un bloque puede utilizarse como una expresión.
            # Su tipo depende de su expresión final.
            tipo = self.visit(ctx.block())

        elif ctx.matchExpr() is not None:
            tipo = self.visit(ctx.matchExpr())

        elif ctx.functionCall() is not None:
            tipo = self.visit(ctx.functionCall())

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
            # Los paréntesis conservan el tipo de la expresión.
            tipo = self.visit(ctx.expression())

        return self.guardar_tipo(ctx, tipo)
