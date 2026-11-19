"""Clasificación Copy/Move acordada para RustiQ.

Este módulo solo clasifica tipos. No realiza copias, movimientos ni préstamos.
Utiliza los tipos canónicos y los registros existentes del frontend.
"""
from tipos_compuestos import separar_tipo_tupla


def clasificar_tipo(tipo, estructuras, enumeraciones, visitando=None):
    """Devuelve Copy, Move o None si el tipo no permite decidir con seguridad.

    None no significa Move: indica un tipo desconocido, unit o una dependencia
    recursiva inválida. La validación de tipos del frontend debe diagnosticar
    esos casos antes de aplicar reglas de propiedad.
    """
    if tipo in ('i32', 'f64', 'bool', 'char'):
        return 'Copy'
    if tipo == 'String':
        return 'Move'
    if not isinstance(tipo, str) or tipo == 'unit':
        return None

    # Una ruta de tipos evita recursión infinita en registros inválidos.
    # No es una caché: otras ramas pueden compartir el mismo tipo válido.
    visitando = frozenset() if visitando is None else visitando
    if tipo in visitando:
        return None
    ruta = visitando | {tipo}

    if tipo.startswith('[') and tipo.endswith(']'):
        contenido = tipo[1:-1]
        if ';' not in contenido:
            return None
        elemento, cantidad = contenido.rsplit(';', 1)
        if not cantidad.isdigit():
            return None
        # Incluso [String;0] se clasifica por su tipo de elemento.
        # No se inspeccionan valores concretos ni tamaños en ejecución.
        componentes = [elemento]
    else:
        componentes = separar_tipo_tupla(tipo)
        if componentes is None:
            if tipo in estructuras:
                componentes = list(estructuras[tipo].values())
            elif tipo in enumeraciones:
                registro = enumeraciones[tipo]
                datos = registro.get('datos_variantes', {})
                # Cuenta el tipo completo del enum: se revisan TODAS sus
                # variantes, no solo la utilizada por un valor concreto.
                componentes = [
                    dato
                    for variante in registro['variantes']
                    for dato in datos.get(variante, [])
                ]
            else:
                return None

    clases = [
        clasificar_tipo(componente, estructuras, enumeraciones, ruta)
        for componente in componentes
    ]
    # Un registro incompleto no se convierte silenciosamente en Move.
    if any(clase is None for clase in clases):
        return None
    return 'Move' if 'Move' in clases else 'Copy'
