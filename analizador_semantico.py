from copy import copy, deepcopy
from generated.RustiQVisitor import RustiQVisitor
from generated.RustiQParser import RustiQParser
from gestor_constantes import GestorConstantes
from tipos_compuestos import (
    normalizar_tipo, separar_tipo_tupla, accesos_lectura, accesos_escritura,
)

class AnalizadorSemantico(RustiQVisitor):
    def __init__(self):
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

        # Cantidad de ámbitos existentes antes de cada ciclo.
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
        nodo = ctx.getTypedRuleContext(RustiQParser.TypeContext, 0)
        return self.normalizar_tipo(nodo) if nodo is not None else None

    def normalizar_tipo(self, nodo):
        return normalizar_tipo(nodo)

    def visitar_con_tipo(self, ctx, esperado=None):
        """Propaga el tipo esperado a literales compuestos directos o entre paréntesis.

        No se propaga a operandos aritméticos, índices o llamadas: esos
        contextos tienen sus propias reglas de tipos.
        """
        if esperado is not None:
            nodo = ctx
            while nodo is not None:
                if isinstance(nodo, (RustiQParser.ArrayLiteralContext, RustiQParser.TupleLiteralContext)):
                    self.tipos_esperados[nodo] = esperado
                    break
                if isinstance(nodo, RustiQParser.PrimaryContext):
                    if nodo.arrayLiteral() is not None:
                        nodo = nodo.arrayLiteral()
                    elif nodo.tupleLiteral() is not None:
                        nodo = nodo.tupleLiteral()
                    elif nodo.expression() is not None:
                        nodo = nodo.expression()
                    else:
                        break
                elif nodo.getChildCount() == 1 and hasattr(nodo.getChild(0), "getChildren"):
                    nodo = nodo.getChild(0)
                else:
                    break
        return self.visit(ctx)

    def guardar_tipo(self, ctx, tipo):
        self.tipos_expresiones[ctx] = tipo
        return tipo

    def buscar_variable_con_ambito(self, nombre):
        # Primero buscar variables y parámetros locales.
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
        variable, _ = self.buscar_variable_con_ambito(nombre)
        return variable

    def obtener_parametros(self, ctx):
        lista = ctx.parameterList()
        return lista.parameter() if lista is not None else []

    # =================================================
    # 2. REGISTRO DE FUNCIONES
    # =================================================

    def visitProgram(self, ctx):
        # Registrar todas las funciones antes de revisar cuerpos.
        for funcion in ctx.functionDecl():
            token = funcion.IDENT().getSymbol()
            nombre = token.text

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

        # Registrar los nombres y tipos de las constantes.
        gestor = GestorConstantes(self)
        gestor.registrar(ctx.constDecl())

        # La búsqueda de identificadores utiliza este registro.
        self.constantes = gestor.simbolos

        # Comprobar tipos y calcular valores antes de los cuerpos.
        gestor.validar_y_calcular()
        self.valores_constantes = gestor.valores

        for funcion in ctx.functionDecl():
            self.visit(funcion)

    # =================================================
    # 3. CUERPOS DE FUNCIONES Y PARÁMETROS
    # =================================================

    def visitFunctionDecl(self, ctx):
        anteriores = self.ambitos
        retorno_anterior = self.tipo_retorno
        ciclos_anteriores = self.limites_ciclos

        # Los parámetros comparten ámbito con las variables
        # declaradas directamente en el cuerpo de la función.
        self.ambitos = [{}]
        self.limites_ciclos = []
        self.tipo_retorno = (
            self.obtener_tipo_declarado(ctx) or "unit"
        )

        try:
            for parametro in self.obtener_parametros(ctx):
                token = parametro.IDENT().getSymbol()
                nombre = token.text

                if nombre in self.ambitos[-1]:
                    self.reportar(
                        token,
                        f"El parámetro '{nombre}' ya fue declarado."
                    )
                    continue

                # Un parámetro recibe su valor al llamar
                # a la función, por eso está inicializado.
                self.ambitos[-1][nombre] = {
                    "tipo": self.obtener_tipo_declarado(parametro),
                    "mutable": parametro.MUT() is not None,
                    "inicializada": True,
                    "puede_inicializada": True,
                }

            # No usamos visitBlock aquí porque crearía
            # otro ámbito entre parámetros y variables locales.
            for sentencia in ctx.block().statement():
                self.visit(sentencia)

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

    # =================================================
    # 4. LLAMADAS A FUNCIONES
    # =================================================

    def visitFunctionCall(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        lista = ctx.argumentList()

        argumentos = (
            lista.expression() if lista is not None else []
        )

        # Revisamos todos los argumentos, aunque la función
        # no exista, para detectar errores dentro de ellos.
        tipos_esperados = self.funciones.get(nombre, {}).get("parametros", [])
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

        funcion = self.funciones.get(nombre)

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
            elif recibido != esperado:
                self.reportar(
                    argumentos[indice - 1].start,
                    f"Argumento {indice} de '{nombre}': "
                    f"se esperaba {esperado}, "
                    f"pero se recibió {recibido}."
                )
                llamada_valida = False

        tipo = funcion["retorno"] if llamada_valida else None
        return self.guardar_tipo(ctx, tipo)

    # =================================================
    # 5. RETORNOS
    # =================================================

    def bloque_garantiza_retorno(self, ctx):
        for sentencia in ctx.statement():
            if sentencia.returnStmt() is not None:
                return True

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

            # Un while podría ejecutarse cero veces.
            # Por eso no garantiza un retorno.

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
            self.visitar_con_tipo(expresion, self.tipo_retorno)
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
    # 6. BLOQUES Y CONDICIONALES
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

            # El cuerpo podría no ejecutarse.
            self.ambitos = inicial

    def visitLoopStmt(self, ctx):
        # Guardar el estado de las variables externas.
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
    # 8. VARIABLES Y ASIGNACIONES
    # =================================================

    def visitLetDecl(self, ctx):
        token = ctx.IDENT().getSymbol()
        nombre = token.text
        ambito = self.ambitos[-1]
        declarado = self.obtener_tipo_declarado(ctx)
        expresion = ctx.expression()

        errores_antes = len(self.errores)
        tipo_valor = (
            self.visitar_con_tipo(expresion, declarado)
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

    def visitAssignment(self, ctx):
        # Conservar el comportamiento de las asignaciones simples.
        if ctx.indexAccess() or ctx.tupleAccess():
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

        if variable is None:
            self.reportar(
                token,
                f"La variable '{nombre}' no está declarada."
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
    # 10. COMPARACIONES
    # =================================================

    def visitComparison(self, ctx):
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
    # 12. OPERADORES UNARIOS Y VALORES
    # =================================================

    def visitUnary(self, ctx):
        # Primero resolver el valor y sus accesos:
        # por ejemplo, numeros[0].
        tipo = self.visit(ctx.postfix())

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
            if clase == "indice":
                es_destino = isinstance(nodo, RustiQParser.IndexAccessContext)
                expresion = nodo.expression() if es_destino else nodo
                tipo = self.comprobar_indices(
                    tipo, [expresion], [nodo] if es_destino else None,
                )
            elif tipo is not None:
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
        tipo = self.comprobar_accesos(self.visit(ctx.primary()), accesos_lectura(ctx))
        return self.guardar_tipo(ctx, tipo)

    def visitar_asignacion_elemento(self, ctx):
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
        if not variable["mutable"]:
            self.reportar(
                token,
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
        expresiones = ctx.expression()
        esperado = self.separar_tipo_arreglo(self.tipos_esperados.get(ctx))
        if not expresiones:
            if esperado is None:
                self.reportar(ctx.start, "No se puede inferir el tipo de un arreglo vacío: indicá un tipo.")
                return self.guardar_tipo(ctx, None)
            # Mantener tamaño cero real: el llamador detecta si esperaba otro tamaño.
            return self.guardar_tipo(ctx, f"[{esperado[0]};0]")

        tipo_contextual = esperado[0] if esperado is not None else None
        tipos = [self.visitar_con_tipo(e, tipo_contextual) for e in expresiones]
        if any(tipo is None for tipo in tipos):
            return self.guardar_tipo(ctx, None)
        elemento = tipos[0]
        valido = True
        if elemento == "unit":
            self.reportar(expresiones[0].start, "Un arreglo no puede contener valores unit.")
            valido = False
        for indice, tipo in enumerate(tipos[1:], start=1):
            if tipo != elemento:
                self.reportar(
                    expresiones[indice].start,
                    f"El elemento {indice + 1} del arreglo debe ser {elemento}, pero se recibió {tipo}."
                )
                valido = False
        return self.guardar_tipo(ctx, f"[{elemento};{len(expresiones)}]" if valido else None)

    def visitTupleLiteral(self, ctx):
        # Cada posición tiene su propio tipo. El contexto permite
        # resolver arreglos vacíos dentro de una tupla anotada.
        esperados = separar_tipo_tupla(self.tipos_esperados.get(ctx)) or []
        tipos = [
            self.visitar_con_tipo(expresion, esperados[i] if i < len(esperados) else None)
            for i, expresion in enumerate(ctx.expression())
        ]
        if any(tipo is None for tipo in tipos):
            return self.guardar_tipo(ctx, None)
        for expresion, tipo in zip(ctx.expression(), tipos):
            if tipo == "unit":
                self.reportar(expresion.start, "Una tupla no puede contener valores unit.")
                return self.guardar_tipo(ctx, None)
        return self.guardar_tipo(ctx, "(" + ",".join(tipos) + ")")

    def visitPrimary(self, ctx):
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

        # Determinar el tipo y tamaño de un arreglo literal.
        elif ctx.arrayLiteral() is not None:
            tipo = self.visit(ctx.arrayLiteral())

        elif ctx.tupleLiteral() is not None:
            tipo = self.visit(ctx.tupleLiteral())

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
            # Expresión entre paréntesis.
            tipo = self.visit(ctx.expression())

        return self.guardar_tipo(ctx, tipo)