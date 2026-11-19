"""Comprueba disponibilidad y transferencias de valores sobre el árbol ANTLR.

Se ejecuta después de tipos y resolución de nombres. Los IDs existentes
permiten distinguir variables sombreadas sin inventar otro AST o tabla de nombres.
Este recorrido valida propiedad; no copia memoria ni ejecuta el programa.
"""
from copy import deepcopy
from generated.RustiQParser import RustiQParser as P
from clasificacion_propiedad import clasificar_tipo
from tipos_compuestos import accesos_lectura


class AnalizadorOwnership:
    """Estados posibles por símbolo: disponible, movido o sin inicializar."""

    def __init__(self, resolucion, tipos, estructuras, enumeraciones):
        self.simbolos = resolucion.simbolos
        self.declaraciones = resolucion.declaraciones
        self.referencias = resolucion.referencias
        self.tipos = tipos
        self.estructuras = estructuras
        self.enumeraciones = enumeraciones
        self.errores = []
        self.reportados = set()
        self.estados = {}
        self.vivo = True
        self.ciclos = []

    def clase(self, tipo):
        """Consulta la clasificación acordada, sin cambiar los tipos fuente."""
        return clasificar_tipo(tipo, self.estructuras, self.enumeraciones)

    def reportar(self, token, mensaje):
        """Evita repetir un diagnóstico al calcular el punto fijo de un ciclo."""
        clave = (token.tokenIndex, mensaje)
        if clave not in self.reportados:
            self.reportados.add(clave)
            self.errores.append({
                'fase': 'semantico', 'mensaje': mensaje,
                'linea': token.line, 'columna': token.column + 1,
            })

    def unir(self, caminos):
        """Una variable puede estar movida si lo está en algún camino posible."""
        if not caminos:
            return {}
        claves = set().union(*(camino.keys() for camino in caminos))
        return {
            clave: set().union(*(
                camino.get(clave, {'sin inicializar'}) for camino in caminos
            )) for clave in claves
        }

    def usar(self, identificador, token, transferir=False):
        """Leer requiere disponibilidad; transferir un Move consume su origen."""
        simbolo = self.simbolos[identificador]
        # Una constante representa un valor calculado que se materializa por uso;
        # no es una variable local cuyo almacenamiento se invalida al transferirlo.
        if simbolo['es_constante']:
            return
        estado = self.estados.get(identificador, {'sin inicializar'})
        if 'movido' in estado:
            self.reportar(token, f"La variable '{simbolo['nombre']}' se usa después de mover su valor.")
            return
        if 'sin inicializar' in estado:
            self.reportar(token, f"La variable '{simbolo['nombre']}' no tiene un valor disponible.")
            return
        if transferir and self.clase(simbolo['tipo']) == 'Move':
            self.estados[identificador] = {'movido'}

    def analizar(self, programa):
        """Cada función empieza con parámetros disponibles y estado independiente."""
        for funcion in programa.functionDecl():
            nombre = funcion.IDENT().getText()
            self.estados = {
                i: {'disponible'} for i, simbolo in self.simbolos.items()
                if simbolo['funcion'] == nombre and simbolo['es_parametro']
            }
            self.vivo = True
            self.ciclos = []
            self.evaluar(funcion.block(), True)

    def evaluar_ramas(self, ramas):
        """Aísla alternativas y conserva solo los caminos que continúan."""
        inicial = deepcopy(self.estados)
        continuaciones = []
        for patron, expresion in ramas:
            self.estados = deepcopy(inicial)
            self.vivo = True
            if patron is not None:
                self.activar_patron(patron)
            self.evaluar(expresion, True)
            if self.vivo:
                continuaciones.append(deepcopy(self.estados))
        self.estados = self.unir(continuaciones)
        self.vivo = bool(continuaciones)

    def activar_patron(self, nodo):
        """Los receptores pertenecen al valor ya transferido al match completo."""
        identificador = self.declaraciones.get(nodo)
        if identificador is not None:
            self.estados[identificador] = {'disponible'}
        for hijo in nodo.getChildren():
            if hasattr(hijo, 'getChildren'):
                self.activar_patron(hijo)

    def evaluar_ciclo(self, nodo):
        """Calcula estados hasta estabilizar las posibles iteraciones.

        El retorno termina la función; break y continue se guardan en el ciclo
        más cercano. El while también puede salir al evaluar su condición.
        """
        entrada = deepcopy(self.estados)
        cabecera = deepcopy(entrada)
        while True:
            self.estados = deepcopy(cabecera)
            self.vivo = True
            salidas = []
            if isinstance(nodo, P.WhileStmtContext):
                self.evaluar(nodo.expression())
                if not self.vivo:
                    return
                # No se deducen condiciones literales: puede resultar falsa.
                salidas.append(deepcopy(self.estados))
            marco = {'break': [], 'continue': []}
            self.ciclos.append(marco)
            try:
                self.evaluar(nodo.block(), True)
            finally:
                self.ciclos.pop()
            repeticiones = marco['continue'][:]
            if self.vivo:
                repeticiones.append(deepcopy(self.estados))
            salidas.extend(marco['break'])
            siguiente = self.unir([entrada] + repeticiones)
            if siguiente == cabecera:
                self.estados = self.unir(salidas)
                self.vivo = bool(salidas)
                return
            cabecera = siguiente

    def evaluar(self, nodo, transferir=False):
        """Recorre en orden de evaluación; un salto detiene el camino actual."""
        if nodo is None or not self.vivo:
            return
        if isinstance(nodo, P.BlockContext):
            for sentencia in nodo.statement():
                self.evaluar(sentencia, True)
            # La expresión final entrega el valor del bloque, incluso si
            # después se descarta; un identificador Move se transfiere aquí.
            self.evaluar(nodo.expression(), True)
            return
        if isinstance(nodo, P.LetDeclContext):
            expresion = nodo.expression()
            self.evaluar(expresion, True)
            identificador = self.declaraciones.get(nodo)
            if self.vivo and identificador is not None:
                self.estados[identificador] = {
                    'disponible' if expresion is not None else 'sin inicializar'
                }
            return
        if isinstance(nodo, P.AssignmentContext):
            identificador = self.referencias[nodo]
            parcial = bool(nodo.indexAccess() or nodo.tupleAccess() or nodo.fieldAccess())
            if parcial or nodo.assignmentOp().getText() != '=':
                self.usar(identificador, nodo.IDENT().getSymbol())
            for acceso in nodo.indexAccess():
                self.evaluar(acceso.expression())
            self.evaluar(nodo.expression(), True)
            if self.vivo and not parcial:
                # Las reglas de mutabilidad ya fueron comprobadas. Reemplazar
                # todo el valor permite reinicializar una variable movida.
                self.estados[identificador] = {'disponible'}
            return
        if isinstance(nodo, P.ReturnStmtContext):
            self.evaluar(nodo.expression(), True)
            self.vivo = False
            return
        if isinstance(nodo, (P.BreakStmtContext, P.ContinueStmtContext)):
            if self.ciclos:
                clase = 'break' if isinstance(nodo, P.BreakStmtContext) else 'continue'
                self.ciclos[-1][clase].append(deepcopy(self.estados))
            self.vivo = False
            return
        if isinstance(nodo, P.IfStmtContext):
            self.evaluar(nodo.expression())
            if self.vivo:
                alternativa = nodo.ifStmt() if nodo.ifStmt() is not None else (
                    nodo.block(1) if nodo.ELSE() is not None else None
                )
                self.evaluar_ramas([(None, nodo.block(0)), (None, alternativa)])
            return
        if isinstance(nodo, (P.WhileStmtContext, P.LoopStmtContext)):
            self.evaluar_ciclo(nodo)
            return
        if isinstance(nodo, P.MatchExprContext):
            # Match por valor consume el valor completo. No se mantiene un
            # propietario parcialmente movido al extraer datos del patrón.
            self.evaluar(nodo.expression(), True)
            if self.vivo:
                self.evaluar_ramas([(b.pattern(), b.expression()) for b in nodo.matchArm()])
            return
        if isinstance(nodo, P.FunctionCallContext):
            lista = nodo.argumentList()
            for argumento in lista.expression() if lista is not None else []:
                self.evaluar(argumento, True)
            return
        if isinstance(nodo, (P.ArrayLiteralContext, P.TupleLiteralContext)):
            for expresion in nodo.expression():
                self.evaluar(expresion, True)
            return
        if isinstance(nodo, P.StructLiteralContext):
            for campo in nodo.fieldInit():
                self.evaluar(campo.expression(), True)
            return
        if isinstance(nodo, P.EnumValueContext):
            lista = nodo.argumentList()
            for argumento in lista.expression() if lista is not None else []:
                self.evaluar(argumento, True)
            return
        if isinstance(nodo, P.PostfixContext):
            accesos = list(accesos_lectura(nodo))
            self.evaluar(nodo.primary(), transferir if not accesos else False)
            for clase, acceso in accesos:
                if clase == 'indice':
                    self.evaluar(acceso)
            if self.vivo and accesos and transferir and self.clase(self.tipos.get(nodo)) == 'Move':
                self.reportar(nodo.start, 'No se permite mover parcialmente un campo o elemento; mové el valor completo.')
            return
        if isinstance(nodo, P.PrimaryContext) and nodo.IDENT() is not None:
            self.usar(self.referencias[nodo], nodo.IDENT().getSymbol(), transferir)
            return
        if isinstance(nodo, (P.LogicalAndContext, P.LogicalOrContext)):
            operandos = nodo.comparison() if isinstance(nodo, P.LogicalAndContext) else nodo.logicalAnd()
            if len(operandos) == 1:
                self.evaluar(operandos[0], transferir)
                return
            self.evaluar(operandos[0])
            for operando in operandos[1:]:
                if not self.vivo:
                    break
                omitido = deepcopy(self.estados)
                self.evaluar(operando)
                caminos = [omitido] + ([self.estados] if self.vivo else [])
                self.estados = self.unir(caminos)
                self.vivo = True
            return
        # Los envoltorios sin operador conservan el contexto de transferencia.
        # Aritmética, comparación y negación solo leen sus operandos.
        hijos = [h for h in nodo.getChildren() if hasattr(h, 'getChildren')]
        operar = isinstance(nodo, (P.AdditiveContext, P.MultiplicativeContext, P.ComparisonContext, P.UnaryContext)) and nodo.getChildCount() > 1
        for hijo in hijos:
            self.evaluar(hijo, transferir if not operar else False)
