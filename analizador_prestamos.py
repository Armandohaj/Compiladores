"""Préstamos léxicos de variables completas sobre los IDs existentes.

Una referencia local conserva su préstamo hasta salir de su ámbito. Los
préstamos temporales de argumentos se liberan al terminar la sentencia.
No se generan direcciones: eso corresponde al backend WebAssembly.
"""
from generated.RustiQParser import RustiQParser as P
from tipos_referencias import separar_referencia, identificador_simple
from tipos_compuestos import accesos_lectura
from clasificacion_propiedad import clasificar_tipo
from flujo_control import salidas_control


class AnalizadorPrestamos:
    def __init__(self, resolucion, tipos, estructuras, enumeraciones):
        """Prepara mapas independientes de cada análisis, sin modificar los símbolos."""
        self.simbolos = resolucion.simbolos
        self.declaraciones = resolucion.declaraciones
        self.referencias = resolucion.referencias
        self.tipos = tipos
        self.estructuras = estructuras
        self.enumeraciones = enumeraciones
        self.prestamos = {}  # Contrato público: únicamente BorrowExprContext.
        self.errores = []
        self.reportados = set()
        self.activos = {}
        self.vinculos = {}   # ID de variable referencia -> préstamos posibles.
        self.vivas = set()
        self.ambitos = []

    def reportar(self, token, mensaje):
        """Emite errores con el formato común y evita duplicados."""
        clave = (token.tokenIndex, mensaje)
        if clave not in self.reportados:
            self.reportados.add(clave)
            self.errores.append({
                'fase': 'semantico', 'mensaje': mensaje,
                'linea': token.line, 'columna': token.column + 1,
            })

    def analizar(self, programa):
        """Las funciones se comprueban por separado; los parámetros viven al entrar."""
        for funcion in programa.functionDecl():
            nombre = funcion.IDENT().getText()
            parametros = {
                i for i, s in self.simbolos.items()
                if s['funcion'] == nombre and s['es_parametro']
            }
            self.vivas = set(parametros)
            self.ambitos = [set(parametros)]
            self.activos = {}
            self.vinculos = {}
            for identificador in parametros:
                referencia = separar_referencia(self.simbolos[identificador]['tipo'])
                if referencia is not None:
                    mutable, tipo = referencia
                    # El origen externo no pertenece a las variables locales del
                    # callee. El caller comprueba los conflictos de los argumentos.
                    clave = ('parametro', identificador)
                    self.activos[clave] = {'simbolo_id': identificador, 'tipo': tipo, 'mutable': mutable}
                    self.vinculos[identificador] = {clave}
            self.evaluar(funcion.block())

    def limpiar(self, conservar=()):
        """Mantiene préstamos vinculados a referencias vivas o resultados temporales."""
        usados = set(conservar)
        for identificador in self.vivas:
            usados.update(self.vinculos.get(identificador, ()))
        self.activos = {k: v for k, v in self.activos.items() if k in usados}

    def conflictos(self, identificador):
        """Devuelve préstamos activos sobre la misma variable completa."""
        return [v for v in self.activos.values() if v['simbolo_id'] == identificador]

    def leer_variable(self, identificador, token, transferir):
        """Impide leer un propietario prestado en exclusiva o moverlo prestado."""
        simbolo = self.simbolos[identificador]
        prestamos = self.conflictos(identificador)
        if any(p['mutable'] for p in prestamos):
            self.reportar(token, f"No se puede acceder directamente a '{simbolo['nombre']}' mientras tiene un préstamo mutable activo.")
        elif transferir and prestamos and clasificar_tipo(simbolo['tipo'], self.estructuras, self.enumeraciones) == 'Move':
            self.reportar(token, f"No se puede mover '{simbolo['nombre']}' mientras tiene préstamos activos.")

    def comprobar_referencia(self, claves, token, escritura=False):
        """Valida que una desreferenciación siga apuntando a un origen vivo."""
        if not claves:
            self.reportar(token, "No se pudo determinar un origen válido para la referencia.")
        for clave in claves:
            prestamo = self.activos.get(clave)
            if prestamo is None or prestamo['simbolo_id'] not in self.vivas:
                self.reportar(token, "La referencia apunta a una variable que dejó de existir.")
            elif escritura and not prestamo['mutable']:
                self.reportar(token, "No se puede escribir mediante una referencia inmutable.")

    def evaluar_brazo(self, brazo):
        """Los receptores de un patrón viven únicamente dentro de su brazo.

        ResolucionVariables ya les asignó sus IDs. Aquí se reutilizan para
        comprobar préstamos, incluso en patrones de tuplas y variantes anidadas.
        El resultado puede prestar una variable exterior, pero no un receptor
        que desaparece al terminar este brazo.
        """
        anteriores = set(self.activos)
        locales = set()

        def registrar_receptores(patron):
            """Recoge solo declaraciones reales; ignora literales y variantes."""
            identificador = self.declaraciones.get(patron)
            if identificador is not None:
                locales.add(identificador)
            for hijo in patron.getChildren():
                if hasattr(hijo, 'getChildren'):
                    registrar_receptores(hijo)

        registrar_receptores(brazo.pattern())
        self.vivas.update(locales)
        self.ambitos.append(locales)
        resultado = set()
        try:
            resultado = self.evaluar(brazo.expression(), True)
        finally:
            self.ambitos.pop()
            self.vivas.difference_update(locales)
            for clave in resultado:
                registro = self.activos.get(clave)
                if registro is not None and registro['simbolo_id'] in locales:
                    self.reportar(brazo.start, 'Una referencia no puede sobrevivir al receptor local del patrón de match.')
            # Se conservan los préstamos exteriores y el valor del brazo, pero
            # los préstamos locales sin un resultado dejan de estar activos.
            self.limpiar(anteriores | resultado)
        return resultado

    def evaluar(self, nodo, transferir=False):
        """Devuelve préstamos posibles si el nodo produce una referencia."""
        if nodo is None:
            return set()
        if isinstance(nodo, P.BorrowExprContext):
            origen = identificador_simple(nodo.unary())
            identificador = self.referencias[origen]
            mutable = nodo.MUT() is not None
            anteriores = self.conflictos(identificador)
            if (mutable and anteriores) or any(p['mutable'] for p in anteriores):
                self.reportar(nodo.start, 'El préstamo es incompatible con los préstamos activos de la variable.')
            registro = {
                'simbolo_id': identificador,
                'tipo': self.simbolos[identificador]['tipo'],
                'mutable': mutable,
            }
            self.prestamos[nodo] = registro
            self.activos[nodo] = registro
            return {nodo}
        if isinstance(nodo, P.DereferenceExprContext):
            claves = self.evaluar(nodo.unary())
            self.comprobar_referencia(claves, nodo.start)
            return set()  # El valor apuntado no es una referencia en esta etapa.
        if isinstance(nodo, P.BlockContext):
            anteriores = set(self.activos)
            self.ambitos.append(set())
            resultado = set()
            try:
                continua = True
                for sentencia in nodo.statement():
                    if not continua:
                        break
                    self.evaluar(sentencia, True)
                    self.limpiar(anteriores)
                    continua = 'normal' in salidas_control(sentencia)
                if continua and nodo.expression() is not None:
                    resultado = self.evaluar(nodo.expression(), True)
            finally:
                locales = self.ambitos.pop()
                self.vivas.difference_update(locales)
                for clave in resultado:
                    registro = self.activos.get(clave)
                    if registro is not None and registro['simbolo_id'] in locales:
                        self.reportar(nodo.start, 'Una referencia no puede sobrevivir a la variable local que presta.')
                self.limpiar(anteriores | resultado)
            return resultado
        if isinstance(nodo, P.LetDeclContext):
            resultado = self.evaluar(nodo.expression(), True)
            identificador = self.declaraciones.get(nodo)
            if identificador is not None:
                self.vivas.add(identificador)
                self.ambitos[-1].add(identificador)
                if separar_referencia(self.simbolos[identificador]['tipo']) is not None:
                    self.comprobar_referencia(resultado, nodo.start)
                    self.vinculos[identificador] = resultado
            return set()
        if isinstance(nodo, P.AssignmentContext):
            identificador = self.referencias[nodo]
            if nodo.dereferenceTarget() is not None:
                claves = self.vinculos.get(identificador, set())
                self.evaluar(nodo.expression(), True)
                if 'normal' in salidas_control(nodo.expression()):
                    self.comprobar_referencia(claves, nodo.start, True)
                return set()
            # Reasignar referencias implicaría combinar y acortar vidas útiles;
            # se rechaza inicialmente en vez de inventar un origen o permitir escape.
            referencia = separar_referencia(self.simbolos[identificador]['tipo'])
            acceso_referenciado = referencia is not None and bool(
                nodo.indexAccess() or nodo.tupleAccess() or nodo.fieldAccess()
            )
            if referencia is not None and not acceso_referenciado:
                self.reportar(nodo.start, 'Esta versión no admite asignar o reasignar variables de referencia; usá let con inicializador.')
            for acceso in nodo.indexAccess():
                self.evaluar(acceso.expression())
            self.evaluar(nodo.expression(), True)
            if acceso_referenciado and 'normal' in salidas_control(nodo):
                # p.campo escribe el origen mediante la capacidad de p; no
                # reemplaza la referencia ni modifica el binding que la guarda.
                self.comprobar_referencia(self.vinculos.get(identificador, set()), nodo.start, True)
            if not acceso_referenciado and 'normal' in salidas_control(nodo) and self.conflictos(identificador):
                self.reportar(nodo.start, 'No se puede modificar un valor mientras tiene préstamos activos.')
            return set()
        if isinstance(nodo, P.PrimaryContext) and nodo.IDENT() is not None:
            identificador = self.referencias[nodo]
            if separar_referencia(self.simbolos[identificador]['tipo']) is not None:
                return set(self.vinculos.get(identificador, ()))
            self.leer_variable(identificador, nodo.start, transferir)
            return set()
        if isinstance(nodo, P.PostfixContext):
            accesos = list(accesos_lectura(nodo))
            resultado = self.evaluar(nodo.primary(), transferir if not accesos else False)
            for clase, acceso in accesos:
                if clase == 'indice':
                    self.evaluar(acceso)
            if accesos and separar_referencia(self.tipos.get(nodo.primary())) is not None:
                self.comprobar_referencia(resultado, nodo.start)
            return resultado if not accesos else set()
        if isinstance(nodo, P.FunctionCallContext):
            lista = nodo.argumentList()
            for argumento in lista.expression() if lista is not None else []:
                self.evaluar(argumento, True)
                if 'normal' not in salidas_control(argumento):
                    break
            return set()
        if isinstance(nodo, P.MatchExprContext):
            self.evaluar(nodo.expression(), True)
            resultado = set()
            if 'normal' in salidas_control(nodo.expression()):
                # Conservadoramente se acumulan préstamos de brazos que entregan
                # referencias. Los patrones con referencias se limitan por tipos.
                for brazo in nodo.matchArm():
                    resultado.update(self.evaluar_brazo(brazo))
            return resultado
        if isinstance(nodo, P.IfStmtContext):
            self.evaluar(nodo.expression())
            if 'normal' in salidas_control(nodo.expression()):
                self.evaluar(nodo.block(0))
                if nodo.ifStmt() is not None:
                    self.evaluar(nodo.ifStmt())
                elif nodo.ELSE() is not None:
                    self.evaluar(nodo.block(1))
            return set()
        if isinstance(nodo, (P.WhileStmtContext, P.LoopStmtContext)):
            if isinstance(nodo, P.WhileStmtContext):
                self.evaluar(nodo.expression())
                if 'normal' not in salidas_control(nodo.expression()):
                    return set()
            self.evaluar(nodo.block())
            return set()
        # Envoltorios y operadores: los operadores solo leen operandos;
        # los constructores transfieren componentes, igual que ownership.
        if isinstance(nodo, P.StructLiteralContext):
            for campo in nodo.fieldInit():
                self.evaluar(campo.expression(), True)
            return set()
        if isinstance(nodo, (P.ArrayLiteralContext, P.TupleLiteralContext, P.EnumValueContext)):
            hijos = nodo.argumentList().expression() if isinstance(nodo, P.EnumValueContext) and nodo.argumentList() is not None else (
                [] if isinstance(nodo, P.EnumValueContext) else nodo.expression()
            )
            for hijo in hijos:
                self.evaluar(hijo, True)
            return set()
        operar = isinstance(nodo, (P.AdditiveContext, P.MultiplicativeContext, P.ComparisonContext, P.UnaryContext, P.LogicalAndContext, P.LogicalOrContext)) and nodo.getChildCount() > 1
        resultado = set()
        for hijo in nodo.getChildren():
            if hasattr(hijo, 'getChildren'):
                resultado.update(self.evaluar(hijo, False if operar else transferir))
                if 'normal' not in salidas_control(hijo):
                    break
        return resultado if separar_referencia(self.tipos.get(nodo)) is not None else set()
