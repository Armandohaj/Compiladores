# Patrones usados en compilación: coincidencia con valores constantes y recolección de
# dependencias respetando ámbitos.
"""Ayudas para patrones y dependencias léxicas durante la compilación."""
from generated.RustiQParser import RustiQParser as P


def nombres_patron(ctx):
    """Extrae receptores; nombres de enums y variantes no son variables."""
    if ctx.DOUBLE_COLON() is not None:
        lista = ctx.patternList()
        hijos = lista.pattern() if lista is not None else []
    elif ctx.LPAREN() is not None:
        hijos = ctx.pattern()
    else:
        return {ctx.IDENT(0).getText()} if ctx.IDENT() else set()
    resultado = set()
    for hijo in hijos:
        resultado.update(nombres_patron(hijo))
    return resultado


def dependencias_globales(nodo, locales=frozenset()):
    """Encuentra constantes globales sin confundirlas con receptores o lets.

    Recorre todos los brazos, incluso los que no se seleccionarán, para
    conservar la detección de ciclos de dependencias del compilador.
    """
    if isinstance(nodo, P.PrimaryContext) and nodo.IDENT() is not None:
        token = nodo.IDENT().getSymbol()
        if token.text not in locales:
            yield token
        return
    if isinstance(nodo, P.MatchExprContext):
        yield from dependencias_globales(nodo.expression(), locales)
        for brazo in nodo.matchArm():
            yield from dependencias_globales(
                brazo.expression(), locales | nombres_patron(brazo.pattern())
            )
        return
    if isinstance(nodo, P.BlockContext):
        visibles = set(locales)
        for sentencia in nodo.statement():
            declaracion = sentencia.letDecl()
            if declaracion is not None:
                if declaracion.expression() is not None:
                    yield from dependencias_globales(declaracion.expression(), visibles)
                # El inicializador ve el ámbito previo a la nueva declaración.
                visibles.add(declaracion.IDENT().getText())
            else:
                yield from dependencias_globales(sentencia, visibles)
        if nodo.expression() is not None:
            yield from dependencias_globales(nodo.expression(), visibles)
        return
    for hijo in nodo.getChildren():
        if hasattr(hijo, 'getChildren'):
            yield from dependencias_globales(hijo, locales)


def coincidir(evaluador, patron, valor):
    """Devuelve las variables capturadas, o None cuando el patrón no coincide."""
    if patron.UNDERSCORE() is not None:
        return {}
    literal = patron.patternLiteral()
    if literal is not None:
        texto = literal.getText()
        if literal.INT() is not None:
            esperado = int(texto)
        elif literal.FLOAT() is not None:
            esperado = float(texto)
        elif literal.TRUE() is not None or literal.FALSE() is not None:
            esperado = literal.TRUE() is not None
        else:
            esperado = evaluador.decodificar_texto(texto)
        return {} if valor == esperado else None
    if patron.DOUBLE_COLON() is not None:
        nombre, variante = [n.getText() for n in patron.IDENT()]
        if not isinstance(valor, dict) or valor.get('enumeracion') != nombre or valor.get('variante') != variante:
            return None
        lista = patron.patternList()
        hijos = lista.pattern() if lista is not None else []
        valores = valor.get('datos', [])
    elif patron.LPAREN() is not None:
        if not isinstance(valor, tuple):
            return None
        hijos, valores = patron.pattern(), valor
    else:
        return {patron.IDENT(0).getText(): valor}
    if len(hijos) != len(valores):
        return None
    capturas = {}
    for hijo, dato in zip(hijos, valores):
        interior = coincidir(evaluador, hijo, dato)
        if interior is None:
            return None
        capturas.update(interior)
    return capturas
