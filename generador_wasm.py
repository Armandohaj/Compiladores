"""Backend WebAssembly mínimo para el subconjunto aritmético de RustiQ."""

from __future__ import annotations

from dataclasses import dataclass

import wasmtime

from main import analizar_programa
from flujo_control import salidas_control
from tipos_compuestos import accesos_escritura, accesos_lectura, separar_tipo_tupla
from tipos_referencias import separar_referencia


TAMANO_PAGINA_WASM = 65536
MAX_PAGINAS_MEMORIA = 65536
MAX_DIRECCION_I32 = 2**32 - 1


class MemoriaStrings:
    """Guarda los textos estáticos que se copiarán al módulo como segmentos data."""
    def __init__(self):
        self.cursor = 0
        self.segmentos = []

    def agregar(self, texto, contexto):
        # Cada String ocupa un descriptor de 8 bytes: dirección de UTF-8 y longitud.
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
        """WebAssembly reserva memoria por páginas de 64 KiB, no byte a byte."""
        return max(1, (self.cursor + TAMANO_PAGINA_WASM - 1) // TAMANO_PAGINA_WASM)

    def wat(self):
        """Convierte los bytes guardados al escape hexadecimal que entiende WAT."""
        return "\n".join(
            f"  (data (i32.const {direccion}) \""
            f"{''.join(f'\\{byte:02x}' for byte in datos)}\")"
            for direccion, datos in self.segmentos
        )

@dataclass
class EstadoModulo:
    """Información compartida mientras se traduce un programa completo a WAT."""
    nombres_funcion: dict
    memoria: MemoriaStrings
    constantes: dict
    estructuras: dict
    enumeraciones: dict
    declaraciones: dict
    simbolos: dict
    llamadas_incorporadas: dict
    incorporadas_usadas: set
    ciclos: dict | None = None
    tipo_retorno_actual: str | None = None
    temporales_match: list | None = None
    siguiente_match: int = 0
    temporales_enum: list | None = None
    siguiente_enum: int = 0
    prestamos: dict | None = None
    escalares_en_memoria: set | None = None
    origenes_prestados: set | None = None


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


def _tipo_wasm(tipo, estructuras=None, enumeraciones=None):
    """Relaciona los tipos RustiQ con los pocos tipos que maneja WebAssembly."""
    referencia = separar_referencia(tipo)
    if referencia is not None:
        return "i32"
    return "i32" if tipo in {"bool", "char", "String"} or _info_arreglo(tipo) is not None or _info_matriz(tipo) is not None or _info_tupla(tipo) is not None or _info_estructura(tipo, estructuras) is not None or _info_enum(tipo, enumeraciones) is not None else tipo


def _escalar_prestable(tipo):
    return tipo in {"i32", "f64", "bool", "char"}


def _tamano_y_alineacion_escalar(tipo):
    """Devuelve el espacio de un escalar cuando debe vivir en memoria por un préstamo."""
    if not _escalar_prestable(tipo):
        return None
    tamano = _tamano_elemento_arreglo(tipo)
    return tamano, tamano


def _referencia_admitida(tipo, estructuras):
    """Comprueba si una referencia usa un layout que el generador ya conoce."""
    referencia = separar_referencia(tipo)
    if referencia is None:
        return False
    return _escalar_prestable(referencia[1]) or _compuesto_prestable(
        referencia[1], estructuras
    )


def _compuesto_prestable(tipo, estructuras):
    """Limita préstamos compuestos a layouts locales con elementos Copy básicos."""
    if _distribucion_estructura(tipo, estructuras) is not None:
        return True
    if _distribucion_tupla(tipo) is not None:
        return True
    arreglo = _info_arreglo(tipo)
    if arreglo is not None:
        return _escalar_prestable(arreglo[0])
    matriz = _info_matriz(tipo)
    return matriz is not None and _escalar_prestable(matriz[0])


def _carga_escalar_memoria(tipo):
    return _instruccion_carga_arreglo(tipo)


def _almacenamiento_escalar_memoria(tipo):
    return _instruccion_almacenamiento_arreglo(tipo, 0)


def _info_arreglo(tipo):
    """Reconoce la forma canónica [T; N] que entrega el frontend."""
    if not tipo.startswith("[") or not tipo.endswith("]"):
        return None
    contenido = tipo[1:-1]
    if ";" not in contenido:
        return None
    elemento, tamano = contenido.rsplit(";", 1)
    if elemento not in {"i32", "bool", "char", "f64", "String"} or not tamano.isdigit():
        return None
    return elemento, int(tamano)


def _info_matriz(tipo):
    """Reconoce una matriz como un arreglo cuyo elemento también es un arreglo."""
    if not tipo.startswith("[") or not tipo.endswith("]"):
        return None
    contenido = tipo[1:-1]
    if ";" not in contenido:
        return None
    fila, filas = contenido.rsplit(";", 1)
    if not filas.isdigit():
        return None
    arreglo_fila = _info_arreglo(fila)
    if arreglo_fila is None:
        return None
    tipo_elemento, columnas = arreglo_fila
    return tipo_elemento, int(filas), columnas


def _info_tupla(tipo):
    campos = separar_tipo_tupla(tipo)
    if campos is None or len(campos) < 2 or any(campo not in {"i32", "f64", "bool", "char"} for campo in campos):
        return None
    return campos


def _distribucion_tupla(tipo):
    """Calcula dónde empieza cada campo de una tupla dentro de memoria lineal."""
    campos = _info_tupla(tipo)
    if campos is None:
        return None
    desplazamiento = 0
    distribucion = []
    for campo in campos:
        alineacion = 8 if campo == "f64" else 4
        desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
        distribucion.append((campo, desplazamiento))
        desplazamiento += _tamano_elemento_arreglo(campo)
    return distribucion, desplazamiento, max(8 if campo == "f64" else 4 for campo in campos)


def _info_estructura(tipo, estructuras):
    campos = (estructuras or {}).get(tipo)
    if campos is None or any(campo not in {"i32", "f64", "bool", "char"} for campo in campos.values()):
        return None
    return campos


def _info_enum(tipo, enumeraciones):
    return (enumeraciones or {}).get(tipo)


def _enum_tiene_datos(tipo, enumeraciones):
    enumeracion = _info_enum(tipo, enumeraciones)
    return enumeracion is not None and bool(enumeracion.get("datos_variantes"))


def _distribucion_enum(tipo, enumeraciones):
    """Construye el layout común de las variantes con datos de una enumeración."""
    enumeracion = _info_enum(tipo, enumeraciones)
    if enumeracion is None:
        return None
    datos = enumeracion.get("datos_variantes")
    if not datos:
        return None
    distribucion = {}
    tamano_maximo = 4
    alineacion_maxima = 4
    for variante, etiqueta in enumeracion["variantes"].items():
        desplazamiento = 4
        campos = []
        for campo in datos.get(variante, []):
            if campo not in {"i32", "bool", "char", "f64"}:
                return None
            alineacion = 8 if campo == "f64" else 4
            desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
            campos.append((campo, desplazamiento))
            desplazamiento += _tamano_elemento_arreglo(campo)
            alineacion_maxima = max(alineacion_maxima, alineacion)
        distribucion[variante] = (etiqueta, campos)
        tamano_maximo = max(tamano_maximo, desplazamiento)
    return distribucion, tamano_maximo, alineacion_maxima


def _distribucion_estructura(tipo, estructuras):
    """Respeta el orden de campos declarado por Kevin y alinea f64 a ocho bytes."""
    campos = _info_estructura(tipo, estructuras)
    if campos is None:
        return None
    desplazamiento = 0
    distribucion = {}
    alineacion_maxima = 4
    for nombre, campo in campos.items():
        alineacion = 8 if campo == "f64" else 4
        desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
        distribucion[nombre] = (campo, desplazamiento)
        desplazamiento += _tamano_elemento_arreglo(campo)
        alineacion_maxima = max(alineacion_maxima, alineacion)
    return distribucion, desplazamiento, alineacion_maxima


def _layout_copia_compuesta(tipo, estructuras, enumeraciones):
    """Indica cuánto se debe copiar para que un valor Copy no comparta su bloque."""
    arreglo = _info_arreglo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        if elemento in {"i32", "f64", "bool", "char"}:
            paso = _tamano_elemento_arreglo(elemento)
            if cantidad <= MAX_DIRECCION_I32 // paso:
                return cantidad * paso, paso
        return None
    matriz = _info_matriz(tipo)
    if matriz is not None:
        elemento, filas, columnas = matriz
        if elemento in {"i32", "f64", "bool", "char"}:
            paso = _tamano_elemento_arreglo(elemento)
            if columnas and filas <= MAX_DIRECCION_I32 // columnas and filas * columnas <= MAX_DIRECCION_I32 // paso:
                return filas * columnas * paso, paso
        return None
    tupla = _distribucion_tupla(tipo)
    if tupla is not None:
        _, tamano, alineacion = tupla
        return tamano, alineacion
    estructura = _distribucion_estructura(tipo, estructuras)
    if estructura is not None:
        _, tamano, alineacion = estructura
        return tamano, alineacion
    enumeracion = _distribucion_enum(tipo, enumeraciones)
    if enumeracion is not None:
        _, tamano, alineacion = enumeracion
        return tamano, alineacion
    return None


def _tamano_elemento_arreglo(tipo):
    return 8 if tipo == "f64" else 4


def _instruccion_carga_arreglo(tipo, desplazamiento=0):
    """Elige i32.load o f64.load según el elemento que se lee de memoria."""
    if desplazamiento == 0:
        return "f64.load align=8" if tipo == "f64" else "i32.load"
    alineacion = " align=8" if tipo == "f64" else ""
    return f"{tipo if tipo == 'f64' else 'i32'}.load offset={desplazamiento}{alineacion}"


def _instruccion_almacenamiento_arreglo(tipo, desplazamiento):
    """Elige el store correcto y conserva la alineación de los decimales."""
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


def _compilar_constante(simbolo, estado, contexto):
    """Convierte el valor ya calculado por Kevin en su literal WebAssembly.

    Así las constantes globales y locales nunca vuelven a evaluar su inicializador
    durante la ejecución del WASM.
    """
    tipo = simbolo["tipo"]
    valor = simbolo["valor"]
    if tipo == "i32":
        return [f"i32.const {valor}"]
    if tipo == "f64":
        return [f"f64.const {valor}"]
    if tipo == "bool":
        return [f"i32.const {int(valor)}"]
    if tipo == "char":
        return [f"i32.const {ord(valor)}"]
    if tipo == "String":
        return [f"i32.const {estado.memoria.agregar(valor, contexto)}"]
    _error(f"Las constantes globales de tipo {tipo} todavía no están implementadas.", contexto)


def _compilar_expresion(expresion, referencias, locales, funciones, nombres_funcion, tipos):
    """Entrada común de expresiones: conserva la precedencia definida por ANTLR."""
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
    """Emite comparaciones y deja un i32 0/1, que es el bool de WebAssembly."""
    operandos = contexto.additive()
    instrucciones = _compilar_aditiva(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    if len(operandos) == 1:
        return instrucciones
    if "normal" not in salidas_control(operandos[0]):
        return instrucciones
    operador = contexto.relOp().getText()
    instrucciones.extend(
        _compilar_aditiva(operandos[1], referencias, locales, funciones, nombres_funcion, tipos)
    )
    if "normal" not in salidas_control(operandos[1]):
        return instrucciones
    tipo = tipos[operandos[0]]
    if _enum_tiene_datos(tipo, nombres_funcion.enumeraciones):
        _error("La comparación de enumeraciones con datos todavía no está implementada.", contexto)
    if _info_arreglo(tipo) is not None or _info_matriz(tipo) is not None:
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


def _wat_condicional_resultado(rama_cierta, rama_falsa, tipo):
    """Variante del if anterior para resultados i32 o f64."""
    cierta = "\n        ".join(rama_cierta)
    falsa = "\n        ".join(rama_falsa)
    return (
        f"(if (result {tipo})\n"
        f"      (then\n        {cierta}\n      )\n"
        f"      (else\n        {falsa}\n      )\n"
        "    )"
    )


def _wat_if(rama_cierta, rama_falsa=None):
    """Crea un if de control: sus ramas no dejan un valor en la pila."""
    cierta = "\n        ".join(rama_cierta) if rama_cierta else "nop"
    wat = "(if\n" f"      (then\n        {cierta}\n      )"
    if rama_falsa is not None:
        falsa = "\n        ".join(rama_falsa) if rama_falsa else "nop"
        wat += f"\n      (else\n        {falsa}\n      )"
    return wat + "\n    )"


def _wat_string_eq():
    """Genera una función interna que compara bytes UTF-8 y no sólo punteros."""
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
    """Genera el pequeño asignador monotónico y la guarda de índices.

    $array_alloc devuelve una dirección alineada y aumenta memoria cuando hace
    falta. $array_addr revisa los límites antes de calcular una posición, por
    eso arreglos, matrices, tuplas y estructuras comparten estas protecciones.
    """
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
    """Traduce + y - después de compilar los operandos en el orden escrito."""
    operandos = contexto.multiplicative()
    instrucciones = _compilar_multiplicativa(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    if "normal" not in salidas_control(operandos[0]):
        return instrucciones
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(
            _compilar_multiplicativa(
                operando, referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        if "normal" not in salidas_control(operando):
            return instrucciones
        tipo = tipos[contexto]
        if tipo not in {"i32", "f64"}:
            _error("Esta operación aritmética no está disponible para el tipo.", contexto)
        instrucciones.append(f"{tipo}.{'add' if operador == '+' else 'sub'}")
    return instrucciones


def _compilar_multiplicativa(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Traduce *, / y %, usando las instrucciones con signo para i32."""
    operandos = contexto.unary()
    instrucciones = _compilar_unaria(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    if "normal" not in salidas_control(operandos[0]):
        return instrucciones
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(
            _compilar_unaria(operando, referencias, locales, funciones, nombres_funcion, tipos)
        )
        if "normal" not in salidas_control(operando):
            return instrucciones
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
    """Maneja negaciones, préstamos y desreferenciaciones antes de los accesos."""
    if contexto.borrowExpr() is not None:
        # El frontend ya comprobó las vidas; aquí sólo convertimos el origen en dirección.
        prestamo = nombres_funcion.prestamos.get(contexto.borrowExpr())
        if prestamo is None:
            _error("El préstamo no está disponible para generar WASM.", contexto.borrowExpr())
        identificador = prestamo["simbolo_id"]
        if identificador not in nombres_funcion.origenes_prestados:
            _error("El origen del préstamo no está disponible para generar WASM.", contexto.borrowExpr())
        instrucciones = [f"local.get $local_{identificador}"]
        tipo_operando = tipos.get(contexto.borrowExpr())
    elif contexto.dereferenceExpr() is not None:
        # Una referencia se guarda como i32, pero el load recupera su tipo RustiQ real.
        referencia = contexto.dereferenceExpr()
        tipo = tipos.get(referencia)
        if not _escalar_prestable(tipo):
            _error("Solo se admite desreferenciar tipos escalares.", referencia)
        instrucciones = [
            *_compilar_unaria(
                referencia.unary(), referencias, locales, funciones, nombres_funcion, tipos
            ),
            _carga_escalar_memoria(tipo),
        ]
        tipo_operando = tipo
    else:
        instrucciones = None
        tipo_operando = None
    if instrucciones is not None:
        if contexto.NOT() is not None:
            return [*instrucciones, "i32.eqz"]
        if contexto.MINUS() is not None:
            if tipo_operando == "f64":
                return [*instrucciones, "f64.neg"]
            if tipo_operando == "i32":
                return ["i32.const 0", *instrucciones, "i32.sub"]
            _error("La negación aritmética solo está disponible para i32 y f64.", contexto)
        return instrucciones
    if contexto.getChildCount() == 1:
        return _compilar_postfija(
            contexto.postfix(), referencias, locales, funciones, nombres_funcion, tipos
        )
    operador = contexto.getChild(0).getText()
    if operador == "!":
        instrucciones = _compilar_postfija(
            contexto.postfix(), referencias, locales, funciones, nombres_funcion, tipos
        )
        return instrucciones if "normal" not in salidas_control(contexto.postfix()) else [*instrucciones, "i32.eqz"]

    postfija = contexto.postfix()
    if tipos[contexto] == "f64":
        instrucciones = _compilar_postfija(
            postfija, referencias, locales, funciones, nombres_funcion, tipos
        )
        return instrucciones if "normal" not in salidas_control(postfija) else [*instrucciones, "f64.neg"]
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

    instrucciones = _compilar_postfija(
        postfija, referencias, locales, funciones, nombres_funcion, tipos
    )
    return instrucciones if "normal" not in salidas_control(postfija) else ["i32.const 0", *instrucciones, "i32.sub"]


def _compilar_postfija(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Aplica accesos de campos e índices sobre el puntero o valor base."""
    instrucciones = _compilar_primaria(
        contexto.primary(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if contexto.getChildCount() == 1:
        return instrucciones
    if "normal" not in salidas_control(contexto.primary()):
        return instrucciones
    tipo_base = tipos[contexto.primary()]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        # La referencia ya es el puntero del bloque original; los layouts calculan el offset.
        if not _compuesto_prestable(referencia[1], nombres_funcion.estructuras):
            _error("Solo se admiten accesos mediante referencias a compuestos locales compatibles.", contexto)
        tipo_base = referencia[1]
    estructura = _distribucion_estructura(tipo_base, nombres_funcion.estructuras)
    if estructura is not None:
        accesos = list(accesos_lectura(contexto))
        if len(accesos) != 1 or accesos[0][0] != "nombre":
            _error("Solo se admite el acceso directo a campos de estructuras locales.", contexto)
        nombre = accesos[0][1].IDENT().getText()
        campos, _, _ = estructura
        if nombre not in campos:
            _error("El campo de la estructura no está disponible para generar WASM.", contexto)
        tipo, desplazamiento = campos[nombre]
        return [*instrucciones, _instruccion_carga_arreglo(tipo, desplazamiento)]
    tupla = _distribucion_tupla(tipo_base)
    if tupla is not None:
        accesos = list(accesos_lectura(contexto))
        if len(accesos) != 1 or accesos[0][0] != "campo":
            _error("Solo se admite el acceso directo a campos de tuplas locales.", contexto)
        indice = int(accesos[0][1].getText()[1:])
        campos, _, _ = tupla
        if indice >= len(campos):
            _error("El campo de la tupla no está disponible para generar WASM.", contexto)
        tipo, desplazamiento = tupla[0][indice]
        return [*instrucciones, _instruccion_carga_arreglo(tipo, desplazamiento)]
    matriz = _info_matriz(tipo_base)
    if matriz is not None:
        tipo_elemento, filas, columnas = matriz
        if len(contexto.expression()) != 2:
            _error("Las matrices locales requieren exactamente dos índices.", contexto)
        bytes_elemento = _tamano_elemento_arreglo(tipo_elemento)
        instrucciones.extend(
            _compilar_expresion(
                contexto.expression(0), referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        instrucciones.extend(
            [
                f"i32.const {filas}",
                f"i32.const {columnas * bytes_elemento}",
                "call $array_addr",
            ]
        )
        instrucciones.extend(
            _compilar_expresion(
                contexto.expression(1), referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        instrucciones.extend(
            [
                f"i32.const {columnas}",
                f"i32.const {bytes_elemento}",
                "call $array_addr",
                _instruccion_carga_arreglo(tipo_elemento),
            ]
        )
        return instrucciones
    arreglo = _info_arreglo(tipo_base)
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


def _literal_patron(contexto, tipo, enumeraciones):
    if contexto.DOUBLE_COLON() is not None:
        enumeracion = _info_enum(tipo, enumeraciones)
        nombres = contexto.IDENT()
        if enumeracion is None or len(nombres) != 2 or contexto.LPAREN() is not None:
            _error("El patrón de enumeración todavía no está implementado.", contexto)
        variante = nombres[1].getText()
        if variante not in enumeracion["variantes"]:
            _error("La variante no está disponible para generar WASM.", contexto)
        return f"i32.const {enumeracion['variantes'][variante]}"
    literal = contexto.patternLiteral()
    if literal is None:
        return None
    if tipo == "i32" and literal.INT() is not None:
        return f"i32.const {int(literal.getText())}"
    if tipo == "bool":
        if literal.TRUE() is not None:
            return "i32.const 1"
        if literal.FALSE() is not None:
            return "i32.const 0"
    if tipo == "char" and literal.CHAR_LITERAL() is not None:
        return f"i32.const {_valor_char(literal.CHAR_LITERAL().getText(), literal)}"
    _error("El patrón de match todavía no está implementado.", contexto)


def _condicion_patron_enum(patron, temporal, tipo, desplazamiento, referencias, locales,
                            nombres_funcion):
    if patron.UNDERSCORE() is not None:
        return [], []
    literal = patron.patternLiteral()
    if literal is not None:
        if tipo == "i32" and literal.INT() is not None:
            valor = f"i32.const {int(literal.getText())}"
        elif tipo == "bool" and literal.TRUE() is not None:
            valor = "i32.const 1"
        elif tipo == "bool" and literal.FALSE() is not None:
            valor = "i32.const 0"
        elif tipo == "char" and literal.CHAR_LITERAL() is not None:
            valor = f"i32.const {_valor_char(literal.CHAR_LITERAL().getText(), literal)}"
        elif tipo == "f64" and literal.FLOAT() is not None:
            valor = f"f64.const {literal.FLOAT().getText()}"
        else:
            _error("El patrón de dato de enumeración todavía no está implementado.", patron)
        return [
            f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
            valor, f"{tipo}.eq" if tipo == "f64" else "i32.eq",
        ], []
    if patron.IDENT():
        identificador = nombres_funcion.declaraciones.get(patron)
        if identificador is None or identificador not in locales:
            _error("El receptor del patrón no está disponible para generar WASM.", patron)
        return [], [
            f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
            f"local.set $local_{identificador}",
        ]
    _error("El patrón de dato de enumeración todavía no está implementado.", patron)


def _compilar_patron_enum(patron, temporal, tipo_valor, referencias, locales, nombres_funcion):
    """Comprueba etiqueta y datos de una variante antes de entrar a su brazo match."""
    distribucion = _distribucion_enum(tipo_valor, nombres_funcion.enumeraciones)
    if distribucion is None or patron.DOUBLE_COLON() is None:
        _error("El patrón de enumeración todavía no está implementado.", patron)
    variantes, _, _ = distribucion
    nombres = patron.IDENT()
    if len(nombres) != 2:
        _error("El patrón de enumeración no está disponible para generar WASM.", patron)
    variante = nombres[1].getText()
    if variante not in variantes:
        _error("La variante no está disponible para generar WASM.", patron)
    etiqueta, campos = variantes[variante]
    lista = patron.patternList()
    patrones = [] if lista is None else lista.pattern()
    if len(patrones) != len(campos):
        _error("El patrón no coincide con los datos de la variante.", patron)
    condiciones = [
        f"local.get ${temporal}", "i32.load", f"i32.const {etiqueta}", "i32.eq"
    ]
    enlaces = []
    for hijo, (tipo, desplazamiento) in zip(patrones, campos):
        condicion, enlace = _condicion_patron_enum(
            hijo, temporal, tipo, desplazamiento, referencias, locales, nombres_funcion
        )
        if condicion:
            condiciones.extend(condicion)
            condiciones.append("i32.and")
        enlaces.extend(enlace)
    return condiciones, enlaces


def _compilar_brazos_match(brazos, indice, temporal, tipo_valor, tipo_resultado,
                           referencias, locales, funciones, nombres_funcion, tipos):
    """Genera brazos anidados para conservar la regla del primer patrón compatible."""
    if indice >= len(brazos):
        return ["unreachable"]
    brazo = brazos[indice]
    patron = brazo.pattern()
    expresion = _compilar_expresion(
        brazo.expression(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if patron.UNDERSCORE() is not None:
        return expresion
    if patron.DOUBLE_COLON() is not None and _enum_tiene_datos(tipo_valor, nombres_funcion.enumeraciones):
        condicion, enlaces = _compilar_patron_enum(
            patron, temporal, tipo_valor, referencias, locales, nombres_funcion
        )
        siguiente = _compilar_brazos_match(
            brazos, indice + 1, temporal, tipo_valor, tipo_resultado,
            referencias, locales, funciones, nombres_funcion, tipos,
        )
        return [
            *condicion,
            _wat_condicional_resultado(
                [*enlaces, *expresion], siguiente,
                _tipo_wasm(tipo_resultado, enumeraciones=nombres_funcion.enumeraciones),
            ),
        ]
    if patron.LPAREN() is not None:
        _error("Este patrón de match todavía no está implementado.", patron)
    if patron.DOUBLE_COLON() is not None:
        literal = _literal_patron(patron, tipo_valor, nombres_funcion.enumeraciones)
    elif patron.IDENT():
        identificador = nombres_funcion.declaraciones.get(patron)
        if identificador is None or identificador not in locales:
            _error("El receptor del patrón no está disponible para generar WASM.", patron)
        return [f"local.get ${temporal}", f"local.set $local_{identificador}", *expresion]
    else:
        literal = _literal_patron(patron, tipo_valor, nombres_funcion.enumeraciones)
    siguiente = _compilar_brazos_match(
        brazos, indice + 1, temporal, tipo_valor, tipo_resultado,
        referencias, locales, funciones, nombres_funcion, tipos,
    )
    return [
        f"local.get ${temporal}",
        literal,
        "i32.eq",
        _wat_condicional_resultado(expresion, siguiente, _tipo_wasm(tipo_resultado, enumeraciones=nombres_funcion.enumeraciones)),
    ]


def _compilar_match(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Evalúa el valor una sola vez y lo conserva en un local temporal del match."""
    tipo_valor = tipos.get(contexto.expression())
    tipo_resultado = tipos.get(contexto)
    if tipo_valor not in {"i32", "bool", "char"} and _info_enum(tipo_valor, nombres_funcion.enumeraciones) is None:
        _error("Solo se admiten match de i32, bool, char y enumeraciones.", contexto)
    if tipo_resultado not in {"i32", "f64", "bool", "char", "String"}:
        _error("El resultado de match todavía no está implementado.", contexto)
    valor = _compilar_expresion(
        contexto.expression(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if "normal" not in salidas_control(contexto.expression()):
        return valor
    temporal = f"valor_match_{nombres_funcion.siguiente_match}"
    nombres_funcion.siguiente_match += 1
    nombres_funcion.temporales_match.append(temporal)
    brazos = contexto.matchArm()
    return [
        *valor,
        f"local.set ${temporal}",
        *_compilar_brazos_match(
            brazos, 0, temporal, tipo_valor, tipo_resultado,
            referencias, locales, funciones, nombres_funcion, tipos,
        ),
    ]


def _compilar_enum_valor(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Construye una variante: etiquetas simples son i32 y las demás usan memoria."""
    nombres = contexto.IDENT()
    tipo = tipos.get(contexto)
    enumeracion = _info_enum(tipo, nombres_funcion.enumeraciones)
    if len(nombres) != 2 or enumeracion is None:
        _error("Esta variante de enumeración todavía no está implementada.", contexto)
    variante = nombres[1].getText()
    if variante not in enumeracion["variantes"]:
        _error("La variante de enumeración no está disponible para generar WASM.", contexto)
    distribucion = _distribucion_enum(tipo, nombres_funcion.enumeraciones)
    if distribucion is None:
        if contexto.argumentList() is not None:
            _error("Esta variante de enumeración todavía no está implementada.", contexto)
        return [f"i32.const {enumeracion['variantes'][variante]}"]
    variantes, tamano, alineacion = distribucion
    etiqueta, campos = variantes[variante]
    argumentos = [] if contexto.argumentList() is None else contexto.argumentList().expression()
    if len(argumentos) != len(campos):
        _error("La variante no coincide con los datos esperados.", contexto)
    temporal = f"enum_{nombres_funcion.siguiente_enum}"
    nombres_funcion.siguiente_enum += 1
    nombres_funcion.temporales_enum.append(temporal)
    instrucciones = [
        f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
        f"local.set ${temporal}", f"local.get ${temporal}", f"i32.const {etiqueta}",
        "i32.store",
    ]
    # Guardamos cada argumento tras reservar el bloque para mantener su orden de evaluación.
    for argumento, (tipo_campo, desplazamiento) in zip(argumentos, campos):
        instrucciones.append(f"local.get ${temporal}")
        instrucciones.extend(_compilar_expresion(
            argumento, referencias, locales, funciones, nombres_funcion, tipos
        ))
        instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_campo, desplazamiento))
    instrucciones.append(f"local.get ${temporal}")
    return instrucciones


def _compilar_primaria(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Traduce literales, variables, llamadas y construcciones que dejan un valor."""
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
    if contexto.block() is not None:
        return _compilar_bloque(
            contexto.block(),
            nombres_funcion.declaraciones,
            referencias,
            nombres_funcion.simbolos,
            locales,
            tipos,
            nombres_funcion.tipo_retorno_actual,
            funciones,
            nombres_funcion,
            nombres_funcion.ciclos,
            True,
        )
    if contexto.matchExpr() is not None:
        return _compilar_match(
            contexto.matchExpr(), referencias, locales, funciones, nombres_funcion, tipos
        )
    if contexto.enumValue() is not None:
        return _compilar_enum_valor(
            contexto.enumValue(), referencias, locales, funciones, nombres_funcion, tipos
        )
    expresion = contexto.expression()
    if expresion is not None:
        return _compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        )
    if contexto.IDENT() is not None:
        identificador = referencias[contexto]
        constante = nombres_funcion.constantes.get(identificador)
        if constante is not None:
            return _compilar_constante(constante, nombres_funcion, contexto)
        if identificador not in locales:
            _error("La referencia no corresponde a una variable local i32.", contexto)
        if identificador in nombres_funcion.escalares_en_memoria:
            # local.get recupera la dirección; el load siguiente obtiene el valor actualizado.
            tipo = nombres_funcion.simbolos[identificador]["tipo"]
            return [f"local.get $local_{identificador}", _carga_escalar_memoria(tipo)]
        return [f"local.get $local_{identificador}"]
    if contexto.functionCall() is not None:
        instrucciones, retorno = _compilar_llamada(
            contexto.functionCall(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if retorno == "unit":
            _error("Una función unit no puede usarse como expresión.", contexto)
        return instrucciones
    if contexto.tupleLiteral() is not None:
        _error("Los literales de tupla solo se admiten al inicializar una variable local.", contexto)
    if contexto.structLiteral() is not None:
        _error("Los constructores de estructuras solo se admiten al inicializar una variable local.", contexto)
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
    if postfija is None or postfija.getChildCount() != 1:
        return None
    return postfija.primary().arrayLiteral()


def _obtener_literal_tupla(expresion):
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
    if postfija is None or postfija.getChildCount() != 1:
        return None
    return postfija.primary().tupleLiteral()


def _obtener_literal_estructura(expresion):
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
    if postfija is None or postfija.getChildCount() != 1:
        return None
    return postfija.primary().structLiteral()


def _obtener_primaria_directa(expresion):
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
    if postfija is None or postfija.getChildCount() != 1:
        return None
    return postfija.primary()


def _compilar_expresion_unit(expresion, referencias, locales, funciones, nombres_funcion, tipos):
    """Evita dejar valores en la pila cuando una expresión se usa sólo por su efecto."""
    primaria = _obtener_primaria_directa(expresion)
    if primaria is not None and primaria.functionCall() is not None:
        instrucciones, retorno = _compilar_llamada(
            primaria.functionCall(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if retorno == "unit":
            return instrucciones
    if primaria is not None and primaria.block() is not None:
        return _compilar_bloque(
            primaria.block(),
            nombres_funcion.declaraciones,
            referencias,
            nombres_funcion.simbolos,
            locales,
            tipos,
            nombres_funcion.tipo_retorno_actual,
            funciones,
            nombres_funcion,
            nombres_funcion.ciclos,
        )
    return _compilar_expresion(
        expresion, referencias, locales, funciones, nombres_funcion, tipos
    )


def _compilar_declaracion(
    declaracion, declaraciones, simbolos, referencias, locales, funciones, nombres_funcion, tipos
):
    """Genera let y reutiliza los layouts de todos los valores locales admitidos."""
    if declaracion not in declaraciones:
        expresion = declaracion.expression()
        return [] if expresion is None else _compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        )
    identificador = declaraciones[declaracion]
    if identificador not in locales:
        _error("La declaración no corresponde a una variable local i32.", declaracion)
    expresion = declaracion.expression()
    tipo_local = simbolos[identificador]["tipo"]
    if identificador in nombres_funcion.escalares_en_memoria:
        # Un escalar prestado deja de vivir sólo en un local para evitar copias desactualizadas.
        tamano_alineacion = _tamano_y_alineacion_escalar(tipo_local)
        if tamano_alineacion is None:
            _error("Solo se admiten préstamos de variables escalares.", declaracion)
        tamano, alineacion = tamano_alineacion
        instrucciones = [
            f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
            f"local.set $local_{identificador}",
        ]
        if expresion is not None:
            instrucciones.append(f"local.get $local_{identificador}")
            instrucciones.extend(_compilar_expresion(
                expresion, referencias, locales, funciones, nombres_funcion, tipos
            ))
            instrucciones.append(_almacenamiento_escalar_memoria(tipo_local))
        return instrucciones
    estructura = _distribucion_estructura(tipo_local, nombres_funcion.estructuras)
    if estructura is not None:
        if expresion is None:
            _error("Una estructura local requiere un constructor para inicializarse.", declaracion)
        literal = _obtener_literal_estructura(expresion)
        if literal is None:
            return [
                *_compilar_valor_para_local(
                    expresion, simbolos[identificador]["tipo"], referencias, locales, funciones,
                    nombres_funcion, tipos,
                ),
                f"local.set $local_{identificador}",
            ]
        campos, tamano, alineacion = estructura
        instrucciones = [
            f"i32.const {tamano}",
            f"i32.const {alineacion}",
            "call $array_alloc",
            f"local.set $local_{identificador}",
        ]
        for inicializador in literal.fieldInit():
            nombre = inicializador.IDENT().getText()
            if nombre not in campos:
                _error("El campo de la estructura no está disponible para generar WASM.", inicializador)
            tipo, desplazamiento = campos[nombre]
            instrucciones.append(f"local.get $local_{identificador}")
            instrucciones.extend(
                _compilar_expresion(
                    inicializador.expression(), referencias, locales, funciones, nombres_funcion, tipos
                )
            )
            instrucciones.append(_instruccion_almacenamiento_arreglo(tipo, desplazamiento))
        return instrucciones
    tupla = _distribucion_tupla(simbolos[identificador]["tipo"])
    if tupla is not None:
        if expresion is None:
            _error("Una tupla local requiere un literal para inicializarse.", declaracion)
        literal = _obtener_literal_tupla(expresion)
        if literal is None:
            return [
                *_compilar_valor_para_local(
                    expresion, simbolos[identificador]["tipo"], referencias, locales, funciones,
                    nombres_funcion, tipos,
                ),
                f"local.set $local_{identificador}",
            ]
        campos, tamano, alineacion = tupla
        expresiones = literal.expression()
        if len(expresiones) != len(campos):
            _error("El literal no coincide con los campos de la tupla.", literal)
        instrucciones = [
            f"i32.const {tamano}",
            f"i32.const {alineacion}",
            "call $array_alloc",
            f"local.set $local_{identificador}",
        ]
        for (tipo, desplazamiento), valor in zip(campos, expresiones):
            instrucciones.append(f"local.get $local_{identificador}")
            instrucciones.extend(
                _compilar_expresion(
                    valor, referencias, locales, funciones, nombres_funcion, tipos
                )
            )
            instrucciones.append(_instruccion_almacenamiento_arreglo(tipo, desplazamiento))
        return instrucciones
    matriz = _info_matriz(simbolos[identificador]["tipo"])
    if matriz is not None:
        tipo_elemento, filas, columnas = matriz
        if expresion is None:
            _error("Una matriz local requiere un literal para inicializarse.", declaracion)
        literal = _obtener_literal_arreglo(expresion)
        if literal is None:
            if _layout_copia_compuesta(
                simbolos[identificador]["tipo"], nombres_funcion.estructuras,
                nombres_funcion.enumeraciones,
            ) is None:
                _error("La copia de esta matriz todavía no está implementada.", expresion)
            return [
                *_compilar_valor_para_local(
                    expresion, simbolos[identificador]["tipo"], referencias, locales, funciones,
                    nombres_funcion, tipos,
                ),
                f"local.set $local_{identificador}",
            ]
        literales_fila = [_obtener_literal_arreglo(fila) for fila in literal.expression()]
        if len(literales_fila) != filas or any(fila is None for fila in literales_fila):
            _error("El literal no coincide con las filas de la matriz.", literal)
        if any(len(fila.expression()) != columnas for fila in literales_fila):
            _error("El literal no coincide con las columnas de la matriz.", literal)
        bytes_elemento = _tamano_elemento_arreglo(tipo_elemento)
        if filas == 0 or columnas == 0:
            _error("Las matrices vacías todavía no están implementadas.", declaracion)
        if filas > MAX_DIRECCION_I32 // columnas or filas * columnas > MAX_DIRECCION_I32 // bytes_elemento:
            _error("La matriz excede el límite de memoria WebAssembly.", declaracion)
        instrucciones = [
            f"i32.const {filas * columnas * bytes_elemento}",
            f"i32.const {bytes_elemento}",
            "call $array_alloc",
            f"local.set $local_{identificador}",
        ]
        for fila_indice, fila in enumerate(literales_fila):
            for columna_indice, elemento in enumerate(fila.expression()):
                instrucciones.append(f"local.get $local_{identificador}")
                instrucciones.extend(
                    _compilar_expresion(
                        elemento, referencias, locales, funciones, nombres_funcion, tipos
                    )
                )
                desplazamiento = (fila_indice * columnas + columna_indice) * bytes_elemento
                instrucciones.append(
                    _instruccion_almacenamiento_arreglo(tipo_elemento, desplazamiento)
                )
        return instrucciones
    arreglo = _info_arreglo(simbolos[identificador]["tipo"])
    if arreglo is not None:
        tipo_elemento, tamano_arreglo = arreglo
        if expresion is None:
            _error("Un arreglo local requiere un literal para inicializarse.", declaracion)
        literal = _obtener_literal_arreglo(expresion)
        if literal is None:
            if _layout_copia_compuesta(
                simbolos[identificador]["tipo"], nombres_funcion.estructuras,
                nombres_funcion.enumeraciones,
            ) is None:
                _error("La copia de este arreglo todavía no está implementada.", expresion)
            return [
                *_compilar_valor_para_local(
                    expresion, simbolos[identificador]["tipo"], referencias, locales, funciones,
                    nombres_funcion, tipos,
                ),
                f"local.set $local_{identificador}",
            ]
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
        *_compilar_valor_para_local(
            expresion, simbolos[identificador]["tipo"], referencias, locales, funciones,
            nombres_funcion, tipos,
        ),
        f"local.set $local_{identificador}",
    ]


def _compilar_valor_para_local(expresion, tipo_destino, referencias, locales, funciones,
                               nombres_funcion, tipos):
    """Copia compuestos Copy a un bloque nuevo antes de asignarlos a otro local."""
    layout = _layout_copia_compuesta(
        tipo_destino, nombres_funcion.estructuras, nombres_funcion.enumeraciones
    )
    if layout is None:
        return _compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        )
    tamano, alineacion = layout
    temporal = f"enum_{nombres_funcion.siguiente_enum}"
    nombres_funcion.siguiente_enum += 1
    nombres_funcion.temporales_enum.append(temporal)
    return [
        *_compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos
        ),
        f"local.set ${temporal}",
        f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
        "local.tee $direccion_asignacion", f"local.get ${temporal}", f"i32.const {tamano}",
        # memory.copy recibe destino, origen y tamaño; así origen y copia son independientes.
        "memory.copy", "local.get $direccion_asignacion",
    ]


def _compilar_asignacion(
    asignacion, referencias, simbolos, locales, funciones, nombres_funcion, tipos
):
    """Traduce = y operadores compuestos sin evaluar destinos con índice dos veces."""
    identificador = referencias[asignacion]
    if identificador not in locales:
        _error("La asignación no corresponde a una variable local i32.", asignacion)
    operador = asignacion.assignmentOp().getText()
    tipo_variable = simbolos[identificador]["tipo"]
    if asignacion.dereferenceTarget() is not None:
        # La referencia guarda una dirección: store modifica al origen, no al binding r.
        referencia = separar_referencia(tipo_variable)
        if referencia is None or not _escalar_prestable(referencia[1]):
            _error("Solo se admite escribir referencias escalares.", asignacion)
        tipo = referencia[1]
        expresion = _compilar_expresion(
            asignacion.expression(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if "normal" not in salidas_control(asignacion.expression()):
            return expresion
        if operador == "=":
            return [
                f"local.get $local_{identificador}", *expresion,
                _almacenamiento_escalar_memoria(tipo),
            ]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo}.add", "-=": f"{tipo}.sub", "*=": f"{tipo}.mul",
            "/=": "i32.div_s" if tipo == "i32" else "f64.div",
        }[operador]
        return [
            f"local.get $local_{identificador}", "local.tee $direccion_asignacion",
            _carga_escalar_memoria(tipo), *expresion, instruccion,
            f"local.set $valor_asignacion_{tipo}", "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo}", _almacenamiento_escalar_memoria(tipo),
        ]
    layout = _layout_copia_compuesta(
        tipo_variable, nombres_funcion.estructuras, nombres_funcion.enumeraciones
    )
    if layout is not None and not (
        asignacion.fieldAccess() or asignacion.tupleAccess() or asignacion.indexAccess()
    ):
        if operador != "=":
            _error("Las asignaciones compuestas de valores compuestos no están implementadas.", asignacion)
        return [
            *_compilar_valor_para_local(
                asignacion.expression(), tipo_variable, referencias, locales, funciones,
                nombres_funcion, tipos,
            ),
            f"local.set $local_{identificador}",
        ]
    if identificador in nombres_funcion.escalares_en_memoria:
        expresion = _compilar_expresion(
            asignacion.expression(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if "normal" not in salidas_control(asignacion.expression()):
            return expresion
        if operador == "=":
            return [
                f"local.get $local_{identificador}", *expresion,
                _almacenamiento_escalar_memoria(tipo_variable),
            ]
        if tipo_variable not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo_variable}.add", "-=": f"{tipo_variable}.sub",
            "*=": f"{tipo_variable}.mul",
            "/=": "i32.div_s" if tipo_variable == "i32" else "f64.div",
        }[operador]
        return [
            f"local.get $local_{identificador}", "local.tee $direccion_asignacion",
            _carga_escalar_memoria(tipo_variable), *expresion, instruccion,
            f"local.set $valor_asignacion_{tipo_variable}", "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo_variable}",
            _almacenamiento_escalar_memoria(tipo_variable),
        ]
    expresion = _compilar_expresion(
        asignacion.expression(), referencias, locales, funciones, nombres_funcion, tipos
    )
    if "normal" not in salidas_control(asignacion.expression()):
        return expresion
    if asignacion.fieldAccess():
        direccion, tipo = _compilar_direccion_estructura(
            asignacion, identificador, simbolos, nombres_funcion.estructuras
        )
        if operador == "=":
            return [
                *direccion,
                *expresion,
                _instruccion_almacenamiento_arreglo(tipo, 0),
            ]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo}.add",
            "-=": f"{tipo}.sub",
            "*=": f"{tipo}.mul",
            "/=": "i32.div_s" if tipo == "i32" else "f64.div",
        }[operador]
        return [
            *direccion,
            "local.tee $direccion_asignacion",
            _instruccion_carga_arreglo(tipo),
            *expresion,
            instruccion,
            f"local.set $valor_asignacion_{tipo}",
            "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo}",
            _instruccion_almacenamiento_arreglo(tipo, 0),
        ]
    if asignacion.tupleAccess():
        direccion, tipo = _compilar_direccion_tupla(asignacion, identificador, simbolos)
        if operador == "=":
            return [
                *direccion,
                *expresion,
                _instruccion_almacenamiento_arreglo(tipo, 0),
            ]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo}.add",
            "-=": f"{tipo}.sub",
            "*=": f"{tipo}.mul",
            "/=": "i32.div_s" if tipo == "i32" else "f64.div",
        }[operador]
        return [
            *direccion,
            "local.tee $direccion_asignacion",
            _instruccion_carga_arreglo(tipo),
            *expresion,
            instruccion,
            f"local.set $valor_asignacion_{tipo}",
            "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo}",
            _instruccion_almacenamiento_arreglo(tipo, 0),
        ]
    if asignacion.indexAccess():
        direccion, tipo = _compilar_direccion_asignacion(
            asignacion, identificador, referencias, simbolos, locales, funciones,
            nombres_funcion, tipos,
        )
        if operador == "=":
            return [
                *direccion,
                *expresion,
                _instruccion_almacenamiento_arreglo(tipo, 0),
            ]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo}.add",
            "-=": f"{tipo}.sub",
            "*=": f"{tipo}.mul",
            "/=": "i32.div_s" if tipo == "i32" else "f64.div",
        }[operador]
        # Guardar la dirección evita evaluar el índice dos veces en += y similares.
        return [
            *direccion,
            "local.tee $direccion_asignacion",
            _instruccion_carga_arreglo(tipo),
            *expresion,
            instruccion,
            f"local.set $valor_asignacion_{tipo}",
            "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo}",
            _instruccion_almacenamiento_arreglo(tipo, 0),
        ]
    if _info_arreglo(tipo_variable) is not None or _info_matriz(tipo_variable) is not None or _info_tupla(tipo_variable) is not None or _info_estructura(tipo_variable, nombres_funcion.estructuras) is not None:
        _error("La asignación completa de valores compuestos todavía no está implementada.", asignacion)
    if operador == "=":
        return [*expresion, f"local.set $local_{identificador}"]
    instrucciones = [f"local.get $local_{identificador}", *expresion]
    tipo = tipo_variable
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


def _compilar_direccion_tupla(asignacion, identificador, simbolos):
    """Obtiene la dirección del campo local sin compartir almacenamiento entre tuplas."""
    accesos = list(accesos_escritura(asignacion))
    if len(accesos) != 1 or accesos[0][0] != "campo":
        _error("Solo se admite la asignación directa a campos de tuplas locales.", asignacion)
    tipo_base = simbolos[identificador]["tipo"]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        tipo_base = referencia[1]
    tupla = _distribucion_tupla(tipo_base)
    if tupla is None:
        _error("La asignación no corresponde a una tupla local admitida.", asignacion)
    indice = int(accesos[0][1].getText()[1:])
    campos, _, _ = tupla
    if indice >= len(campos):
        _error("El campo de la tupla no está disponible para generar WASM.", asignacion)
    tipo, desplazamiento = campos[indice]
    instrucciones = [f"local.get $local_{identificador}"]
    if desplazamiento:
        instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
    return instrucciones, tipo


def _compilar_direccion_estructura(asignacion, identificador, simbolos, estructuras):
    """Calcula la dirección de un campo, incluso cuando la base es una &Estructura."""
    accesos = list(accesos_escritura(asignacion))
    if len(accesos) != 1 or accesos[0][0] != "nombre":
        _error("Solo se admite la asignación directa a campos de estructuras locales.", asignacion)
    tipo_base = simbolos[identificador]["tipo"]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        tipo_base = referencia[1]
    estructura = _distribucion_estructura(tipo_base, estructuras)
    if estructura is None:
        _error("La asignación no corresponde a una estructura local admitida.", asignacion)
    nombre = accesos[0][1].IDENT().getText()
    campos, _, _ = estructura
    if nombre not in campos:
        _error("El campo de la estructura no está disponible para generar WASM.", asignacion)
    tipo, desplazamiento = campos[nombre]
    instrucciones = [f"local.get $local_{identificador}"]
    if desplazamiento:
        instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
    return instrucciones, tipo


def _compilar_direccion_asignacion(
    asignacion, identificador, referencias, simbolos, locales, funciones, nombres_funcion, tipos
):
    """Calcula una dirección de elemento con las guardas existentes de $array_addr."""
    tipo_base = simbolos[identificador]["tipo"]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        tipo_base = referencia[1]
    accesos = asignacion.indexAccess()
    instrucciones = [f"local.get $local_{identificador}"]
    matriz = _info_matriz(tipo_base)
    if matriz is not None:
        tipo_elemento, filas, columnas = matriz
        if len(accesos) != 2:
            _error("Las matrices locales requieren exactamente dos índices.", asignacion)
        bytes_elemento = _tamano_elemento_arreglo(tipo_elemento)
        instrucciones.extend(
            _compilar_expresion(
                accesos[0].expression(), referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        instrucciones.extend([
            f"i32.const {filas}",
            f"i32.const {columnas * bytes_elemento}",
            "call $array_addr",
        ])
        instrucciones.extend(
            _compilar_expresion(
                accesos[1].expression(), referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        instrucciones.extend([
            f"i32.const {columnas}",
            f"i32.const {bytes_elemento}",
            "call $array_addr",
        ])
        return instrucciones, tipo_elemento

    arreglo = _info_arreglo(tipo_base)
    if arreglo is None or len(accesos) != 1:
        _error("Solo se admiten asignaciones a arreglos locales de una dimensión.", asignacion)
    tipo_elemento, tamano = arreglo
    instrucciones.extend(
        _compilar_expresion(
            accesos[0].expression(), referencias, locales, funciones, nombres_funcion, tipos
        )
    )
    instrucciones.extend([
        f"i32.const {tamano}",
        f"i32.const {_tamano_elemento_arreglo(tipo_elemento)}",
        "call $array_addr",
    ])
    return instrucciones, tipo_elemento


def _compilar_llamada(llamada, referencias, locales, funciones, nombres_funcion, tipos):
    """Compila imports read/print o llamadas RustiQ conservando el orden de argumentos."""
    incorporada = nombres_funcion.llamadas_incorporadas.get(llamada)
    if incorporada is not None:
        nombres_funcion.incorporadas_usadas.add(incorporada)
        if incorporada == "read":
            return ["call $read_i32"], "i32"
        argumentos = llamada.argumentList().expression()
        instrucciones = _compilar_expresion(
            argumentos[0], referencias, locales, funciones, nombres_funcion, tipos
        )
        if "normal" not in salidas_control(argumentos[0]):
            return instrucciones, "unit"
        return [*instrucciones, "call $print_i32"], "unit"

    nombre = llamada.IDENT().getText()
    firma = funciones.get(nombre)
    if firma is None or nombre not in nombres_funcion.nombres_funcion:
        _error(f"La función '{nombre}' no está disponible para generar WASM.", llamada)
    if any(
        tipo not in {"i32", "bool", "f64", "char", "String"}
        and not _referencia_admitida(tipo, nombres_funcion.estructuras)
        for tipo in firma["parametros"]
    ):
        _error(f"La función '{nombre}' usa parámetros no soportados.", llamada)
    if firma["retorno"] not in {"i32", "bool", "f64", "char", "String", "unit"}:
        _error(f"La función '{nombre}' tiene un retorno no soportado.", llamada)

    argumentos = []
    lista = llamada.argumentList()
    if lista is not None:
        argumentos = lista.expression()
    instrucciones = []
    for argumento in argumentos:
        # Cada argumento se deja en la pila antes de call, como exige la firma WASM.
        instrucciones.extend(
            _compilar_expresion(
                argumento, referencias, locales, funciones, nombres_funcion, tipos
            )
        )
        if "normal" not in salidas_control(argumento):
            return instrucciones, firma["retorno"]
    instrucciones.append(f"call $funcion_{nombres_funcion.nombres_funcion[nombre]}")
    return instrucciones, firma["retorno"]


def _compilar_bloque(
    bloque, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
    producir_valor=False,
):
    """Ejecuta sentencias en orden y sólo deja la expresión final cuando se necesita."""
    instrucciones = []
    for sentencia in bloque.statement():
        instrucciones.extend(
            _compilar_sentencia(
                sentencia, declaraciones, referencias, simbolos, locales,
                tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
            )
        )
        if "normal" not in salidas_control(sentencia):
            return instrucciones
    expresion = bloque.expression()
    if expresion is None:
        return instrucciones
    compilar_expresion = (
        _compilar_expresion_unit
        if tipos_expresiones.get(expresion) == "unit"
        else _compilar_expresion
    )
    instrucciones.extend(
        compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos_expresiones
        )
    )
    if not producir_valor and tipos_expresiones.get(expresion) != "unit" and "normal" in salidas_control(expresion):
        instrucciones.append("drop")
    return instrucciones


def _compilar_if(
    condicional, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
):
    """Compila las ramas por separado para que WASM ejecute sólo la condición elegida."""
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
    """Representa while y loop con block/loop y saltos br o br_if de WebAssembly."""
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
    """Dirige cada sentencia del árbol a su generador y cuida la pila de WASM."""
    if sentencia.constLocalDecl() is not None:
        # Kevin ya calculó la constante; declararla no debe ejecutar su inicializador otra vez.
        identificador = declaraciones.get(sentencia.constLocalDecl())
        constante = nombres_funcion.constantes.get(identificador)
        if constante is None or not constante["es_constante"]:
            _error("La constante local no está disponible para generar WASM.", sentencia)
        return []
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
    if sentencia.expression() is not None:
        # El punto y coma convierte el valor en efecto: drop sólo se usa si existe un valor.
        expresion = sentencia.expression()
        tipo = tipos_expresiones.get(expresion)
        compilar = _compilar_expresion_unit if tipo == "unit" else _compilar_expresion
        instrucciones = compilar(
            expresion, referencias, locales, funciones, nombres_funcion, tipos_expresiones
        )
        if "normal" not in salidas_control(expresion) or tipo == "unit":
            return instrucciones
        return [*instrucciones, "drop"]
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
        instrucciones = _compilar_expresion(
            expresion, referencias, locales, funciones, nombres_funcion, tipos_expresiones
        )
        return [*instrucciones, *(["return"] if "normal" in salidas_control(expresion) else [])]
    if sentencia.block() is not None:
        return _compilar_bloque(
            sentencia.block(), declaraciones, referencias, simbolos, locales,
            tipos_expresiones, tipo_retorno, funciones, nombres_funcion, ciclos,
        )
    _error("Esta sentencia todavía no está implementada.", sentencia)


def _compilar_funcion(funcion, analisis, indice, nombres_funcion):
    """Prepara locales, parámetros y cuerpo de una función antes de exportarla."""
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
        tipo = analisis["simbolos"][identificador]["tipo"]
        referencia = separar_referencia(tipo)
        if referencia is not None:
            if not _referencia_admitida(tipo, nombres_funcion.estructuras):
                _error("Solo se admiten parámetros referencia con layouts locales compatibles.", funcion)
            continue
        if _info_arreglo(tipo) is not None or _info_matriz(tipo) is not None or _info_tupla(tipo) is not None or _info_estructura(tipo, nombres_funcion.estructuras) is not None or _info_enum(tipo, nombres_funcion.enumeraciones) is not None:
            _error("Los parámetros de valores compuestos todavía no están implementados.", funcion)
    for identificador in variables:
        tipo = analisis["simbolos"][identificador]["tipo"]
        referencia = separar_referencia(tipo)
        if referencia is not None and not _referencia_admitida(tipo, nombres_funcion.estructuras):
            _error("Solo se admiten referencias con layouts locales compatibles.", funcion)
        if tipo not in {"i32", "bool", "f64", "char", "String"} and referencia is None and _info_arreglo(tipo) is None and _info_matriz(tipo) is None and _info_tupla(tipo) is None and _info_estructura(tipo, nombres_funcion.estructuras) is None and _info_enum(tipo, nombres_funcion.enumeraciones) is None:
            _error("El tipo de parámetro o variable no está implementado.", funcion)
    origenes_prestados = {
        prestamo["simbolo_id"]
        for prestamo in analisis["prestamos"].values()
        if analisis["simbolos"][prestamo["simbolo_id"]]["funcion"] == nombre
    }
    # Los escalares prestados necesitan una celda; los compuestos ya son punteros propios.
    declaraciones_por_id = {
        identificador: declaracion
        for declaracion, identificador in analisis["declaraciones"].items()
    }
    escalares_en_memoria = set()
    for identificador in origenes_prestados:
        tipo = analisis["simbolos"][identificador]["tipo"]
        if identificador in parametros:
            _error("Solo se admiten préstamos de variables locales con layouts compatibles.", funcion)
        if _escalar_prestable(tipo):
            escalares_en_memoria.add(identificador)
        elif not _compuesto_prestable(tipo, nombres_funcion.estructuras):
            _error("Solo se admiten préstamos de variables locales con layouts compatibles.", funcion)
        if type(declaraciones_por_id.get(identificador)).__name__ == "PatternContext":
            _error("Los préstamos de receptores de match todavía no están implementados.", funcion)
    parametros_wat = " ".join(
        f"(param $local_{identificador} "
        f"{_tipo_wasm(analisis['simbolos'][identificador]['tipo'], nombres_funcion.estructuras, nombres_funcion.enumeraciones)})"
        for identificador in sorted(parametros)
    )
    # Los parámetros referencia también son i32 porque transportan una dirección.
    resultado_wat = "" if tipo_retorno == "unit" else f" (result {_tipo_wasm(tipo_retorno)})"
    declaraciones_locales = "\n".join(
        f"    (local $local_{identificador} "
        f"{'i32' if identificador in escalares_en_memoria else _tipo_wasm(analisis['simbolos'][identificador]['tipo'], nombres_funcion.estructuras, nombres_funcion.enumeraciones)})"
        for identificador in sorted(variables - parametros)
    )
    temporales_asignacion = "\n".join([
        "    (local $direccion_asignacion i32)",
        "    (local $valor_asignacion_i32 i32)",
        "    (local $valor_asignacion_f64 f64)",
    ])
    instrucciones = []
    ciclos = {"siguiente": 0, "activos": []}
    nombres_funcion.ciclos = ciclos
    nombres_funcion.tipo_retorno_actual = tipo_retorno
    nombres_funcion.temporales_match = []
    nombres_funcion.siguiente_match = 0
    nombres_funcion.temporales_enum = []
    nombres_funcion.siguiente_enum = 0
    nombres_funcion.prestamos = analisis["prestamos"]
    nombres_funcion.escalares_en_memoria = escalares_en_memoria
    nombres_funcion.origenes_prestados = origenes_prestados
    continua = True
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
        if "normal" not in salidas_control(sentencia):
            continua = False
            break
    expresion_final = funcion.block().expression()
    retorno_final_emitido = False
    if expresion_final is not None and continua:
        compilar_expresion = (
            _compilar_expresion_unit
            if analisis["tipos_expresiones"].get(expresion_final) == "unit"
            else _compilar_expresion
        )
        instrucciones.extend(
            compilar_expresion(
                expresion_final,
                analisis["referencias"],
                variables,
                analisis["funciones"],
                nombres_funcion,
                analisis["tipos_expresiones"],
            )
        )
        if tipo_retorno != "unit" and "normal" in salidas_control(expresion_final):
            instrucciones.append("return")
            retorno_final_emitido = True
        elif tipo_retorno == "unit" and analisis["tipos_expresiones"].get(expresion_final) != "unit" and "normal" in salidas_control(expresion_final):
            instrucciones.append("drop")
    if tipo_retorno != "unit" and not retorno_final_emitido:
        instrucciones.append("unreachable")
    cuerpo = "\n    ".join(instrucciones)
    temporales_match = "\n".join(
        f"    (local ${temporal} i32)" for temporal in nombres_funcion.temporales_match
    )
    temporales_enum = "\n".join(
        f"    (local ${temporal} i32)" for temporal in nombres_funcion.temporales_enum
    )
    locales_wat = "\n" + "\n".join(
        parte for parte in (
            declaraciones_locales, temporales_asignacion, temporales_match, temporales_enum
        ) if parte
    )
    return (
        f"  (func $funcion_{indice} {parametros_wat}{resultado_wat}{locales_wat}\n"
        f"    {cuerpo}\n"
        f"  )\n"
        f"  (export \"{nombre}\" (func $funcion_{indice}))"
    )


def _validar_constantes_globales(arbol, declaraciones, constantes):
    """Rechaza controladamente tipos globales sin representación Wasm actual."""
    tipos_admitidos = {"i32", "f64", "bool", "char", "String"}
    for declaracion in arbol.constDecl():
        constante = constantes[declaraciones[declaracion]]
        if constante["tipo"] not in tipos_admitidos:
            _error(
                f"Las constantes globales de tipo {constante['tipo']} todavía no están implementadas.",
                declaracion,
            )


def _validar_enumeraciones(arbol, enumeraciones):
    for declaracion in arbol.enumDecl():
        tipo = declaracion.IDENT().getText()
        enumeracion = enumeraciones[tipo]
        if enumeracion.get("datos_variantes") and _distribucion_enum(tipo, enumeraciones) is None:
            _error("Los datos asociados de esta enumeración todavía no están implementados.", declaracion)


def _imports_incorporados(incorporadas_usadas):
    """Declara solamente las importaciones que requieren las llamadas del programa."""
    imports = []
    if "read" in incorporadas_usadas:
        imports.append('  (import "env" "read_i32" (func $read_i32 (result i32)))')
    if "print" in incorporadas_usadas:
        imports.append('  (import "env" "print_i32" (func $print_i32 (param i32)))')
    return "\n".join(imports)


def compilar_programa(codigo):
    """Compila RustiQ a WebAssembly y devuelve ``valido`, `errores`, `wat`, `wasm`.

    Primero delega léxico, sintaxis, tipos, ownership y borrowing al frontend.
    Sólo con ese resultado válido se genera WAT, se valida con Wasmtime y se
    entrega el binario real al editor o al ejecutor de escritorio.
    """
    analisis = analizar_programa(codigo)
    if not analisis["valido"]:
        return {"valido": False, "errores": analisis["errores"], "wat": None, "wasm": None}
    try:
        arbol = analisis["arbol"]
        funciones = arbol.functionDecl()
        if not funciones:
            _error("El programa debe declarar al menos una función.", arbol)
        constantes = {
            identificador: simbolo
            for identificador, simbolo in analisis["simbolos"].items()
            if simbolo["es_constante"]
        }
        _validar_constantes_globales(arbol, analisis["declaraciones"], constantes)
        _validar_enumeraciones(arbol, analisis["enumeraciones"])
        estado = EstadoModulo(
            {
                funcion.IDENT().getText(): indice
                for indice, funcion in enumerate(funciones)
            },
            MemoriaStrings(),
            constantes,
            analisis["estructuras"],
            analisis["enumeraciones"],
            analisis["declaraciones"],
            analisis["simbolos"],
            analisis["llamadas_incorporadas"],
            set(),
        )
        wat_funciones = [
            _compilar_funcion(funcion, analisis, indice, estado)
            for indice, funcion in enumerate(funciones)
        ]
        # El módulo reúne memoria, helpers internos, funciones del programa y datos UTF-8.
        datos = estado.memoria.wat()
        imports = _imports_incorporados(estado.incorporadas_usadas)
        wat = (
            "(module\n"
            + (imports + "\n" if imports else "")
            + f"  (memory (export \"memory\") {estado.memoria.paginas_necesarias()})\n"
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
    """Instancia el binario con Wasmtime y llama una exportación para las pruebas.

    Permite pasar argumentos cuando la exportación los necesita.
    """
    motor = wasmtime.Engine()
    modulo = wasmtime.Module(motor, wasm)
    almacen = wasmtime.Store(motor)
    instancia = wasmtime.Instance(almacen, modulo, [])
    return instancia.exports(almacen)[funcion](almacen, *argumentos)


def ejecutar_string_wasm(wasm, funcion="main", *argumentos):
    """Ejecuta una función String y reconstruye el texto desde el descriptor en memoria."""
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
