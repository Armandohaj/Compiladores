# Validación de patrones y exhaustividad. Las estructuras temporales de cobertura no
# reemplazan el árbol ANTLR y no son un AST público del compilador.
"""Patrones y exhaustividad sobre el árbol ANTLR, sin construir otro AST.

Las descripciones temporales de cobertura solo sirven para comprobar casos;
no sustituyen los nodos del compilador ni se entregan al backend.
"""
from copy import deepcopy
from flujo_control import salidas_control
from tipos_compuestos import separar_tipo_tupla


def constructores(tipo, enumeraciones):
    """Enumera las formas de un tipo finito; None indica dominio abierto."""
    if tipo == 'bool':
        return [('true', []), ('false', [])]
    campos = separar_tipo_tupla(tipo)
    if campos is not None:
        return [('tupla', campos)]
    if tipo in enumeraciones:
        enum = enumeraciones[tipo]
        datos = enum.get('datos_variantes', {})
        return [(nombre, datos.get(nombre, [])) for nombre in enum['variantes']]
    return None


def cubre_todo(filas, tipos, enumeraciones):
    """Especializa una matriz de patrones para buscar combinaciones sin cubrir.

    None representa un comodín o una variable receptora. Al separar las
    columnas se comprueban también combinaciones de tuplas y datos de enums;
    mencionar una variante con un patrón restrictivo no la cubre por completo.
    """
    # La matriz contiene una fila por patrón y columnas por componentes. Se descompone
    # recursivamente para comprobar datos anidados: mencionar E::Dato(true) no cubre
    # E::Dato(false).
    if not tipos:
        return bool(filas)
    if not filas:
        return False
    # Una fila representa un brazo y cada columna un componente a cubrir.
    # Para bool comprobamos true/false; para enums cada variante y sus datos.
    # E::Dato(true) no cubre E::Dato(false), aunque mencione la variante.
    formas = constructores(tipos[0], enumeraciones)
    if formas is None:
        # Un conjunto finito de literales no cubre un dominio abierto.
        return cubre_todo([f[1:] for f in filas if f[0] is None], tipos[1:], enumeraciones)
    for nombre, interiores in formas:
        especializadas = []
        for fila in filas:
            patron = fila[0]
            if patron is None:
                especializadas.append([None] * len(interiores) + fila[1:])
            elif patron[0] == nombre:
                especializadas.append(patron[1] + fila[1:])
        if not cubre_todo(especializadas, interiores + tipos[1:], enumeraciones):
            return False
    return True


def comprobar_patron(sem, ctx, esperado, nombres):
    """Valida recursivamente y declara las variables del brazo como inmutables."""
    sem.guardar_tipo(ctx, esperado)
    if ctx.UNDERSCORE() is not None:
        return None
    literal = ctx.patternLiteral()
    if literal is not None:
        if literal.INT() is not None:
            tipo = 'i32'
            valor = int(literal.getText())
            if not -(2**31) <= valor < 2**31:
                sem.reportar(literal.start, 'Literal de patrón fuera del rango i32.')
        elif literal.FLOAT() is not None:
            tipo = 'f64'
        elif literal.TRUE() is not None or literal.FALSE() is not None:
            tipo = 'bool'
        elif literal.CHAR_LITERAL() is not None:
            tipo = 'char'
        else:
            tipo = 'String'
        sem.guardar_tipo(literal, tipo)
        if esperado is not None and tipo != esperado:
            sem.reportar(literal.start, f'Patrón incompatible: se esperaba {esperado}, pero se recibió {tipo}.')
        return (literal.getText(), [])
    if ctx.DOUBLE_COLON() is not None:
        enum, variante = [n.getText() for n in ctx.IDENT()]
        registro = sem.enumeraciones.get(enum)
        lista = ctx.patternList()
        hijos = lista.pattern() if lista is not None else []
        if registro is None or variante not in registro['variantes']:
            sem.reportar(ctx.start, f"Variante de patrón desconocida: '{enum}::{variante}'.")
            return ('invalido', [])
        if esperado is not None and enum != esperado:
            sem.reportar(ctx.start, f'Patrón incompatible: se esperaba {esperado}, pero se recibió {enum}.')
        tipos = registro.get('datos_variantes', {}).get(variante, [])
        if len(hijos) != len(tipos) or (not tipos and ctx.LPAREN() is not None):
            sem.reportar(ctx.start, f"La variante '{variante}' requiere {len(tipos)} patrones de datos.")
        return (variante, [comprobar_patron(sem, h, t, nombres) for h, t in zip(hijos, tipos)])
    if ctx.LPAREN() is not None:
        tipos = separar_tipo_tupla(esperado)
        hijos = ctx.pattern()
        if tipos is None or len(tipos) != len(hijos):
            sem.reportar(ctx.start, 'El patrón de tupla debe coincidir con el tipo y la cantidad de elementos.')
            return ('invalido', [])
        return ('tupla', [comprobar_patron(sem, h, t, nombres) for h, t in zip(hijos, tipos)])
    # IDENT es una lista porque la alternativa de variante tiene dos nombres.
    token = ctx.IDENT(0).getSymbol()
    if token.text in nombres:
        sem.reportar(token, f"La variable de patrón '{token.text}' está repetida.")
    elif not sem.nombre_incorporado(token):
        nombres.add(token.text)
        sem.ambitos[-1][token.text] = {
            'tipo': esperado, 'mutable': False,
            'inicializada': True, 'puede_inicializada': True,
        }
    return None


def analizar_match(sem, ctx):
    """Analiza cada brazo desde el mismo estado y une su inicialización."""
    # Se tipan todos los brazos, pero en ejecución se elige el primero compatible. Los
    # brazos sin continuación normal no aportan un valor al tipo del match ni a la
    # inicialización posterior.
    inicio = len(sem.errores)
    tipo = sem.visit(ctx.expression())
    if isinstance(tipo, str) and tipo.startswith('&'):
        # No se inventa una procedencia para receptores de patrones referencia.
        # Esta etapa admite match de valores, no patrones sobre referencias.
        sem.reportar(ctx.start, "Esta versión no admite patrones sobre referencias.")

    # Evaluar el valor del match puede tener efectos sobre las variables.
    # Ese estado, anterior a seleccionar un brazo, es el punto de partida.
    originales = sem.ambitos
    inicial = deepcopy(originales)
    estados = []
    filas = []
    resultado = None

    try:
        for brazo in ctx.matchArm():
            # Ningún brazo hereda las asignaciones de otro.
            sem.ambitos = deepcopy(inicial)
            sem.ambitos.append({})
            try:
                patron = comprobar_patron(sem, brazo.pattern(), tipo, set())
                filas.append([patron])
                # Todos los brazos producen el valor esperado por el match.
                recibido = sem.visitar_con_tipo(
                    brazo.expression(), sem.tipos_esperados.get(ctx)
                )
                sem.guardar_tipo(brazo, recibido)
                # Un brazo que hace return no entrega un valor al match ni
                # llega a la instrucción siguiente. No exigirle el mismo tipo
                # de resultado que a un brazo que sí continúa.
                continua = 'normal' in salidas_control(brazo.expression())
                if continua and resultado is None:
                    resultado = recibido
                elif continua and recibido is not None and recibido != resultado:
                    sem.reportar(
                        brazo.expression().start,
                        f'Brazos de match incompatibles: {resultado} y {recibido}.',
                    )
            finally:
                # Los receptores del patrón no salen de su brazo.
                sem.ambitos.pop()
            # Solo los caminos que continúan afectan las variables posteriores.
            if continua:
                estados.append(deepcopy(sem.ambitos))
    finally:
        # Conservar los diccionarios originales: una declaración que está
        # analizando su inicializador puede mantener una referencia a ellos.
        sem.ambitos = originales

    if tipo is not None and len(sem.errores) == inicio:
        if not cubre_todo(filas, [tipo], sem.enumeraciones):
            sem.reportar(
                ctx.start,
                'El match no es exhaustivo: faltan valores o variantes por cubrir.',
            )

    # Solo un match válido permite establecer garantías posteriores.
    # Conservadoramente se consideran todos los brazos, aunque alguno
    # pueda ser redundante. salidas_control determina qué brazos continúan;
    # esta fase no diagnostica brazos redundantes ni deduce todos los valores.
    if len(sem.errores) == inicio and estados:
        for indice, ambito in enumerate(sem.ambitos):
            for nombre, variable in ambito.items():
                alternativas = [estado[indice][nombre] for estado in estados]
                variable['inicializada'] = all(
                    alternativa['inicializada'] for alternativa in alternativas
                )
                variable['puede_inicializada'] = any(
                    alternativa['puede_inicializada'] for alternativa in alternativas
                )

    return sem.guardar_tipo(
        ctx, (resultado or 'unit') if len(sem.errores) == inicio else None
    )
