"""Backend WebAssembly mínimo para el subconjunto aritmético de RustiQ."""

from __future__ import annotations

from dataclasses import dataclass

import wasmtime

from main import analizar_programa


TAMANO_PAGINA_WASM = 65536
MAX_PAGINAS_MEMORIA = 65536
MAX_DIRECCION_I32 = 2**32 - 1


class MemoriaStrings:
    def __init__(self):
        self.cursor = 0
        self.segmentos = []

    def agregar(self, texto, contexto):
        datos = texto.encode("utf-8")
        descriptor = self.cursor
        inicio = descriptor + 8
        total = inicio + len(datos)
        if (
            descriptor > MAX_DIRECCION_I32
            or inicio > MAX_DIRECCION_I32
            or len(datos) > MAX_DIRECCION_I32
            or total > MAX_PAGINAS_MEMORIA * TAMANO_PAGINA_WASM
        ):
            _error("Los datos estáticos exceden el límite de memoria WebAssembly.", contexto)
        contenido = inicio.to_bytes(4, "little") + len(datos).to_bytes(4, "little") + datos
        self.segmentos.append((descriptor, contenido))
        self.cursor += len(contenido)
        return descriptor

    def paginas_necesarias(self):
        return max(1, (self.cursor + TAMANO_PAGINA_WASM - 1) // TAMANO_PAGINA_WASM)

    def wat(self):
        return "\n".join(
            f"  (data (i32.const {direccion}) \""
            f"{''.join(f'\\{byte:02x}' for byte in datos)}\")"
            for direccion, datos in self.segmentos
        )

@dataclass
class EstadoModulo:
    nombres_funcion: dict
    memoria: MemoriaStrings


@dataclass
class ErrorGeneracion(Exception):
    """Error controlado al encontrar sintaxis aún no soportada."""

    mensaje: str
    contexto: object

    def como_error(self):
        inicio = getattr(self.contexto, "start", None)
        if inicio is None:
            inicio = getattr(self.contexto, "symbol", None)
        return {
            "fase": "generacion",
            "mensaje": self.mensaje,
            "linea": inicio.line,
            "columna": inicio.column + 1,
        }


def _error(mensaje, contexto):
    raise ErrorGeneracion(mensaje, contexto)


def _tipo_wasm(tipo):
    return "i32" if tipo in {"bool", "char", "String"} or _info_arreglo(tipo) is not None else tipo


def _info_arreglo(tipo):
    if not tipo.startswith("[") or not tipo.endswith("]"):
        return None
    contenido = tipo[1:-1]
    if ";" not in contenido:
        return None
    elemento, tamano = contenido.rsplit(";", 1)
    if elemento not in {"i32", "bool", "char", "f64"} or not tamano.isdigit():
        return None
    return elemento, int(tamano)


def _tamano_elemento_arreglo(tipo):
    return 8 if tipo == "f64" else 4


def _instruccion_carga_arreglo(tipo):
    return "f64.load align=8" if tipo == "f64" else "i32.load"


def _instruccion_almacenamiento_arreglo(tipo, desplazamiento):
    alineacion = " align=8" if tipo == "f64" else ""
    return f"{tipo if tipo == 'f64' else 'i32'}.store offset={desplazamiento}{alineacion}"


def _valor_string(literal, contexto):
    contenido = literal[1:-1]
    escapes = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", '"': '"', "'": "'", "\\": "\\"}
    resultado = []
    indice = 0
    while indice < len(contenido):
        caracter = contenido[indice]
        if caracter != "\\":
            resultado.append(caracter)
            indice += 1
            continue
        if indice + 1 >= len(contenido) or contenido[indice + 1] not in escapes:
            _error("Literal String no soportado.", contexto)
        resultado.append(escapes[contenido[indice + 1]])
        indice += 2
    return "".join(resultado)


def _valor_char(literal, contexto):
    contenido = literal[1:-1]
    escapes = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "'": "'", '"': '"', "\\": "\\"}
    if contenido.startswith("\\"):
        if len(contenido) != 2 or contenido[1] not in escapes:
            _error("Literal char no soportado.", contexto)
        contenido = escapes[contenido[1]]
    if len(contenido) != 1:
        _error("Literal char inválido.", contexto)
    return ord(contenido)


def _compilar_expresion(expresion, referencias, locales, funciones, nombres_funcion, tipos):
    return _compilar_logical_or(
        expresion.logicalOr(), referencias, locales, funciones, nombres_funcion, tipos
    )


def _compilar_logical_or(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    operandos = contexto.logicalAnd()
    instrucciones = _compilar_logical_and(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    for operando in operandos[1:]:
        derecho = _compilar_logical_and(
            operando, referencias, locales, funciones, nombres_funcion, tipos
        )
        instrucciones.append(_wat_condicional(["i32.const 1"], derecho))
    return instrucciones


def _compilar_logical_and(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    operandos = contexto.comparison()
    instrucciones = _compilar_comparacion(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    for operando in operandos[1:]:
        derecho = _compilar_comparacion(
            operando, referencias, locales, funciones, nombres_funcion, tipos
        )
        instrucciones.append(_wat_condicional(derecho, ["i32.const 0"]))
    return instrucciones


def _compilar_comparacion(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    operandos = contexto.additive()
    instrucciones = _compilar_aditiva(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    if len(operandos) == 1:
        return instrucciones
    operador = contexto.relOp().getText()
    instrucciones.extend(
        _compilar_aditiva(operandos[1], referencias, locales, funciones, nombres_funcion, tipos)
    )
    tipo = tipos[operandos[0]]
    if _info_arreglo(tipo) is not None:
        _error("Las comparaciones entre arreglos todavía no están implementadas.", contexto)
    if tipo == "String":
        if operador not in {"==", "!="}:
            _error("Las cadenas solo admiten == y !=.", contexto)
        instrucciones.append("call $string_eq")
        if operador == "!=":
            instrucciones.append("i32.eqz")
        return instrucciones
    if tipo == "f64":
        instrucciones.append({
            "==": "f64.eq", "!=": "f64.ne", "<": "f64.lt",
            "<=": "f64.le", ">": "f64.gt", ">=": "f64.ge",
        }[operador])
    else:
        if tipo == "char" and operador not in {"==", "!="}:
            _error("Los caracteres solo admiten == y !=.", contexto)
        instrucciones.append({
            "==": "i32.eq", "!=": "i32.ne", "<": "i32.lt_s",
            "<=": "i32.le_s", ">": "i32.gt_s", ">=": "i32.ge_s",
        }[operador])
    return instrucciones


def _wat_condicional(rama_cierta, rama_falsa):
    """Construye un if con resultado i32; la condición ya está en la pila."""
    cierta = "\n        ".join(rama_cierta)
    falsa = "\n        ".join(rama_falsa)
    return (
        "(if (result i32)\n"
        f"      (then\n        {cierta}\n      )\n"
        f"      (else\n        {falsa}\n      )\n"
        "    )"
    )


def _wat_if(rama_cierta, rama_falsa=None):
    cierta = "\n        ".join(rama_cierta) if rama_cierta else "nop"
    wat = "(if\n" f"      (then\n        {cierta}\n      )"
    if rama_falsa is not None:
        falsa = "\n        ".join(rama_falsa) if rama_falsa else "nop"
        wat += f"\n      (else\n        {falsa}\n      )"
    return wat + "\n    )"


def _wat_string_eq():
    return """  (func $string_eq (param $izquierda i32) (param $derecha i32) (result i32)
    (local $puntero_izquierdo i32)
    (local $longitud_izquierda i32)
    (local $puntero_derecho i32)
    (local $longitud_derecha i32)
    (local $indice i32)
    local.get $izquierda
    i32.load
    local.set $puntero_izquierdo
    local.get $izquierda
    i32.const 4
    i32.add
    i32.load
    local.set $longitud_izquierda
    local.get $derecha
    i32.load
    local.set $puntero_derecho
    local.get $derecha
    i32.const 4
    i32.add
    i32.load
    local.set $longitud_derecha
    local.get $longitud_izquierda
    local.get $longitud_derecha
    i32.ne
    (if (then i32.const 0 return))
    (block $fin
      (loop $comparar
        local.get $indice
        local.get $longitud_izquierda
        i32.ge_u
        br_if $fin
        local.get $puntero_izquierdo
        local.get $indice
        i32.add
        i32.load8_u
        local.get $puntero_derecho
        local.get $indice
        i32.add
        i32.load8_u
        i32.ne
        (if (then i32.const 0 return))
        local.get $indice
        i32.const 1
        i32.add
        local.set $indice
        br $comparar
      )
    )
    i32.const 1
  )"""


def _wat_arreglos(inicio_heap):
    return f"""  (global $heap (mut i32) (i32.const {inicio_heap}))
  (func $array_alloc (param $tamano i32) (param $alineacion i32) (result i32)
    (local $base i32)
    (local $sin_alinear i32)
    (local $final i32)
    (local $paginas i32)
    global.get $heap
    local.tee $sin_alinear
    local.get $alineacion
    i32.const 1
    i32.sub
    i32.add
    local.tee $base
    local.get $sin_alinear
    i32.lt_u
    (if (then unreachable))
    local.get $base
    local.get $alineacion
    i32.const 1
    i32.sub
    i32.const -1
    i32.xor
    i32.and
    local.set $base
    local.get $base
    local.get $tamano
    i32.add
    local.tee $final
    local.get $base
    i32.lt_u
    (if (then unreachable))
    local.get $final
    global.set $heap
    local.get $final
    i32.const 16
    i32.shr_u
    local.set $paginas
    local.get $final
    i32.const 65535
    i32.and
    i32.eqz
    (if
      (then)
      (else
        local.get $paginas
        i32.const 1
        i32.add
        local.set $paginas
      )
    )
    local.get $paginas
    memory.size
    i32.gt_u
    (if
      (then
        local.get $paginas
        memory.size
        i32.sub
        memory.grow
        i32.const -1
        i32.eq
        (if (then unreachable))
      )
    )
    local.get $base
  )
  (func $array_addr (param $base i32) (param $indice i32) (param $tamano i32) (param $paso i32) (result i32)
    local.get $indice
    i32.const 0
    i32.lt_s
    (if (then unreachable))
    local.get $indice
    local.get $tamano
    i32.ge_u
    (if (then unreachable))
    local.get $base
    local.get $indice
    local.get $paso
    i32.mul
    i32.add
  )"""


def _compilar_aditiva(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    operandos = contexto.multiplicative()
    instrucciones = _compilar_multiplicativa(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(
            _compilar_multiplicativa(
                operando, referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        tipo = tipos[contexto]
        if tipo not in {"i32", "f64"}:
            _error("Esta operación aritmética no está disponible para el tipo.", contexto)
        instrucciones.append(f"{tipo}.{'add' if operador == '+' else 'sub'}")
    return instrucciones


def _compilar_multiplicativa(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    operandos = contexto.unary()
    instrucciones = _compilar_unaria(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(
            _compilar_unaria(operando, referencias, locales, funciones, nombres_funcion, tipos)
        )
        tipo = tipos[contexto]
        if tipo not in {"i32", "f64"}:
            _error("Esta operación aritmética no está disponible para el tipo.", contexto)
        if operador == "%" and tipo != "i32":
            _error("El operador '%' solo está disponible para i32.", contexto)
        instrucciones.append({
            "*": f"{tipo}.mul",
            "/": "i32.div_s" if tipo == "i32" else "f64.div",
            "%": "i32.rem_s",
        }[operador])
    return instrucciones


def _compilar_unaria(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    if contexto.getChildCount() == 1:
        return _compilar_postfija(
            contexto.postfix(), referencias, locales, funciones, nombres_funcion, tipos
        )
    operador = contexto.getChild(0).getText()
    if operador == "!":
        return [
            *_compilar_postfija(
                contexto.postfix(), referencias, locales, funciones, nombres_funcion, tipos
            ),
            "i32.eqz",
        ]

    postfija = contexto.postfix()
    if tipos[contexto] == "f64":
        return [
            *_compilar_postfija(
                postfija, referencias, locales, funciones, nombres_funcion, tipos
            ),
            "f64.neg",
        ]
    if tipos[contexto] != "i32":
        _error("La negación aritmética solo está disponible para i32 y f64.", contexto)
    primaria = postfija.primary() if postfija.getChildCount() == 1 else None
    literal = primaria.INT() if primaria is not None else None
    if literal is not None:
        valor = int(literal.getText())
        if valor == 2**31:
            return ["i32.const -2147483648"]
        if valor > 2**31 - 1:
            _error("El literal excede el rango de i32.", literal)

    return [
        "i32.const 0",
        *_compilar_postfija(
            postfija, referencias, locales, funciones, nombres_funcion, tipos
        ),
        "i32.sub",
    ]


def _compilar_postfija(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    instrucciones = _compilar_primaria(
        contexto.primary(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if contexto.getChildCount() == 1:
        return instrucciones
    arreglo = _info_arreglo(tipos[contexto.primary()])
    if arreglo is None or len(contexto.expression()) != 1:
        _error("Solo se admiten accesos a arreglos locales de una dimensión.", contexto)
    tipo_elemento, tamano = arreglo
    instrucciones.extend(
        _compilar_expresion(
            contexto.expression(0), referencias, locales, funciones, nombres_funcion, tipos
        )
    )
    instrucciones.extend(
        [
            f"i32.const {tamano}",
            f"i32.const {_tamano_elemento_arreglo(tipo_elemento)}",
            "call $array_addr",
            _instruccion_carga_arreglo(tipo_elemento),
        ]
    )
    return instrucciones


def _compilar_primaria(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    literal = contexto.INT()
    if literal is not None:
        valor = int(literal.getText())
        if valor > 2**31 - 1:
            _error("El literal excede el rango de i32.", contexto)
        return [f"i32.const {valor}"]
    decimal = contexto.FLOAT()
    if decimal is not None:
        return [f"f64.const {decimal.getText()}"]
    caracter = contexto.CHAR_LITERAL()
    if caracter is not None:
        return [f"i32.const {_valor_char(caracter.getText(), contexto)}"]
    cadena = contexto.STRING_LITERAL()
    if cadena is not None:
        return [
            f"i32.const {nombres_funcion.memoria.agregar(_valor_string(cadena.getText(), contexto), contexto)}"
        ]
    if contexto.TRUE() is not None:
        return ["i32.const 1"]
    if contexto.FALSE() is not None:
        return ["i32.const 0"]
    expresion = contexto.expression()
    if expresion is not None:
        return _compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        )
    if contexto.IDENT() is not None:
        identificador = referencias[contexto]
        if identificador not in locales:
            _error("La referencia no corresponde a una variable local i32.", contexto)
        return [f"local.get $local_{identificador}"]
    if contexto.functionCall() is not None:
        instrucciones, retorno = _compilar_llamada(
            contexto.functionCall(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if retorno == "unit":
            _error("Una función unit no puede usarse como expresión.", contexto)
        return instrucciones
    _error(
        "Solo se admiten literales i32 y expresiones aritméticas entre paréntesis.",
        contexto,
    )


def _obtener_literal_arreglo(expresion):
    or_logico = expresion.logicalOr()
    if len(or_logico.logicalAnd()) != 1:
        return None
    and_logico = or_logico.logicalAnd(0)
    if len(and_logico.comparison()) != 1:
        return None
    comparacion = and_logico.comparison(0)
    if len(comparacion.additive()) != 1:
        return None
    aditiva = comparacion.additive(0)
    if len(aditiva.multiplicative()) != 1:
        return None
    multiplicativa = aditiva.multiplicative(0)
    if len(multiplicativa.unary()) != 1:
        return None
    unaria = multiplicativa.unary(0)
    if unaria.getChildCount() != 1:
        return None
    postfija = unaria.postfix()
    if postfija.getChildCount() != 1:
        return None
    return postfija.primary().arrayLiteral()


def _compilar_declaracion(
    declaracion, declaraciones, simbolos, referencias, locales, funciones, nombres_funcion, tipos
):
    identificador = declaraciones[declaracion]
    if identificador not in locales:
        _error("La declaración no corresponde a una variable local i32.", declaracion)
    expresion = declaracion.expression()
    arreglo = _info_arreglo(simbolos[identificador]["tipo"])
    if arreglo is not None:
        tipo_elemento, tamano_arreglo = arreglo
        if expresion is None:
            _error("Un arreglo local requiere un literal para inicializarse.", declaracion)
        literal = _obtener_literal_arreglo(expresion)
        if literal is None:
            _error("Solo se admiten literales para inicializar arreglos locales.", expresion)
        elementos = literal.expression()
        if len(elementos) != tamano_arreglo:
            _error("El tamaño del literal no coincide con la declaración del arreglo.", literal)
        bytes_elemento = _tamano_elemento_arreglo(tipo_elemento)
        if tamano_arreglo > MAX_DIRECCION_I32 // bytes_elemento:
            _error("El arreglo excede el límite de memoria WebAssembly.", declaracion)
        instrucciones = [
            f"i32.const {tamano_arreglo * bytes_elemento}",
            f"i32.const {bytes_elemento}",
            "call $array_alloc",
            f"local.set $local_{identificador}",
        ]
        for indice, elemento in enumerate(elementos):
            instrucciones.extend([f"local.get $local_{identificador}"])
            instrucciones.extend(
                _compilar_expresion(
                    elemento, referencias, locales, funciones, nombres_funcion, tipos
                )
            )
            instrucciones.append(
                _instruccion_almacenamiento_arreglo(tipo_elemento, indice * bytes_elemento)
            )
        return instrucciones
    if expresion is None:
        return []
    return [
        *_compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        ),
        f"local.set $local_{identificador}",
    ]


def _compilar_asignacion(
    asignacion, referencias, simbolos, locales, funciones, nombres_funcion, tipos
):
    identificador = referencias[asignacion]
    if identificador not in locales:
        _error("La asignación no corresponde a una variable local i32.", asignacion)
    if _info_arreglo(simbolos[identificador]["tipo"]) is not None:
        _error("La asignación de arreglos todavía no está implementada.", asignacion)
    operador = asignacion.assignmentOp().getText()
    expresion = _compilar_expresion(
        asignacion.expression(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if operador == "=":
        return [*expresion, f"local.set $local_{identificador}"]
    instrucciones = [f"local.get $local_{identificador}", *expresion]
    tipo = simbolos[identificador]["tipo"]
    if tipo not in {"i32", "f64"}:
        _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
    instrucciones.append({
        "+=": f"{tipo}.add",
        "-=": f"{tipo}.sub",
        "*=": f"{tipo}.mul",
        "/=": "i32.div_s" if tipo == "i32" else "f64.div",
    }[operador])
    instrucciones.append(f"local.set $local_{identificador}")
    return instrucciones


def _compilar_llamada(llamada, referencias, locales, funciones, nombres_funcion, tipos):
    nombre = llamada.IDENT().getText()
    firma = funciones.get(nombre)
    if firma is None or nombre not in nombres_funcion.nombres_funcion:
        _error(f"La función '{nombre}' no está disponible para generar WASM.", llamada)
    if any(tipo not in {"i32", "bool", "f64", "char", "String"} for tipo in firma["parametros"]):
        _error(f"La función '{nombre}' usa parámetros no soportados.", llamada)
    if firma["retorno"] not in {"i32", "bool", "f64", "char", "String", "unit"}:
        _error(f"La función '{nombre}' tiene un retorno no soportado.", llamada)

    argumentos = []
    lista = llamada.argumentList()
    if lista is not None:
        argumentos = lista.expression()
    instrucciones = []
    for argumento in argumentos:
        instrucciones.extend(
            _compilar_expresion(
                argumento, referencias, locales, funciones, nombres_funcion, tipos
            )
        )
    instrucciones.append(f"call $funcion_{nombres_funcion.nombres_funcion[nombre]}")
    return instrucciones, firma["retorno"]


def _compilar_bloque(
    bloque, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
):
    instrucciones = []
    for sentencia in bloque.statement():
        instrucciones.extend(
            _compilar_sentencia(
                sentencia, declaraciones, referencias, simbolos, locales,
                tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
            )
        )
    return instrucciones


def _compilar_if(
    condicional, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
):
    condicion = _compilar_expresion(
        condicional.expression(), referencias, locales, funciones, nombres_funcion,
        tipos_expresiones,
    )
    rama_cierta = _compilar_bloque(
        condicional.block(0), declaraciones, referencias, simbolos, locales,
        tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
    )
    rama_falsa = None
    if condicional.ifStmt() is not None:
        rama_falsa = _compilar_if(
            condicional.ifStmt(), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    elif len(condicional.block()) == 2:
        rama_falsa = _compilar_bloque(
            condicional.block(1), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    return [*condicion, _wat_if(rama_cierta, rama_falsa)]


def _compilar_ciclo(
    ciclo, es_while, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
):
    indice = ciclos["siguiente"]
    ciclos["siguiente"] += 1
    salida = f"salida_{indice}"
    siguiente = f"siguiente_{indice}"
    ciclos["activos"].append((salida, siguiente))
    try:
        cuerpo = _compilar_bloque(
            ciclo.block(), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    finally:
        ciclos["activos"].pop()

    contenido = []
    if es_while:
        contenido.extend(
            _compilar_expresion(
                ciclo.expression(), referencias, locales, funciones, nombres_funcion,
                tipos_expresiones,
            )
        )
        contenido.extend(["i32.eqz", f"br_if ${salida}"])
    contenido.extend(cuerpo)
    contenido.append(f"br ${siguiente}")
    instrucciones = "\n        ".join(contenido)
    return [
        f"(block ${salida}\n"
        f"      (loop ${siguiente}\n"
        f"        {instrucciones}\n"
        f"      )\n"
        f"    )"
    ]


def _compilar_sentencia(
    sentencia, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
):
    if sentencia.letDecl() is not None:
        return _compilar_declaracion(
            sentencia.letDecl(), declaraciones, simbolos, referencias, locales,
            funciones, nombres_funcion, tipos_expresiones,
        )
    if sentencia.assignment() is not None:
        return _compilar_asignacion(
            sentencia.assignment(), referencias, simbolos, locales, funciones, nombres_funcion,
            tipos_expresiones,
        )
    if sentencia.functionCall() is not None:
        instrucciones, retorno = _compilar_llamada(
            sentencia.functionCall(), referencias, locales, funciones, nombres_funcion,
            tipos_expresiones,
        )
        return [*instrucciones, *( ["drop"] if retorno != "unit" else [] )]
    if sentencia.ifStmt() is not None:
        return _compilar_if(
            sentencia.ifStmt(), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    if sentencia.whileStmt() is not None:
        return _compilar_ciclo(
            sentencia.whileStmt(), True, declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    if sentencia.loopStmt() is not None:
        return _compilar_ciclo(
            sentencia.loopStmt(), False, declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    if sentencia.breakStmt() is not None:
        return [f"br ${ciclos['activos'][-1][0]}"]
    if sentencia.continueStmt() is not None:
        return [f"br ${ciclos['activos'][-1][1]}"]
    if sentencia.returnStmt() is not None:
        expresion = sentencia.returnStmt().expression()
        if tipo_retorno == "unit":
            if expresion is not None:
                _error("Una función unit no puede retornar una expresión.", sentencia)
            return ["return"]
        if expresion is None:
            _error("La función debe retornar una expresión.", sentencia)
        if tipos_expresiones.get(expresion) != tipo_retorno:
            _error("El tipo de retorno no coincide con la función.", expresion)
        return [
            *_compilar_expresion(
                expresion, referencias, locales, funciones, nombres_funcion, tipos_expresiones
            ),
            "return",
        ]
    if sentencia.block() is not None:
        return _compilar_bloque(
            sentencia.block(), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    _error("Esta sentencia todavía no está implementada.", sentencia)


def _compilar_funcion(funcion, analisis, indice, nombres_funcion):
    nombre = funcion.IDENT().getText()
    tipo_retorno = funcion.type_().getText() if funcion.type_() is not None else "unit"
    if tipo_retorno not in {"i32", "bool", "f64", "char", "String", "unit"}:
        _error(f"La función '{nombre}' tiene un retorno no soportado.", funcion)
    variables = {
        identificador
        for identificador, simbolo in analisis["simbolos"].items()
        if simbolo["funcion"] == nombre and not simbolo["es_parametro"]
        and not simbolo["es_constante"]
    }
    parametros = {
        identificador
        for identificador, simbolo in analisis["simbolos"].items()
        if simbolo["funcion"] == nombre and simbolo["es_parametro"]
    }
    variables.update(parametros)
    for identificador in parametros:
        if _info_arreglo(analisis["simbolos"][identificador]["tipo"]) is not None:
            _error("Los parámetros de arreglos todavía no están implementados.", funcion)
    for identificador in variables:
        tipo = analisis["simbolos"][identificador]["tipo"]
        if tipo not in {"i32", "bool", "f64", "char", "String"} and _info_arreglo(tipo) is None:
            _error("El tipo de parámetro o variable no está implementado.", funcion)
    parametros_wat = " ".join(
        f"(param $local_{identificador} "
        f"{_tipo_wasm(analisis['simbolos'][identificador]['tipo'])})"
        for identificador in sorted(parametros)
    )
    resultado_wat = "" if tipo_retorno == "unit" else f" (result {_tipo_wasm(tipo_retorno)})"
    declaraciones_locales = "\n".join(
        f"    (local $local_{identificador} "
        f"{_tipo_wasm(analisis['simbolos'][identificador]['tipo'])})"
        for identificador in sorted(variables - parametros)
    )
    instrucciones = []
    ciclos = {"siguiente": 0, "activos": []}
    for sentencia in funcion.block().statement():
        instrucciones.extend(
            _compilar_sentencia(
                sentencia,
                analisis["declaraciones"],
                analisis["referencias"],
                analisis["simbolos"],
                variables,
                analisis["tipos_expresiones"],
                tipo_retorno,
                analisis["funciones"],
                nombres_funcion,
                ciclos,
            )
        )
    if tipo_retorno != "unit":
        instrucciones.append("unreachable")
    cuerpo = "\n    ".join(instrucciones)
    locales_wat = f"\n{declaraciones_locales}" if declaraciones_locales else ""
    return (
        f"  (func $funcion_{indice} {parametros_wat}{resultado_wat}{locales_wat}\n"
        f"    {cuerpo}\n"
        f"  )\n"
        f"  (export \"{nombre}\" (func $funcion_{indice}))"
    )


def compilar_programa(codigo):
    """Compila RustiQ a WebAssembly y devuelve ``valido`, `errores`, `wat`, `wasm`."""
    analisis = analizar_programa(codigo)
    if not analisis["valido"]:
        return {"valido": False, "errores": analisis["errores"], "wat": None, "wasm": None}
    try:
        arbol = analisis["arbol"]
        if arbol.constDecl():
            _error("Las constantes globales todavía no están implementadas.", arbol.constDecl(0))
        funciones = arbol.functionDecl()
        if not funciones:
            _error("El programa debe declarar al menos una función.", arbol)
        estado = EstadoModulo(
            {
                funcion.IDENT().getText(): indice
                for indice, funcion in enumerate(funciones)
            },
            MemoriaStrings(),
        )
        wat_funciones = [
            _compilar_funcion(funcion, analisis, indice, estado)
            for indice, funcion in enumerate(funciones)
        ]
        datos = estado.memoria.wat()
        wat = (
            f"(module\n  (memory (export \"memory\") {estado.memoria.paginas_necesarias()})\n"
            + _wat_string_eq() + "\n"
            + _wat_arreglos((estado.memoria.cursor + 3) & ~3) + "\n"
            + "\n".join(wat_funciones)
            + ("\n" + datos if datos else "")
            + "\n)"
        )
        wasm = wasmtime.wat2wasm(wat)
        wasmtime.Module(wasmtime.Engine(), wasm)
    except ErrorGeneracion as error:
        return {"valido": False, "errores": [error.como_error()], "wat": None, "wasm": None}
    except wasmtime.WasmtimeError as error:
        return {
            "valido": False,
            "errores": [{"fase": "generacion", "mensaje": str(error), "linea": 1, "columna": 1}],
            "wat": None,
            "wasm": None,
        }
    return {"valido": True, "errores": [], "wat": wat, "wasm": wasm}


def ejecutar_modulo_wasm(wasm, funcion="main", *argumentos):
    """Instancia un binario generado y ejecuta una exportación sin parámetros."""
    motor = wasmtime.Engine()
    modulo = wasmtime.Module(motor, wasm)
    almacen = wasmtime.Store(motor)
    instancia = wasmtime.Instance(almacen, modulo, [])
    return instancia.exports(almacen)[funcion](almacen, *argumentos)


def ejecutar_string_wasm(wasm, funcion="main", *argumentos):
    motor = wasmtime.Engine()
    modulo = wasmtime.Module(motor, wasm)
    almacen = wasmtime.Store(motor)
    instancia = wasmtime.Instance(almacen, modulo, [])
    descriptor = instancia.exports(almacen)[funcion](almacen, *argumentos)
    memoria = instancia.exports(almacen)["memory"]
    cabecera = bytes(memoria.read(almacen, descriptor, descriptor + 8))
    puntero = int.from_bytes(cabecera[:4], "little")
    longitud = int.from_bytes(cabecera[4:], "little")
    return bytes(memoria.read(almacen, puntero, puntero + longitud)).decode("utf-8")
