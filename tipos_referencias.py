"""Tipos fuente de referencias y destinos simples del préstamo inicial."""
from generated.RustiQParser import RustiQParser as P


def separar_referencia(tipo):
    """Devuelve (mutable, tipo_prestado) o None; no convierte tipos a i32."""
    if not isinstance(tipo, str):
        return None
    if tipo.startswith('&mut '):
        return True, tipo[5:]
    if tipo.startswith('&'):
        return False, tipo[1:]
    return None


def identificador_simple(nodo):
    """Encuentra x o (x); rechaza campos, índices, llamadas y operaciones."""
    while nodo is not None:
        if isinstance(nodo, P.PrimaryContext):
            if nodo.IDENT() is not None:
                return nodo
            nodo = nodo.expression()
        elif isinstance(nodo, P.PostfixContext):
            if nodo.getChildCount() != 1:
                return None
            nodo = nodo.primary()
        elif isinstance(nodo, P.UnaryContext):
            if nodo.getChildCount() != 1 or nodo.postfix() is None:
                return None
            nodo = nodo.postfix()
        elif nodo.getChildCount() == 1 and hasattr(nodo.getChild(0), 'getChildren'):
            nodo = nodo.getChild(0)
        else:
            return None
    return None
