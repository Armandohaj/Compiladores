"""Describe cómo puede terminar un nodo del árbol ANTLR.

normal: continúa y puede producir un valor; return: termina la función;
break/continue: transfieren el control al ciclo más cercano.
No se ejecuta código ni se agrega otro árbol para el backend.
"""
from generated.RustiQParser import RustiQParser as P


def secuencia(nodos):
    """Compone evaluaciones en orden; un salto impide ejecutar las siguientes."""
    salidas = {'normal'}
    for nodo in nodos:
        if 'normal' not in salidas:
            break
        salidas = (salidas - {'normal'}) | salidas_control(nodo)
    return salidas


def salidas_control(nodo):
    """Calcula salidas posibles conservadoramente, sin deducir condiciones literales."""
    if nodo is None:
        return {'normal'}
    if isinstance(nodo, P.ReturnStmtContext):
        previas = salidas_control(nodo.expression())
        return (previas - {'normal'}) | ({'return'} if 'normal' in previas else set())
    if isinstance(nodo, P.BreakStmtContext):
        return {'break'}
    if isinstance(nodo, P.ContinueStmtContext):
        return {'continue'}
    if isinstance(nodo, P.BlockContext):
        nodos = list(nodo.statement())
        if nodo.expression() is not None:
            nodos.append(nodo.expression())
        return secuencia(nodos)
    if isinstance(nodo, P.IfStmtContext):
        condicion = salidas_control(nodo.expression())
        ramas = salidas_control(nodo.block(0))
        if nodo.ifStmt() is not None:
            ramas |= salidas_control(nodo.ifStmt())
        elif nodo.ELSE() is not None:
            ramas |= salidas_control(nodo.block(1))
        else:
            ramas.add('normal')
        return (condicion - {'normal'}) | (ramas if 'normal' in condicion else set())
    if isinstance(nodo, P.MatchExprContext):
        valor = salidas_control(nodo.expression())
        ramas = set()
        for brazo in nodo.matchArm():
            ramas |= salidas_control(brazo.expression())
        # Solo se usa como garantía después de validar exhaustividad.
        return (valor - {'normal'}) | (ramas if 'normal' in valor else set())
    if isinstance(nodo, (P.WhileStmtContext, P.LoopStmtContext)):
        # El ciclo consume sus propios break/continue. Conservamos la regla
        # anterior: por sí solo no garantiza que una función retorne.
        cuerpo = salidas_control(nodo.block())
        ciclo = {'normal'} | (cuerpo & {'return'})
        if isinstance(nodo, P.WhileStmtContext):
            condicion = salidas_control(nodo.expression())
            return (condicion - {'normal'}) | (ciclo if 'normal' in condicion else set())
        return ciclo
    if isinstance(nodo, (P.LogicalAndContext, P.LogicalOrContext)):
        operandos = nodo.comparison() if isinstance(nodo, P.LogicalAndContext) else nodo.logicalAnd()
        salidas = salidas_control(operandos[0])
        for operando in operandos[1:]:
            if 'normal' in salidas:
                # Siempre existe el camino conservador que omite la derecha.
                salidas |= salidas_control(operando)
        return salidas
    return secuencia([
        hijo for hijo in nodo.getChildren() if hasattr(hijo, 'getChildren')
    ])
