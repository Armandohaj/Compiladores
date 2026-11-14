"""Utilidades compartidas para mantener iguales los tipos del semántico y backend."""
from generated.RustiQParser import RustiQParser


def normalizar_tipo(nodo):
    """Convierte un tipo de ANTLR en su representación canónica."""
    interiores = nodo.getTypedRuleContexts(RustiQParser.TypeContext)
    if nodo.LBRACKET() is not None:
        return f"[{normalizar_tipo(interiores[0])};{int(nodo.INT().getText())}]"
    if nodo.LPAREN() is not None:
        return "(" + ",".join(normalizar_tipo(t) for t in interiores) + ")"
    return nodo.getText()


def separar_tipo_tupla(tipo):
    """Separa solo comas exteriores: (i32,(bool,char)) tiene dos campos."""
    if tipo is None or not tipo.startswith("(") or not tipo.endswith(")"):
        return None
    campos = []
    inicio = 1
    profundidad = 0
    for indice, caracter in enumerate(tipo[1:-1], start=1):
        if caracter in "([":
            profundidad += 1
        elif caracter in ")]":
            profundidad -= 1
        elif caracter == "," and profundidad == 0:
            campos.append(tipo[inicio:indice])
            inicio = indice + 1
    campos.append(tipo[inicio:-1])
    return campos


def accesos_lectura(ctx):
    """Conserva el orden de accesos mezclados: matriz[0].1[2]."""
    for nodo in ctx.getChildren():
        if isinstance(nodo, RustiQParser.ExpressionContext):
            yield "indice", nodo
        elif isinstance(nodo, RustiQParser.TupleAccessContext):
            yield "campo", nodo
        elif isinstance(nodo, RustiQParser.FieldAccessContext):
            yield "nombre", nodo


def accesos_escritura(ctx):
    """No incluye la expresión derecha de la asignación."""
    for nodo in ctx.getChildren():
        if isinstance(nodo, RustiQParser.IndexAccessContext):
            yield "indice", nodo
        elif isinstance(nodo, RustiQParser.TupleAccessContext):
            yield "campo", nodo
        elif isinstance(nodo, RustiQParser.FieldAccessContext):
            yield "nombre", nodo
