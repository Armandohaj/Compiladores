from generated.RustiQParser import RustiQParser
from evaluador_constantes import EvaluadorConstantes, ErrorConstante


class GestorConstantes:
    """Registra, valida y calcula las constantes globales."""

    def __init__(self, semantico):
        self.semantico = semantico

        # Nombre -> nodo de declaración.
        self.declaraciones = {}

        # Nombre -> información semántica.
        self.simbolos = {}

        # Nombre -> valor calculado.
        self.valores = {}

        # Constantes que estamos calculando actualmente.
        # Sirve para detectar dependencias circulares.
        self.en_proceso = set()

    def recorrer(self, nodo):
        yield nodo

        for hijo in nodo.getChildren():
            if hasattr(hijo, "getChildren"):
                yield from self.recorrer(hijo)

    # =================================================
    # 1. REGISTRO
    # =================================================

    def registrar(self, declaraciones):
        for ctx in declaraciones:
            token = ctx.IDENT().getSymbol()
            nombre = token.text

            if nombre in self.simbolos:
                self.semantico.reportar(
                    token,
                    f"La constante '{nombre}' ya fue declarada."
                )
                continue

            if nombre in self.semantico.funciones:
                self.semantico.reportar(
                    token,
                    f"El nombre '{nombre}' ya pertenece "
                    "a una función."
                )
                continue

            self.declaraciones[nombre] = ctx
            self.simbolos[nombre] = {
                "tipo": self.semantico.obtener_tipo_declarado(ctx),
                "mutable": False,
                "inicializada": True,
                "puede_inicializada": True,
                "es_constante": True,
            }

    # =================================================
    # 2. VALIDACIÓN DE TIPOS Y EXPRESIONES
    # =================================================

    def validar_y_calcular(self):
        errores_antes = len(self.semantico.errores)

        for nombre, ctx in self.declaraciones.items():
            # Revisar todos los nodos, aunque un operador
            # lógico pueda omitirlos al calcular el valor.
            for nodo in self.recorrer(ctx.expression()):
                if isinstance(nodo, RustiQParser.FunctionCallContext):
                    self.semantico.reportar(
                        nodo.IDENT().getSymbol(),
                        "Una constante no puede inicializarse "
                        "con una llamada a función."
                    )

            esperado = self.simbolos[nombre]["tipo"]
            tipo = self.semantico.visitar_con_tipo(ctx.expression(), esperado)

            if tipo is not None and tipo != esperado:
                self.semantico.reportar(
                    ctx.IDENT().getSymbol(),
                    f"Tipos incompatibles en la constante '{nombre}': "
                    f"se esperaba {esperado}, pero se recibió {tipo}."
                )

        # No calcular expresiones con errores de tipos.
        if len(self.semantico.errores) != errores_antes:
            return

        for nombre, ctx in self.declaraciones.items():
            try:
                self.calcular(ctx.IDENT().getSymbol())
            except ErrorConstante as error:
                self.semantico.reportar(error.token, error.mensaje)

    # =================================================
    # 3. DEPENDENCIAS Y VALORES
    # =================================================

    def calcular(self, token):
        nombre = token.text

        if nombre in self.valores:
            return self.valores[nombre]

        if nombre not in self.declaraciones:
            raise ErrorConstante(
                token,
                f"La constante '{nombre}' no está declarada."
            )

        if nombre in self.en_proceso:
            raise ErrorConstante(
                token,
                f"Dependencia circular en la constante '{nombre}'."
            )

        self.en_proceso.add(nombre)

        try:
            ctx = self.declaraciones[nombre]

            # Resolver primero todas las dependencias.
            # También detecta ciclos en ramas con cortocircuito.
            for nodo in self.recorrer(ctx.expression()):
                if (
                    isinstance(nodo, RustiQParser.PrimaryContext)
                    and nodo.IDENT() is not None
                ):
                    self.calcular(nodo.IDENT().getSymbol())

            evaluador = EvaluadorConstantes(
                self.semantico.tipos_expresiones,
                self.calcular,
            )

            valor = evaluador.visit(ctx.expression())

            evaluador.comprobar_rango(
                valor,
                self.simbolos[nombre]["tipo"],
                ctx.IDENT().getSymbol(),
            )

            self.valores[nombre] = valor
            return valor
        finally:
            self.en_proceso.remove(nombre)