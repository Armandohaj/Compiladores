"""Registro de tipos nominales y validación de sus declaraciones.

Se ejecuta antes de analizar constantes y funciones para permitir que
un tipo sea utilizado antes de aparecer su declaración en el archivo.
"""
from generated.RustiQParser import RustiQParser


class GestorEstructuras:
    """Comprueba campos, tipos conocidos y ciclos de tipos por valor."""

    def __init__(self, semantico):
        self.semantico = semantico
        self.declaraciones = {}
        self.estructuras = {}

    def recorrer(self, nodo):
        """Recorre nodos del árbol original; no construye otro AST."""
        yield nodo
        for hijo in nodo.getChildren():
            if hasattr(hijo, "getChildren"):
                yield from self.recorrer(hijo)

    def registrar(self, programa):
        """Devuelve nombre -> campos; cada campo conserva su tipo canónico."""
        otros = {n.IDENT().getText() for n in programa.functionDecl() + programa.constDecl()}
        for ctx in programa.structDecl():
            token = ctx.IDENT().getSymbol()
            nombre = token.text
            if nombre in self.estructuras:
                self.semantico.reportar(token, f"La estructura '{nombre}' ya fue declarada.")
                continue
            if nombre in otros:
                self.semantico.reportar(token, f"El nombre de estructura '{nombre}' ya pertenece a una función o constante.")
            campos = {}
            for campo in ctx.fieldDecl():
                identificador = campo.IDENT().getSymbol()
                if identificador.text in campos:
                    self.semantico.reportar(identificador, f"El campo '{identificador.text}' ya fue declarado en '{nombre}'.")
                else:
                    campos[identificador.text] = self.semantico.obtener_tipo_declarado(campo)
            self.estructuras[nombre] = campos
            self.declaraciones[nombre] = ctx
        return self.estructuras

    def validar(self, programa):
        """Rechaza tipos desconocidos y definiciones recursivas por valor.

        Todavía no existen referencias en el lenguaje implementado.
        Se rechazan ciclos incluso a través de tuplas o arreglos.
        """
        for nodo in self.recorrer(programa):
            if isinstance(nodo, RustiQParser.TypeContext) and nodo.IDENT() is not None:
                token = nodo.IDENT().getSymbol()
                if token.text not in self.estructuras:
                    self.semantico.reportar(token, f"El tipo '{token.text}' no está declarado.")

        dependencias = {}
        for nombre, ctx in self.declaraciones.items():
            dependencias[nombre] = {
                nodo.IDENT().getText()
                for campo in ctx.fieldDecl()
                for nodo in self.recorrer(campo)
                if isinstance(nodo, RustiQParser.TypeContext)
                and nodo.IDENT() is not None
                and nodo.IDENT().getText() in self.estructuras
            }
        visitados = set()
        activos = set()

        def revisar(nombre):
            if nombre in activos:
                self.semantico.reportar(
                    self.declaraciones[nombre].IDENT().getSymbol(),
                    f"La estructura '{nombre}' tiene una dependencia recursiva por valor."
                )
                return
            if nombre in visitados:
                return
            activos.add(nombre)
            for dependencia in sorted(dependencias[nombre]):
                revisar(dependencia)
            activos.remove(nombre)
            visitados.add(nombre)

        for nombre in self.estructuras:
            revisar(nombre)
