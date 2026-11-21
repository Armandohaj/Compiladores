"""
Registro de enumeraciones y datos asociados a sus variantes.

Ejemplo:
enum Resultado {
    Correcto(i32),
    Error(String),
    Vacio
}
"""

from generated.RustiQParser import RustiQParser


class GestorEnumeraciones:
    """Registra variantes, etiquetas y tipos de datos asociados."""

    def __init__(self, semantico):
        self.semantico = semantico
        self.enumeraciones = {}

    def registrar(self, programa):
        """
        Devuelve el registro de enumeraciones.

        Conserva el mapa de etiquetas anterior.
        Si un enum tiene variantes con datos, agrega también
        el mapa datos_variantes.
        """

        otras_declaraciones = (
            programa.functionDecl()
            + programa.constDecl()
            + programa.structDecl()
        )

        otros_nombres = {
            declaracion.IDENT().getText()
            for declaracion in otras_declaraciones
        }

        for ctx in programa.enumDecl():
            token = ctx.IDENT().getSymbol()
            nombre = token.text

            if nombre in self.enumeraciones:
                self.semantico.reportar(
                    token,
                    f"La enumeración '{nombre}' ya fue declarada."
                )
                continue

            if nombre in otros_nombres:
                self.semantico.reportar(
                    token,
                    f"El nombre de enumeración '{nombre}' "
                    "ya pertenece a otra declaración global."
                )

            etiquetas = {}
            datos_variantes = {}

            for posicion, variante in enumerate(ctx.variantDecl()):
                token_variante = variante.IDENT().getSymbol()
                nombre_variante = token_variante.text

                if nombre_variante in etiquetas:
                    self.semantico.reportar(
                        token_variante,
                        f"La variante '{nombre_variante}' "
                        f"ya fue declarada en '{nombre}'."
                    )
                    continue

                # La etiqueta identifica qué variante contiene el valor.
                etiquetas[nombre_variante] = posicion

                lista_tipos = variante.variantTypeList()

                if lista_tipos is None:
                    # Variante sin datos, como Vacio.
                    tipos = []
                else:
                    # Obtener los nodos de tipo sin depender
                    # del nombre que ANTLR asigne al método type.
                    nodos = lista_tipos.getTypedRuleContexts(
                        RustiQParser.TypeContext
                    )

                    tipos = [
                        self.semantico.normalizar_tipo(nodo)
                        for nodo in nodos
                    ]

                # Ejemplo: Coordenada(i32, i32)
                # queda registrada como ["i32", "i32"].
                datos_variantes[nombre_variante] = tipos

            registro = {
                "variantes": etiquetas,
            }

            # Mantener el formato anterior en enums sin datos.
            # Esto conserva las pruebas del bloque anterior.
            if any(datos_variantes.values()):
                registro["datos_variantes"] = datos_variantes

            self.enumeraciones[nombre] = registro

        return self.enumeraciones