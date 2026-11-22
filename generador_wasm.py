"""Backend WebAssembly mínimo para el subconjunto aritmético de RustiQ."""

from __future__ import annotations

from dataclasses import dataclass
import json

import wasmtime

from main import analizar_programa
from flujo_control import salidas_control
from tipos_compuestos import accesos_escritura, accesos_lectura, separar_tipo_tupla
from tipos_referencias import separar_referencia
from clasificacion_propiedad import clasificar_tipo


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


def _tamano_y_alineacion_prestamo(tipo, enumeraciones):
    tamano_alineacion = _tamano_y_alineacion_escalar(tipo)
    if tamano_alineacion is not None:
        return tamano_alineacion
    if _info_enum(tipo, enumeraciones) is not None:
        return 4, 4
    if tipo == "String":
        return 4, 4
    return None


def _referencia_admitida(tipo, estructuras, enumeraciones=None):
    """Comprueba si una referencia usa un layout que el generador ya conoce."""
    referencia = separar_referencia(tipo)
    if referencia is None:
        return False
    return _escalar_prestable(referencia[1]) or referencia[1] == "String" or _info_enum(
        referencia[1], enumeraciones
    ) is not None or _compuesto_prestable(
        referencia[1], estructuras, enumeraciones
    )


def _compuesto_prestable(tipo, estructuras, enumeraciones=None):
    """Limita préstamos compuestos a layouts locales con elementos Copy básicos."""
    layout = _layout_recursivo(tipo, estructuras, enumeraciones)
    return layout is not None and (
        _distribucion_estructura(tipo, estructuras, enumeraciones) is not None
        or _distribucion_tupla(tipo, estructuras, enumeraciones) is not None
        or _info_arreglo(tipo) is not None
    )


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
    if not elemento or not tamano.isdigit():
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


def _partes_arreglo_recursivo(tipo):
    if not tipo.startswith("[") or not tipo.endswith("]"):
        return None
    profundidad = 0
    for indice, caracter in enumerate(tipo[1:-1], 1):
        if caracter == "[":
            profundidad += 1
        elif caracter == "]":
            profundidad -= 1
        elif caracter == ";" and profundidad == 0:
            elemento, cantidad = tipo[1:indice], tipo[indice + 1:-1]
            return (elemento, int(cantidad)) if cantidad.isdigit() else None
    return None


def _layout_recursivo(tipo, estructuras, enumeraciones=None, pila=()):
    if tipo in {"i32", "bool", "char", "String"}:
        return {"tipo": tipo, "tamano": 4, "alineacion": 4, "wasm": "i32"}
    if tipo == "f64":
        return {"tipo": tipo, "tamano": 8, "alineacion": 8, "wasm": "f64"}
    if tipo in pila:
        return None
    arreglo = _partes_arreglo_recursivo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        interno = _layout_recursivo(elemento, estructuras, enumeraciones, pila)
        if interno is None or cantidad > MAX_DIRECCION_I32 // max(1, interno["tamano"]):
            return None
        return {"tipo": tipo, "tamano": interno["tamano"] * cantidad, "alineacion": interno["alineacion"], "elemento": interno, "cantidad": cantidad, "wasm": "i32"}
    campos = _info_tupla(tipo)
    if campos is not None:
        lista = [(str(indice), campo) for indice, campo in enumerate(campos)]
    else:
        estructura = _info_estructura(tipo, estructuras)
        if estructura is None and _info_enum(tipo, enumeraciones) is not None:
            return {"tipo": tipo, "tamano": 4, "alineacion": 4, "wasm": "i32"}
        if estructura is None:
            return None
        lista = list(estructura.items())
    desplazamiento = 0
    alineacion = 4
    resultado = {}
    for nombre, campo in lista:
        interno = _layout_recursivo(campo, estructuras, enumeraciones, (*pila, tipo))
        if interno is None:
            return None
        paso = 4 if interno.get("elemento") is not None or _info_tupla(campo) is not None or _info_estructura(campo, estructuras) is not None else interno["tamano"]
        campo_alineacion = 4 if paso == 4 and interno["tamano"] != 4 else interno["alineacion"]
        desplazamiento = (desplazamiento + campo_alineacion - 1) & ~(campo_alineacion - 1)
        resultado[nombre] = (campo, desplazamiento, interno)
        desplazamiento += paso
        alineacion = max(alineacion, campo_alineacion)
    return {"tipo": tipo, "tamano": desplazamiento, "alineacion": alineacion, "campos": resultado, "wasm": "i32"}


def _info_tupla(tipo):
    campos = separar_tipo_tupla(tipo)
    if campos is None or len(campos) < 2:
        return None
    return campos


def _tipo_compuesto_local(tipo, estructuras):
    return _info_tupla(tipo) is not None or _info_estructura(tipo, estructuras) is not None


def _tamano_y_alineacion_campo(tipo, estructuras, enumeraciones=None):
    if tipo == "f64":
        return 8, 8
    if tipo in {"i32", "bool", "char", "String"}:
        return 4, 4
    if _tipo_compuesto_local(tipo, estructuras):
        return 4, 4
    if _partes_arreglo_recursivo(tipo) is not None:
        return 4, 4
    if _info_enum(tipo, enumeraciones) is not None:
        return 4, 4
    return None


def _distribucion_tupla(tipo, estructuras=None, enumeraciones=None):
    """Calcula dónde empieza cada campo de una tupla dentro de memoria lineal."""
    campos = _info_tupla(tipo)
    if campos is None:
        return None
    desplazamiento = 0
    distribucion = []
    for campo in campos:
        datos = _tamano_y_alineacion_campo(campo, estructuras, enumeraciones)
        if datos is None:
            return None
        tamano_campo, alineacion = datos
        desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
        distribucion.append((campo, desplazamiento))
        desplazamiento += tamano_campo
    return distribucion, desplazamiento, max(8 if campo == "f64" else 4 for campo in campos)


def _info_estructura(tipo, estructuras):
    campos = (estructuras or {}).get(tipo)
    return campos


def _info_enum(tipo, enumeraciones):
    return (enumeraciones or {}).get(tipo)


def _enum_tiene_datos(tipo, enumeraciones):
    enumeracion = _info_enum(tipo, enumeraciones)
    return enumeracion is not None and bool(enumeracion.get("datos_variantes"))


def _distribucion_enum(tipo, enumeraciones, estructuras=None):
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
            datos_campo = _tamano_y_alineacion_campo(campo, estructuras, enumeraciones)
            if datos_campo is None:
                return None
            tamano_campo, alineacion = datos_campo
            desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
            campos.append((campo, desplazamiento))
            desplazamiento += tamano_campo
            alineacion_maxima = max(alineacion_maxima, alineacion)
        distribucion[variante] = (etiqueta, campos)
        tamano_maximo = max(tamano_maximo, desplazamiento)
    return distribucion, tamano_maximo, alineacion_maxima


def _distribucion_estructura(tipo, estructuras, enumeraciones=None):
    """Respeta el orden de campos declarado por Kevin y alinea f64 a ocho bytes."""
    campos = _info_estructura(tipo, estructuras)
    if campos is None:
        return None
    desplazamiento = 0
    distribucion = {}
    alineacion_maxima = 4
    for nombre, campo in campos.items():
        datos = _tamano_y_alineacion_campo(campo, estructuras, enumeraciones)
        if datos is None:
            return None
        tamano_campo, alineacion = datos
        desplazamiento = (desplazamiento + alineacion - 1) & ~(alineacion - 1)
        distribucion[nombre] = (campo, desplazamiento)
        desplazamiento += tamano_campo
        alineacion_maxima = max(alineacion_maxima, alineacion)
    return distribucion, desplazamiento, alineacion_maxima


def _layout_copia_compuesta(tipo, estructuras, enumeraciones):
    """Indica cuánto se debe copiar para que un valor Copy no comparta su bloque."""
    matriz = _info_matriz(tipo)
    if matriz is not None and _partes_arreglo_recursivo(matriz[0]) is None:
        elemento, filas, columnas = matriz
        if elemento in {"i32", "f64", "bool", "char"}:
            paso = _tamano_elemento_arreglo(elemento)
            if columnas and filas <= MAX_DIRECCION_I32 // columnas and filas * columnas <= MAX_DIRECCION_I32 // paso:
                return filas * columnas * paso, paso
        if (clasificar_tipo(tipo, estructuras, enumeraciones) == "Copy"
                and (_distribucion_tupla(elemento, estructuras, enumeraciones) is not None
                     or _distribucion_estructura(elemento, estructuras, enumeraciones) is not None)
                and columnas and filas <= MAX_DIRECCION_I32 // columnas
                and filas * columnas <= MAX_DIRECCION_I32 // 4):
            return filas * columnas * 4, 4
        return None
    arreglo = _info_arreglo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        if elemento in {"i32", "f64", "bool", "char"}:
            paso = _tamano_elemento_arreglo(elemento)
            if cantidad <= MAX_DIRECCION_I32 // paso:
                return cantidad * paso, paso
        if (clasificar_tipo(tipo, estructuras, enumeraciones) == "Copy"
                and _layout_copia_compuesta(elemento, estructuras, enumeraciones) is not None
                and cantidad <= MAX_DIRECCION_I32 // 4):
            return cantidad * 4, 4
        return None
    tupla = _distribucion_tupla(tipo, estructuras, enumeraciones)
    if tupla is not None:
        if clasificar_tipo(tipo, estructuras, enumeraciones) != "Copy":
            return None
        _, tamano, alineacion = tupla
        return tamano, alineacion
    estructura = _distribucion_estructura(tipo, estructuras, enumeraciones)
    if estructura is not None:
        if clasificar_tipo(tipo, estructuras, enumeraciones) != "Copy":
            return None
        _, tamano, alineacion = estructura
        return tamano, alineacion
    enumeracion = _info_enum(tipo, enumeraciones)
    if (enumeracion is not None
            and clasificar_tipo(tipo, estructuras, enumeraciones) == "Copy"):
        distribucion = _distribucion_enum(tipo, enumeraciones, estructuras)
        if distribucion is None:
            return None
        _, tamano, alineacion = distribucion
        return tamano, alineacion
    return None


def _metadatos_layout(tipo, estructuras, enumeraciones, pila=()):
    if tipo in {"i32", "f64", "bool", "char", "String"}:
        return {"clase": tipo}
    if tipo in pila:
        return None
    arreglo = _partes_arreglo_recursivo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        interno = _metadatos_layout(elemento, estructuras, enumeraciones, pila)
        if interno is None:
            return None
        layout = _layout_recursivo(elemento, estructuras, enumeraciones)
        if layout is None:
            return None
        paso = 4 if (layout.get("elemento") is not None
                     or _distribucion_tupla(elemento, estructuras, enumeraciones) is not None
                     or _distribucion_estructura(elemento, estructuras, enumeraciones) is not None
                     or _enum_tiene_datos(elemento, enumeraciones)) else layout["tamano"]
        return {"clase": "arreglo", "cantidad": cantidad, "paso": paso, "elemento": interno}
    tupla = _distribucion_tupla(tipo, estructuras, enumeraciones)
    if tupla is not None:
        campos, _, _ = tupla
        resultado = []
        for campo, desplazamiento in campos:
            interno = _metadatos_layout(campo, estructuras, enumeraciones, (*pila, tipo))
            if interno is None:
                return None
            resultado.append({"desplazamiento": desplazamiento, "valor": interno})
        return {"clase": "tupla", "campos": resultado}
    estructura = _distribucion_estructura(tipo, estructuras, enumeraciones)
    if estructura is not None:
        resultado = []
        for nombre, (campo, desplazamiento) in estructura[0].items():
            interno = _metadatos_layout(campo, estructuras, enumeraciones, (*pila, tipo))
            if interno is None:
                return None
            resultado.append({"nombre": nombre, "desplazamiento": desplazamiento, "valor": interno})
        return {"clase": "estructura", "nombre": tipo, "campos": resultado}
    enumeracion = _info_enum(tipo, enumeraciones)
    if enumeracion is None:
        return None
    distribucion = _distribucion_enum(tipo, enumeraciones, estructuras)
    variantes = []
    for nombre, etiqueta in enumeracion["variantes"].items():
        campos = []
        if distribucion is not None:
            _, distribucion_campos = distribucion[0][nombre]
            for campo, desplazamiento in distribucion_campos:
                interno = _metadatos_layout(campo, estructuras, enumeraciones, (*pila, tipo))
                if interno is None:
                    return None
                campos.append({"desplazamiento": desplazamiento, "valor": interno})
        variantes.append({"nombre": nombre, "etiqueta": etiqueta, "campos": campos})
    return {"clase": "enum", "nombre": tipo, "con_datos": distribucion is not None, "variantes": variantes}


def _metadatos_main(analisis, estructuras, enumeraciones):
    firma = analisis["funciones"].get("main")
    if firma is None:
        return None
    if firma["parametros"]:
        return None
    if firma["retorno"] == "unit":
        return {"version": 1, "retorno": {"clase": "unit"}}
    layout = _metadatos_layout(firma["retorno"], estructuras, enumeraciones)
    if layout is None:
        return None
    return {"version": 1, "retorno": layout}


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


def _nuevo_temporal(nombres_funcion):
    temporal = f"enum_{nombres_funcion.siguiente_enum}"
    nombres_funcion.siguiente_enum += 1
    nombres_funcion.temporales_enum.append(temporal)
    return temporal


def _compilar_literal_compuesto(contexto, tipo, referencias, locales, funciones, nombres_funcion, tipos):
    tupla = _distribucion_tupla(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    estructura = _distribucion_estructura(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    if tupla is None and estructura is None:
        _error("El literal compuesto todavía no está implementado.", contexto)
    campos, tamano, alineacion = tupla if tupla is not None else estructura
    temporal = _nuevo_temporal(nombres_funcion)
    instrucciones = [f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc", f"local.set ${temporal}"]
    if tupla is not None:
        literal = contexto.tupleLiteral() if hasattr(contexto, "tupleLiteral") else _obtener_literal_tupla(contexto)
        if literal is None:
            _error("El literal de tupla no está disponible para generar WASM.", contexto)
        pares = zip(campos, literal.expression())
    else:
        literal = contexto.structLiteral() if hasattr(contexto, "structLiteral") else _obtener_literal_estructura(contexto)
        if literal is None:
            _error("El constructor de estructura no está disponible para generar WASM.", contexto)
        pares = []
        for inicializador in literal.fieldInit():
            nombre = inicializador.IDENT().getText()
            pares.append((campos[nombre], inicializador.expression()))
    for (tipo_campo, desplazamiento), valor in pares:
        instrucciones.append(f"local.get ${temporal}")
        if _info_matriz(tipo_campo) is not None and _obtener_literal_arreglo(valor) is not None:
            instrucciones.extend(_compilar_expresion(
                valor, referencias, locales, funciones, nombres_funcion, tipos
            ))
        else:
            instrucciones.extend(_compilar_valor_para_local(
                valor, tipo_campo, referencias, locales, funciones, nombres_funcion, tipos
            ))
        instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_campo, desplazamiento))
    return [*instrucciones, f"local.get ${temporal}"]


def _compilar_literal_arreglo_recursivo(literal, tipo, referencias, locales, funciones, nombres_funcion, tipos):
    partes = _partes_arreglo_recursivo(tipo)
    if partes is None:
        _error("El literal de arreglo no tiene un layout disponible.", literal)
    tipo_elemento, cantidad = partes
    layout = _layout_recursivo(tipo_elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    valores = literal.expression()
    if layout is None or len(valores) != cantidad:
        _error("El literal de arreglo todavía no está implementado para este tipo.", literal)
    temporal = _nuevo_temporal(nombres_funcion)
    paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(tipo_elemento, nombres_funcion.estructuras) is not None or _distribucion_estructura(tipo_elemento, nombres_funcion.estructuras) is not None else layout["tamano"]
    instrucciones = [f"i32.const {paso * cantidad}", f"i32.const {4 if paso == 4 else layout['alineacion']}", "call $array_alloc", f"local.set ${temporal}"]
    for indice, valor in enumerate(valores):
        instrucciones.append(f"local.get ${temporal}")
        instrucciones.extend(_compilar_valor_para_local(valor, tipo_elemento, referencias, locales, funciones, nombres_funcion, tipos))
        instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_elemento, indice * paso))
    return [*instrucciones, f"local.get ${temporal}"]


def _compilar_accesos_compuestos(instrucciones, tipo, accesos, estructuras, cargar_final=True):
    for indice, (clase, acceso) in enumerate(accesos):
        final = indice == len(accesos) - 1
        if clase == "nombre":
            datos = _distribucion_estructura(tipo, estructuras)
            nombre = acceso.IDENT().getText()
            if datos is None or nombre not in datos[0]:
                _error("El campo de la estructura no está disponible para generar WASM.", acceso)
            siguiente, desplazamiento = datos[0][nombre]
        elif clase == "campo":
            datos = _distribucion_tupla(tipo, estructuras)
            posicion = int(acceso.getText()[1:])
            if datos is None or posicion >= len(datos[0]):
                _error("El campo de la tupla no está disponible para generar WASM.", acceso)
            siguiente, desplazamiento = datos[0][posicion]
        else:
            _error("Este acceso compuesto todavía no está implementado.", acceso)
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        if not final:
            instrucciones.append("i32.load")
        elif cargar_final:
            instrucciones.append(_instruccion_carga_arreglo(siguiente))
        tipo = siguiente
    return instrucciones, tipo


def _resolver_accesos(instrucciones, tipo, accesos, referencias, locales, funciones, nombres_funcion, tipos, cargar_final=True):
    for indice, (clase, acceso) in enumerate(accesos):
        final = indice == len(accesos) - 1
        if clase == "nombre":
            datos = _distribucion_estructura(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
            nombre = acceso.IDENT().getText()
            if datos is None or nombre not in datos[0]:
                _error("El campo de la estructura no está disponible para generar WASM.", acceso)
            siguiente, desplazamiento = datos[0][nombre]
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        elif clase == "campo":
            datos = _distribucion_tupla(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
            posicion = int(acceso.getText()[1:])
            if datos is None or posicion >= len(datos[0]):
                _error("El campo de la tupla no está disponible para generar WASM.", acceso)
            siguiente, desplazamiento = datos[0][posicion]
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        else:
            partes = _partes_arreglo_recursivo(tipo)
            if partes is None:
                _error("El índice no corresponde a un arreglo disponible.", acceso)
            siguiente, cantidad = partes
            layout = _layout_recursivo(siguiente, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
            if layout is None:
                _error("El elemento indexado no tiene layout disponible.", acceso)
            paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(siguiente, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _distribucion_estructura(siguiente, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _info_enum(siguiente, nombres_funcion.enumeraciones) is not None else layout["tamano"]
            expresion_indice = acceso.expression() if hasattr(acceso, "expression") else acceso
            instrucciones.extend(_compilar_expresion(expresion_indice, referencias, locales, funciones, nombres_funcion, tipos))
            instrucciones.extend([f"i32.const {cantidad}", f"i32.const {paso}", "call $array_addr"])
        representado_puntero = _partes_arreglo_recursivo(siguiente) is not None or _distribucion_tupla(siguiente, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _distribucion_estructura(siguiente, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _enum_tiene_datos(siguiente, nombres_funcion.enumeraciones)
        if not final:
            if not representado_puntero:
                _error("No se puede continuar un acceso después de un valor escalar.", acceso)
            instrucciones.append("i32.load")
        elif cargar_final:
            instrucciones.append(_instruccion_carga_arreglo(siguiente))
        tipo = siguiente
    return instrucciones, tipo


def _compilar_constante(simbolo, estado, contexto):
    """Convierte el valor ya calculado por Kevin en su literal WebAssembly.

    Así las constantes globales y locales nunca vuelven a evaluar su inicializador
    durante la ejecución del WASM.
    """
    tipo = simbolo["tipo"]
    valor = simbolo["valor"]
    return _compilar_valor_constante(tipo, valor, estado, contexto)


def _compilar_valor_constante(tipo, valor, estado, contexto):
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
    enumeracion = _info_enum(tipo, estado.enumeraciones)
    if enumeracion is not None:
        distribucion = _distribucion_enum(tipo, estado.enumeraciones, estado.estructuras)
        if distribucion is None:
            return [f"i32.const {valor['etiqueta']}"]
        variantes, tamano, alineacion = distribucion
        etiqueta, campos = variantes[valor["variante"]]
        temporal = _nuevo_temporal(estado)
        instrucciones = [
            f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
            f"local.set ${temporal}", f"local.get ${temporal}",
            f"i32.const {etiqueta}", "i32.store",
        ]
        for (tipo_campo, desplazamiento), dato in zip(campos, valor["datos"]):
            instrucciones.extend([f"local.get ${temporal}"])
            instrucciones.extend(_compilar_valor_constante(tipo_campo, dato, estado, contexto))
            instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_campo, desplazamiento))
        return [*instrucciones, f"local.get ${temporal}"]
    matriz = _info_matriz(tipo)
    if matriz is not None and matriz[0] in {"i32", "f64", "bool", "char", "String"}:
        elemento, filas, columnas = matriz
        paso = _tamano_elemento_arreglo(elemento)
        temporal = _nuevo_temporal(estado)
        instrucciones = [
            f"i32.const {filas * columnas * paso}",
            f"i32.const {paso}", "call $array_alloc", f"local.set ${temporal}",
        ]
        for fila, valores in enumerate(valor):
            for columna, dato in enumerate(valores):
                instrucciones.append(f"local.get ${temporal}")
                instrucciones.extend(_compilar_valor_constante(elemento, dato, estado, contexto))
                instrucciones.append(_instruccion_almacenamiento_arreglo(
                    elemento, (fila * columnas + columna) * paso
                ))
        return [*instrucciones, f"local.get ${temporal}"]
    arreglo = _partes_arreglo_recursivo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        layout = _layout_recursivo(elemento, estado.estructuras, estado.enumeraciones)
        if layout is None or len(valor) != cantidad:
            _error(f"La constante global de tipo {tipo} no tiene layout disponible.", contexto)
        paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(elemento, estado.estructuras, estado.enumeraciones) is not None or _distribucion_estructura(elemento, estado.estructuras, estado.enumeraciones) is not None or _info_enum(elemento, estado.enumeraciones) is not None else layout["tamano"]
        temporal = _nuevo_temporal(estado)
        instrucciones = [
            f"i32.const {paso * cantidad}",
            f"i32.const {4 if paso == 4 else layout['alineacion']}",
            "call $array_alloc", f"local.set ${temporal}",
        ]
        for indice, dato in enumerate(valor):
            instrucciones.append(f"local.get ${temporal}")
            instrucciones.extend(_compilar_valor_constante(elemento, dato, estado, contexto))
            instrucciones.append(_instruccion_almacenamiento_arreglo(elemento, indice * paso))
        return [*instrucciones, f"local.get ${temporal}"]
    tupla = _distribucion_tupla(tipo, estado.estructuras, estado.enumeraciones)
    estructura = _distribucion_estructura(tipo, estado.estructuras, estado.enumeraciones)
    if tupla is None and estructura is None:
        _error(f"Las constantes globales de tipo {tipo} todavía no están implementadas.", contexto)
    campos, tamano, alineacion = tupla if tupla is not None else estructura
    temporal = _nuevo_temporal(estado)
    instrucciones = [
        f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
        f"local.set ${temporal}",
    ]
    pares = zip(campos, valor) if tupla is not None else (
        ((datos, valor["campos"][nombre]) for nombre, datos in campos.items())
    )
    for (tipo_campo, desplazamiento), dato in pares:
        instrucciones.append(f"local.get ${temporal}")
        instrucciones.extend(_compilar_valor_constante(tipo_campo, dato, estado, contexto))
        instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_campo, desplazamiento))
    return [*instrucciones, f"local.get ${temporal}"]


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
    izquierda = _compilar_aditiva(
        operandos[0], referencias, locales, funciones, nombres_funcion, tipos
    )
    if len(operandos) == 1:
        return izquierda
    if "normal" not in salidas_control(operandos[0]):
        return izquierda
    operador = contexto.relOp().getText()
    derecha = _compilar_aditiva(
        operandos[1], referencias, locales, funciones, nombres_funcion, tipos
    )
    if "normal" not in salidas_control(operandos[1]):
        return [*izquierda, *derecha]
    tipo = tipos[operandos[0]]
    if _enum_tiene_datos(tipo, nombres_funcion.enumeraciones):
        if operador not in {"==", "!="}:
            _error("Las enumeraciones solo admiten == y !=.", contexto)
        instrucciones = _comparar_valores(
            tipo, izquierda, derecha, nombres_funcion
        )
        return [*instrucciones, "i32.eqz"] if operador == "!=" else instrucciones
    instrucciones = [*izquierda, *derecha]
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


def _nuevo_temporal_comparacion(nombres_funcion, tipo):
    temporal = f"comparacion_{nombres_funcion.siguiente_match}"
    nombres_funcion.siguiente_match += 1
    nombres_funcion.temporales_match.append((
        temporal,
        _tipo_wasm(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones),
    ))
    return temporal


def _cargar_valor_memoria(temporal, tipo, desplazamiento=0):
    instrucciones = [f"local.get ${temporal}"]
    if desplazamiento:
        instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
    instrucciones.append(_instruccion_carga_arreglo(tipo))
    return instrucciones


def _combinar_igualdades(igualdades):
    if not igualdades:
        return ["i32.const 1"]
    instrucciones = list(igualdades[0])
    for igualdad in igualdades[1:]:
        instrucciones.extend([*igualdad, "i32.and"])
    return instrucciones


def _comparar_valores(tipo, izquierda, derecha, nombres_funcion):
    if tipo == "String":
        return [*izquierda, *derecha, "call $string_eq"]
    if tipo == "f64":
        return [*izquierda, *derecha, "f64.eq"]
    if tipo in {"i32", "bool", "char"}:
        return [*izquierda, *derecha, "i32.eq"]
    enumeracion = _info_enum(tipo, nombres_funcion.enumeraciones)
    if enumeracion is not None:
        if not _enum_tiene_datos(tipo, nombres_funcion.enumeraciones):
            return [*izquierda, *derecha, "i32.eq"]
        temporal_izquierdo = _nuevo_temporal_comparacion(nombres_funcion, tipo)
        temporal_derecho = _nuevo_temporal_comparacion(nombres_funcion, tipo)
        distribucion = _distribucion_enum(
            tipo, nombres_funcion.enumeraciones, nombres_funcion.estructuras
        )
        variantes, _, _ = distribucion
        ramas = ["i32.const 0"]
        for nombre, (etiqueta, campos) in reversed(list(variantes.items())):
            igualdades = [
                _comparar_valores(
                    tipo_campo,
                    _cargar_valor_memoria(temporal_izquierdo, tipo_campo, desplazamiento),
                    _cargar_valor_memoria(temporal_derecho, tipo_campo, desplazamiento),
                    nombres_funcion,
                )
                for tipo_campo, desplazamiento in campos
            ]
            ramas = [
                f"local.get ${temporal_izquierdo}", "i32.load",
                f"i32.const {etiqueta}", "i32.eq",
                _wat_condicional_resultado(
                    _combinar_igualdades(igualdades), ramas, "i32"
                ),
            ]
        return [
            *izquierda, f"local.set ${temporal_izquierdo}",
            *derecha, f"local.set ${temporal_derecho}",
            f"local.get ${temporal_izquierdo}", "i32.load",
            f"local.get ${temporal_derecho}", "i32.load", "i32.eq",
            _wat_condicional_resultado(ramas, ["i32.const 0"], "i32"),
        ]
    temporal_izquierdo = _nuevo_temporal_comparacion(nombres_funcion, tipo)
    temporal_derecho = _nuevo_temporal_comparacion(nombres_funcion, tipo)
    matriz = _info_matriz(tipo)
    if matriz is not None and matriz[0] in {"i32", "f64", "bool", "char", "String"}:
        elemento, filas, columnas = matriz
        paso = _tamano_elemento_arreglo(elemento)
        igualdades = [
            _comparar_valores(
                elemento,
                _cargar_valor_memoria(temporal_izquierdo, elemento, indice * paso),
                _cargar_valor_memoria(temporal_derecho, elemento, indice * paso),
                nombres_funcion,
            )
            for indice in range(filas * columnas)
        ]
    else:
        arreglo = _partes_arreglo_recursivo(tipo)
        if arreglo is not None:
            elemento, cantidad = arreglo
            layout = _layout_recursivo(
                elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones
            )
            paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _distribucion_estructura(elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None or _info_enum(elemento, nombres_funcion.enumeraciones) is not None else layout["tamano"]
            igualdades = [
                _comparar_valores(
                    elemento,
                    _cargar_valor_memoria(temporal_izquierdo, elemento, indice * paso),
                    _cargar_valor_memoria(temporal_derecho, elemento, indice * paso),
                    nombres_funcion,
                )
                for indice in range(cantidad)
            ]
        else:
            distribucion = _distribucion_tupla(
                tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
            )
            if distribucion is None:
                distribucion = _distribucion_estructura(
                    tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
                )
            if distribucion is None:
                return [*izquierda, *derecha, "i32.eq"]
            igualdades = [
                _comparar_valores(
                    tipo_campo,
                    _cargar_valor_memoria(temporal_izquierdo, tipo_campo, desplazamiento),
                    _cargar_valor_memoria(temporal_derecho, tipo_campo, desplazamiento),
                    nombres_funcion,
                )
                for tipo_campo, desplazamiento in (
                    distribucion[0] if isinstance(distribucion[0], list) else distribucion[0].values()
                )
            ]
    return [
        *izquierda, f"local.set ${temporal_izquierdo}",
        *derecha, f"local.set ${temporal_derecho}",
        *_combinar_igualdades(igualdades),
    ]


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
        layout = _layout_copia_compuesta(
            tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
        )
        origen = _compilar_unaria(
            referencia.unary(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if layout is not None and clasificar_tipo(
            tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
        ) == "Copy":
            instrucciones = _copiar_compuesto(
                tipo,
                [*origen, "i32.load"] if _info_enum(
                    tipo, nombres_funcion.enumeraciones
                ) is not None else origen,
                nombres_funcion,
            )
        elif _escalar_prestable(tipo) or tipo == "String" or _info_enum(
            tipo, nombres_funcion.enumeraciones
        ) is not None:
            instrucciones = [*origen, _carga_escalar_memoria(tipo)]
        else:
            _error("Solo se admite desreferenciar tipos escalares.", referencia)
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
        if not _compuesto_prestable(
            referencia[1], nombres_funcion.estructuras, nombres_funcion.enumeraciones
        ) and _info_enum(referencia[1], nombres_funcion.enumeraciones) is None:
            _error("Solo se admiten accesos mediante referencias a compuestos locales compatibles.", contexto)
        tipo_base = referencia[1]
    estructura = _distribucion_estructura(tipo_base, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    if estructura is not None:
        accesos = list(accesos_lectura(contexto))
        if len(accesos) == 2 and accesos[0][0] == "nombre" and accesos[1][0] == "indice":
            nombre = accesos[0][1].IDENT().getText()
            campo, desplazamiento = estructura[0][nombre]
            partes = _partes_arreglo_recursivo(campo)
            if partes is not None:
                tipo_elemento, cantidad = partes
                if tipo_elemento in {"i32", "f64", "bool", "char", "String"}:
                    instrucciones.extend([f"i32.const {desplazamiento}", "i32.add", "i32.load"])
                    instrucciones.extend(_compilar_expresion(accesos[1][1], referencias, locales, funciones, nombres_funcion, tipos))
                    instrucciones.extend([f"i32.const {cantidad}", f"i32.const {_tamano_elemento_arreglo(tipo_elemento)}", "call $array_addr", _instruccion_carga_arreglo(tipo_elemento)])
                    return instrucciones
        return _resolver_accesos(instrucciones, tipo_base, accesos, referencias, locales, funciones, nombres_funcion, tipos)[0]
    tupla = _distribucion_tupla(tipo_base, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    if tupla is not None:
        accesos = list(accesos_lectura(contexto))
        return _resolver_accesos(instrucciones, tipo_base, accesos, referencias, locales, funciones, nombres_funcion, tipos)[0]
    accesos = list(accesos_lectura(contexto))
    if (_info_matriz(tipo_base) is None and _info_arreglo(tipo_base) is not None
            and len(accesos) > 1):
        return _resolver_accesos(
            instrucciones, tipo_base, accesos, referencias, locales, funciones,
            nombres_funcion, tipos,
        )[0]
    partes_anidadas = _partes_arreglo_recursivo(tipo_base)
    if (partes_anidadas is not None
        and _partes_arreglo_recursivo(partes_anidadas[0]) is not None
        and _partes_arreglo_recursivo(_partes_arreglo_recursivo(partes_anidadas[0])[0]) is not None
        and len(contexto.expression()) > 1):
        tipo_actual = tipo_base
        for indice, expresion_indice in enumerate(contexto.expression()):
            partes = _partes_arreglo_recursivo(tipo_actual)
            if partes is None:
                _error("El acceso indexado excede el tipo del arreglo.", contexto)
            elemento, cantidad = partes
            layout = _layout_recursivo(elemento, nombres_funcion.estructuras)
            if layout is None:
                _error("El elemento del arreglo no tiene layout disponible.", contexto)
            paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(elemento, nombres_funcion.estructuras) is not None or _distribucion_estructura(elemento, nombres_funcion.estructuras) is not None else layout["tamano"]
            instrucciones.extend(_compilar_expresion(expresion_indice, referencias, locales, funciones, nombres_funcion, tipos))
            instrucciones.extend([f"i32.const {cantidad}", f"i32.const {paso}", "call $array_addr"])
            if indice < len(contexto.expression()) - 1:
                instrucciones.append("i32.load")
            else:
                instrucciones.append(_instruccion_carga_arreglo(elemento))
            tipo_actual = elemento
        return instrucciones
    matriz = _info_matriz(tipo_base)
    if matriz is not None and _partes_arreglo_recursivo(matriz[0]) is None:
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
        instrucciones.extend([f"i32.const {columnas}", f"i32.const {bytes_elemento}", "call $array_addr"])
        if contexto.fieldAccess():
            estructura = _distribucion_estructura(tipo_elemento, nombres_funcion.estructuras)
            if estructura is None:
                _error("El elemento de la matriz no tiene el campo solicitado.", contexto)
            nombre = contexto.fieldAccess(0).IDENT().getText()
            tipo_campo, desplazamiento = estructura[0][nombre]
            instrucciones.append("i32.load")
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
            instrucciones.append(_instruccion_carga_arreglo(tipo_campo))
        elif contexto.tupleAccess():
            tupla = _distribucion_tupla(tipo_elemento, nombres_funcion.estructuras)
            if tupla is None:
                _error("El elemento de la matriz no es una tupla disponible.", contexto)
            posicion = int(contexto.tupleAccess(0).getText()[1:])
            tipo_campo, desplazamiento = tupla[0][posicion]
            instrucciones.append("i32.load")
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
            instrucciones.append(_instruccion_carga_arreglo(tipo_campo))
        else:
            instrucciones.append(_instruccion_carga_arreglo(tipo_elemento))
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
        ]
    )
    accesos = list(accesos_lectura(contexto))
    if len(accesos) == 2 and accesos[1][0] == "nombre":
        estructura = _distribucion_estructura(tipo_elemento, nombres_funcion.estructuras)
        if estructura is None:
            _error("El elemento del arreglo no tiene el campo solicitado.", contexto)
        nombre = accesos[1][1].IDENT().getText()
        tipo_campo, desplazamiento = estructura[0][nombre]
        instrucciones.append("i32.load")
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        instrucciones.append(_instruccion_carga_arreglo(tipo_campo))
        return instrucciones
    if len(accesos) == 2 and accesos[1][0] == "campo":
        tupla = _distribucion_tupla(tipo_elemento, nombres_funcion.estructuras)
        if tupla is None:
            _error("El elemento del arreglo no es una tupla disponible.", contexto)
        posicion = int(accesos[1][1].getText()[1:])
        tipo_campo, desplazamiento = tupla[0][posicion]
        instrucciones.append("i32.load")
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        instrucciones.append(_instruccion_carga_arreglo(tipo_campo))
        return instrucciones
    instrucciones.append(_instruccion_carga_arreglo(tipo_elemento))
    return instrucciones


def _literal_patron(contexto, tipo, enumeraciones, nombres_funcion=None):
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
    if tipo == "f64" and literal.FLOAT() is not None:
        return f"f64.const {literal.getText()}"
    if tipo == "String" and literal.STRING_LITERAL() is not None:
        descriptor = nombres_funcion.memoria.agregar(_valor_string(literal.STRING_LITERAL().getText(), literal), literal)
        return f"i32.const {descriptor}"
    _error("El patrón de match todavía no está implementado.", contexto)


def _enlazar_receptor_patron(identificador, valor, tipo, nombres_funcion, contexto):
    """Guarda un receptor prestable en memoria antes de ejecutar su brazo match."""
    if identificador not in nombres_funcion.escalares_en_memoria:
        return [*valor, f"local.set $local_{identificador}"]
    tamano_alineacion = _tamano_y_alineacion_prestamo(
        tipo, nombres_funcion.enumeraciones
    )
    if tamano_alineacion is None:
        _error("El receptor del patrón no tiene un tipo prestable en WASM.", contexto)
    tamano, alineacion = tamano_alineacion
    # El receptor sólo existe en este brazo: se reserva al entrar al brazo elegido.
    return [
        f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
        f"local.set $local_{identificador}", f"local.get $local_{identificador}",
        *valor, _almacenamiento_escalar_memoria(tipo),
    ]


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
            valor = f"f64.const {literal.getText()}"
        elif tipo == "String" and literal.STRING_LITERAL() is not None:
            descriptor = nombres_funcion.memoria.agregar(
                _valor_string(literal.STRING_LITERAL().getText(), literal), literal
            )
            valor = f"i32.const {descriptor}"
        else:
            _error("El patrón de dato de enumeración todavía no está implementado.", patron)
        return [
            f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
            valor, "call $string_eq" if tipo == "String" else f"{tipo}.eq" if tipo == "f64" else "i32.eq",
        ], []
    if patron.DOUBLE_COLON() is not None:
        if _enum_tiene_datos(tipo, nombres_funcion.enumeraciones):
            temporal_hijo = _nuevo_temporal(nombres_funcion)
            condicion, enlaces = _compilar_patron_enum(
                patron, temporal_hijo, tipo, referencias, locales, nombres_funcion
            )
            return [
                f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
                f"local.set ${temporal_hijo}", *condicion,
            ], enlaces
        valor = _literal_patron(
            patron, tipo, nombres_funcion.enumeraciones, nombres_funcion
        )
        return [
            f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
            valor, "i32.eq",
        ], []
    if patron.IDENT():
        identificador = nombres_funcion.declaraciones.get(patron)
        if identificador is None or identificador not in locales:
            _error("El receptor del patrón no está disponible para generar WASM.", patron)
        return [], _enlazar_receptor_patron(
            identificador,
            [f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento)],
            tipo, nombres_funcion, patron,
        )
    if patron.LPAREN() is not None:
        temporal_hijo = _nuevo_temporal(nombres_funcion)
        condicion, enlaces = _compilar_patron_tupla(
            patron, temporal_hijo, tipo, referencias, locales, nombres_funcion
        )
        return [
            f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
            f"local.set ${temporal_hijo}", *condicion,
        ], enlaces
    _error("El patrón de dato de enumeración todavía no está implementado.", patron)


def _compilar_patron_enum(patron, temporal, tipo_valor, referencias, locales, nombres_funcion):
    """Comprueba etiqueta y datos de una variante antes de entrar a su brazo match."""
    distribucion = _distribucion_enum(
        tipo_valor, nombres_funcion.enumeraciones, nombres_funcion.estructuras
    )
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


def _compilar_patron_tupla(patron, temporal, tipo_valor, referencias, locales,
                           nombres_funcion):
    distribucion = _distribucion_tupla(tipo_valor, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    patrones = patron.pattern()
    if distribucion is None or len(patrones) != len(distribucion[0]):
        _error("El patrón de tupla no está disponible para generar WASM.", patron)
    condiciones = []
    enlaces = []
    for hijo, (tipo, desplazamiento) in zip(patrones, distribucion[0]):
        if hijo.UNDERSCORE() is not None:
            continue
        if hijo.patternLiteral() is not None:
            valor = _literal_patron(hijo, tipo, nombres_funcion.enumeraciones, nombres_funcion)
            condicion = [
                f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
                valor, "call $string_eq" if tipo == "String" else "f64.eq" if tipo == "f64" else "i32.eq",
            ]
            if condiciones:
                condiciones.extend(condicion)
                condiciones.append("i32.and")
            else:
                condiciones.extend(condicion)
            continue
        if hijo.IDENT():
            identificador = nombres_funcion.declaraciones.get(hijo)
            if identificador is None:
                _error("El receptor del patrón de tupla no está disponible para generar WASM.", hijo)
            enlaces.extend(_enlazar_receptor_patron(
                identificador,
                [f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento)],
                tipo, nombres_funcion, hijo,
            ))
            continue
        if hijo.LPAREN() is not None:
            temporal_hijo = _nuevo_temporal(nombres_funcion)
            condicion, enlace = _compilar_patron_tupla(
                hijo, temporal_hijo, tipo, referencias, locales, nombres_funcion
            )
            condiciones.extend([
                f"local.get ${temporal}", _instruccion_carga_arreglo(tipo, desplazamiento),
                f"local.set ${temporal_hijo}", *condicion,
            ])
            if len(condiciones) > len(condicion) + 3:
                condiciones.append("i32.and")
            enlaces.extend(enlace)
            continue
        _error("El patrón de tupla todavía no está implementado.", hijo)
    return condiciones or ["i32.const 1"], enlaces


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
        condicion, enlaces = _compilar_patron_tupla(
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
    if patron.DOUBLE_COLON() is not None:
        literal = _literal_patron(patron, tipo_valor, nombres_funcion.enumeraciones, nombres_funcion)
    elif patron.IDENT():
        identificador = nombres_funcion.declaraciones.get(patron)
        if identificador is None or identificador not in locales:
            _error("El receptor del patrón no está disponible para generar WASM.", patron)
        return [
            *_enlazar_receptor_patron(
                identificador, [f"local.get ${temporal}"], tipo_valor,
                nombres_funcion, patron,
            ),
            *expresion,
        ]
    else:
        literal = _literal_patron(patron, tipo_valor, nombres_funcion.enumeraciones, nombres_funcion)
    siguiente = _compilar_brazos_match(
        brazos, indice + 1, temporal, tipo_valor, tipo_resultado,
        referencias, locales, funciones, nombres_funcion, tipos,
    )
    return [
        f"local.get ${temporal}",
        literal,
        "call $string_eq" if tipo_valor == "String" else "f64.eq" if tipo_valor == "f64" else "i32.eq",
        _wat_condicional_resultado(expresion, siguiente, _tipo_wasm(tipo_resultado, enumeraciones=nombres_funcion.enumeraciones)),
    ]


def _compilar_match(contexto, referencias, locales, funciones, nombres_funcion, tipos):
    """Evalúa el valor una sola vez y lo conserva en un local temporal del match."""
    tipo_valor = tipos.get(contexto.expression())
    tipo_resultado = tipos.get(contexto)
    if (tipo_valor not in {"i32", "bool", "char", "f64", "String"}
            and _distribucion_tupla(tipo_valor, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
            and _info_enum(tipo_valor, nombres_funcion.enumeraciones) is None):
        _error("Solo se admiten match de i32, bool, char, tuplas y enumeraciones.", contexto)
    if tipo_resultado not in {"i32", "f64", "bool", "char", "String"}:
        _error("El resultado de match todavía no está implementado.", contexto)
    temporal = f"valor_match_{nombres_funcion.siguiente_match}"
    nombres_funcion.siguiente_match += 1
    nombres_funcion.temporales_match.append((temporal, _tipo_wasm(tipo_valor, nombres_funcion.estructuras, nombres_funcion.enumeraciones)))
    literal_tupla = _obtener_literal_tupla(contexto.expression())
    if literal_tupla is not None and _distribucion_tupla(tipo_valor, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None:
        campos, tamano, alineacion = _distribucion_tupla(tipo_valor, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
        expresiones = literal_tupla.expression()
        if len(expresiones) != len(campos):
            _error("El literal no coincide con los campos de la tupla.", literal_tupla)
        valor = [
            f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc",
            f"local.set ${temporal}",
        ]
        for (tipo, desplazamiento), expresion in zip(campos, expresiones):
            valor.append(f"local.get ${temporal}")
            valor.extend(_compilar_expresion(
                expresion, referencias, locales, funciones, nombres_funcion, tipos
            ))
            valor.append(_instruccion_almacenamiento_arreglo(tipo, desplazamiento))
    else:
        valor = _compilar_expresion(
            contexto.expression(), referencias, locales, funciones, nombres_funcion, tipos
        )
        if "normal" not in salidas_control(contexto.expression()):
            return valor
        valor.append(f"local.set ${temporal}")
    brazos = contexto.matchArm()
    return [
        *valor,
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
    distribucion = _distribucion_enum(tipo, nombres_funcion.enumeraciones, nombres_funcion.estructuras)
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
        return _compilar_literal_compuesto(contexto, tipos[contexto], referencias, locales, funciones, nombres_funcion, tipos)
    if contexto.structLiteral() is not None:
        return _compilar_literal_compuesto(contexto, tipos[contexto], referencias, locales, funciones, nombres_funcion, tipos)
    if contexto.arrayLiteral() is not None:
        return _compilar_literal_arreglo_recursivo(contexto.arrayLiteral(), tipos[contexto], referencias, locales, funciones, nombres_funcion, tipos)
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
        tamano_alineacion = _tamano_y_alineacion_prestamo(
            tipo_local, nombres_funcion.enumeraciones
        )
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
    estructura = _distribucion_estructura(tipo_local, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
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
        return [
            *_compilar_literal_compuesto(
                expresion, tipo_local, referencias, locales, funciones, nombres_funcion, tipos
            ),
            f"local.set $local_{identificador}",
        ]
    tupla = _distribucion_tupla(simbolos[identificador]["tipo"], nombres_funcion.estructuras, nombres_funcion.enumeraciones)
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
        return [
            *_compilar_literal_compuesto(
                expresion, tipo_local, referencias, locales, funciones, nombres_funcion, tipos
            ),
            f"local.set $local_{identificador}",
        ]
    matriz = _info_matriz(simbolos[identificador]["tipo"])
    if matriz is not None and _partes_arreglo_recursivo(matriz[0]) is None:
        tipo_elemento, filas, columnas = matriz
        if expresion is None:
            _error("Una matriz local requiere un literal para inicializarse.", declaracion)
        literal = _obtener_literal_arreglo(expresion)
        if literal is None:
            if _layout_copia_compuesta(
                simbolos[identificador]["tipo"], nombres_funcion.estructuras,
                nombres_funcion.enumeraciones,
            ) is None:
                return [
                    *_compilar_expresion(
                        expresion, referencias, locales, funciones, nombres_funcion, tipos
                    ),
                    f"local.set $local_{identificador}",
                ]
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
    arreglo = _info_arreglo(tipo_destino)
    matriz = _info_matriz(tipo_destino)
    if (_distribucion_tupla(tipo_destino, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
        or _distribucion_estructura(tipo_destino, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
        or _info_enum(tipo_destino, nombres_funcion.enumeraciones) is not None
        or (matriz is not None and _partes_arreglo_recursivo(matriz[0]) is None
            and (_distribucion_tupla(matriz[0], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
                 or _distribucion_estructura(matriz[0], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None))
        or (arreglo is not None and (_distribucion_tupla(arreglo[0], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
                                    or _distribucion_estructura(arreglo[0], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
                                    or _layout_copia_compuesta(arreglo[0], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None))):
        return _copiar_compuesto(tipo_destino, _compilar_expresion(expresion, referencias, locales, funciones, nombres_funcion, tipos), nombres_funcion)
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


def _copiar_compuesto(tipo, origen, nombres_funcion, filas_punteros=False):
    layout = _layout_copia_compuesta(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    if layout is None:
        return origen
    tamano, alineacion = layout
    matriz_actual = _info_matriz(tipo)
    if filas_punteros and matriz_actual is not None:
        tamano, alineacion = matriz_actual[1] * 4, 4
    origen_temporal = _nuevo_temporal(nombres_funcion)
    destino_temporal = _nuevo_temporal(nombres_funcion)
    instrucciones = [*origen, f"local.set ${origen_temporal}", f"i32.const {tamano}", f"i32.const {alineacion}", "call $array_alloc", f"local.set ${destino_temporal}", f"local.get ${destino_temporal}", f"local.get ${origen_temporal}", f"i32.const {tamano}", "memory.copy"]
    enumeracion = _distribucion_enum(
        tipo, nombres_funcion.enumeraciones, nombres_funcion.estructuras
    )
    if enumeracion is not None:
        variantes, _, _ = enumeracion
        for etiqueta, campos in variantes.values():
            campos_compuestos = [
                (tipo_campo, desplazamiento)
                for tipo_campo, desplazamiento in campos
                if _layout_copia_compuesta(
                    tipo_campo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
                ) is not None
            ]
            if not campos_compuestos:
                continue
            instrucciones.extend([
                f"local.get ${origen_temporal}", "i32.load",
                f"i32.const {etiqueta}", "i32.eq", "if",
            ])
            for tipo_campo, desplazamiento in campos_compuestos:
                instrucciones.append(f"local.get ${destino_temporal}")
                fuente = [f"local.get ${origen_temporal}"]
                if desplazamiento:
                    fuente.extend([f"i32.const {desplazamiento}", "i32.add"])
                fuente.append("i32.load")
                instrucciones.extend(_copiar_compuesto(
                    tipo_campo, fuente, nombres_funcion,
                    _info_matriz(tipo_campo) is not None,
                ))
                instrucciones.append(_instruccion_almacenamiento_arreglo(tipo_campo, desplazamiento))
            instrucciones.append("end")
        return [*instrucciones, f"local.get ${destino_temporal}"]
    matriz = _info_matriz(tipo)
    if (matriz is not None and not filas_punteros
            and _partes_arreglo_recursivo(matriz[0]) is None):
        elemento, filas, columnas = matriz
        for indice in range(filas * columnas):
            if _layout_copia_compuesta(
                elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones
            ) is None:
                continue
            instrucciones.extend([f"local.get ${destino_temporal}"])
            if indice:
                instrucciones.extend([f"i32.const {indice * 4}", "i32.add"])
            fuente = [f"local.get ${origen_temporal}"]
            if indice:
                fuente.extend([f"i32.const {indice * 4}", "i32.add"])
            fuente.append("i32.load")
            instrucciones.extend(_copiar_compuesto(
                elemento, fuente, nombres_funcion,
                _info_matriz(elemento) is not None,
            ))
            instrucciones.append("i32.store")
        return [*instrucciones, f"local.get ${destino_temporal}"]
    arreglo = _info_arreglo(tipo)
    if arreglo is not None:
        elemento, cantidad = arreglo
        for indice in range(cantidad):
            if _layout_copia_compuesta(elemento, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None:
                continue
            instrucciones.extend([f"local.get ${destino_temporal}"])
            if indice:
                instrucciones.extend([f"i32.const {indice * 4}", "i32.add"])
            fuente = [f"local.get ${origen_temporal}"]
            if indice:
                fuente.extend([f"i32.const {indice * 4}", "i32.add"])
            fuente.append("i32.load")
            instrucciones.extend(_copiar_compuesto(
                elemento, fuente, nombres_funcion,
                _info_matriz(elemento) is not None,
            ))
            instrucciones.append("i32.store")
        return [*instrucciones, f"local.get ${destino_temporal}"]
    tupla = _distribucion_tupla(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)
    campos = tupla[0] if tupla is not None else _distribucion_estructura(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones)[0].values()
    for tipo_campo, desplazamiento in campos:
        if _layout_copia_compuesta(tipo_campo, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None:
            continue
        instrucciones.extend([f"local.get ${destino_temporal}"])
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        fuente = [f"local.get ${origen_temporal}"]
        if desplazamiento:
            fuente.extend([f"i32.const {desplazamiento}", "i32.add"])
        fuente.append("i32.load")
        instrucciones.extend(_copiar_compuesto(
            tipo_campo, fuente, nombres_funcion,
            _info_matriz(tipo_campo) is not None,
        ))
        instrucciones.append("i32.store")
    return [*instrucciones, f"local.get ${destino_temporal}"]


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
        if referencia is None or (
            not _escalar_prestable(referencia[1])
            and referencia[1] != "String"
            and _info_enum(referencia[1], nombres_funcion.enumeraciones) is None
        ):
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
    tipo_base = separar_referencia(tipo_variable)
    tipo_base = tipo_variable if tipo_base is None else tipo_base[1]
    accesos = list(accesos_escritura(asignacion))
    usa_resolvedor = (
        _distribucion_estructura(tipo_base, nombres_funcion.estructuras) is not None
        or _distribucion_tupla(tipo_base, nombres_funcion.estructuras) is not None
        or (_info_matriz(tipo_base) is None and _info_arreglo(tipo_base) is not None and len(accesos) > 1)
    )
    if usa_resolvedor and accesos:
        direccion, tipo = _resolver_accesos(
            [f"local.get $local_{identificador}"], tipo_base, accesos,
            referencias, locales, funciones, nombres_funcion, tipos, False,
        )
        if operador == "=":
            return [*direccion, *expresion, _instruccion_almacenamiento_arreglo(tipo, 0)]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {
            "+=": f"{tipo}.add", "-=": f"{tipo}.sub", "*=": f"{tipo}.mul",
            "/=": "i32.div_s" if tipo == "i32" else "f64.div",
        }[operador]
        return [
            *direccion, "local.tee $direccion_asignacion",
            _instruccion_carga_arreglo(tipo), *expresion, instruccion,
            f"local.set $valor_asignacion_{tipo}", "local.get $direccion_asignacion",
            f"local.get $valor_asignacion_{tipo}",
            _instruccion_almacenamiento_arreglo(tipo, 0),
        ]
    if asignacion.indexAccess():
        direccion, tipo = _compilar_direccion_asignacion(
            asignacion, identificador, referencias, simbolos, locales, funciones,
            nombres_funcion, tipos,
        )
        if operador == "=":
            return [*direccion, *expresion, _instruccion_almacenamiento_arreglo(tipo, 0)]
        if tipo not in {"i32", "f64"}:
            _error("Las asignaciones compuestas solo admiten i32 y f64.", asignacion)
        instruccion = {"+=": f"{tipo}.add", "-=": f"{tipo}.sub", "*=": f"{tipo}.mul", "/=": "i32.div_s" if tipo == "i32" else "f64.div"}[operador]
        return [*direccion, "local.tee $direccion_asignacion", _instruccion_carga_arreglo(tipo), *expresion, instruccion, f"local.set $valor_asignacion_{tipo}", "local.get $direccion_asignacion", f"local.get $valor_asignacion_{tipo}", _instruccion_almacenamiento_arreglo(tipo, 0)]
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
        direccion, tipo = _compilar_direccion_tupla(asignacion, identificador, simbolos, nombres_funcion.estructuras)
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


def _compilar_direccion_tupla(asignacion, identificador, simbolos, estructuras):
    """Obtiene la dirección del campo local sin compartir almacenamiento entre tuplas."""
    accesos = list(accesos_escritura(asignacion))
    tipo_base = simbolos[identificador]["tipo"]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        tipo_base = referencia[1]
    tupla = _distribucion_tupla(tipo_base, estructuras)
    if tupla is None:
        _error("La asignación no corresponde a una tupla local admitida.", asignacion)
    instrucciones = [f"local.get $local_{identificador}"]
    return _compilar_accesos_compuestos(instrucciones, tipo_base, accesos, estructuras, False)


def _compilar_direccion_estructura(asignacion, identificador, simbolos, estructuras):
    """Calcula la dirección de un campo, incluso cuando la base es una &Estructura."""
    accesos = list(accesos_escritura(asignacion))
    tipo_base = simbolos[identificador]["tipo"]
    referencia = separar_referencia(tipo_base)
    if referencia is not None:
        tipo_base = referencia[1]
    estructura = _distribucion_estructura(tipo_base, estructuras)
    if estructura is None:
        _error("La asignación no corresponde a una estructura local admitida.", asignacion)
    instrucciones = [f"local.get $local_{identificador}"]
    return _compilar_accesos_compuestos(instrucciones, tipo_base, accesos, estructuras, False)


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
    partes_anidadas = _partes_arreglo_recursivo(tipo_base)
    if (partes_anidadas is not None
        and _partes_arreglo_recursivo(partes_anidadas[0]) is not None
        and _partes_arreglo_recursivo(_partes_arreglo_recursivo(partes_anidadas[0])[0]) is not None
        and len(accesos) > 1):
        tipo_actual = tipo_base
        for indice, acceso in enumerate(accesos):
            partes = _partes_arreglo_recursivo(tipo_actual)
            if partes is None:
                _error("El acceso indexado excede el tipo del arreglo.", asignacion)
            elemento, cantidad = partes
            layout = _layout_recursivo(elemento, nombres_funcion.estructuras)
            if layout is None:
                _error("El elemento del arreglo no tiene layout disponible.", asignacion)
            paso = 4 if layout.get("elemento") is not None or _distribucion_tupla(elemento, nombres_funcion.estructuras) is not None or _distribucion_estructura(elemento, nombres_funcion.estructuras) is not None else layout["tamano"]
            instrucciones.extend(_compilar_expresion(acceso.expression(), referencias, locales, funciones, nombres_funcion, tipos))
            instrucciones.extend([f"i32.const {cantidad}", f"i32.const {paso}", "call $array_addr"])
            if indice < len(accesos) - 1:
                instrucciones.append("i32.load")
            tipo_actual = elemento
        return instrucciones, tipo_actual
    estructura = _distribucion_estructura(tipo_base, nombres_funcion.estructuras)
    if estructura is not None and asignacion.fieldAccess():
        nombre = asignacion.fieldAccess(0).IDENT().getText()
        tipo_campo, desplazamiento = estructura[0][nombre]
        partes = _partes_arreglo_recursivo(tipo_campo)
        if partes is None or len(accesos) != 1:
            _error("El acceso indexado al campo no está disponible para generar WASM.", asignacion)
        tipo_elemento, cantidad = partes
        instrucciones.extend([f"i32.const {desplazamiento}", "i32.add", "i32.load"])
        instrucciones.extend(_compilar_expresion(accesos[0].expression(), referencias, locales, funciones, nombres_funcion, tipos))
        instrucciones.extend([f"i32.const {cantidad}", f"i32.const {_tamano_elemento_arreglo(tipo_elemento)}", "call $array_addr"])
        return instrucciones, tipo_elemento
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
        if asignacion.fieldAccess():
            estructura = _distribucion_estructura(tipo_elemento, nombres_funcion.estructuras)
            if estructura is None:
                _error("El elemento de la matriz no tiene el campo solicitado.", asignacion)
            nombre = asignacion.fieldAccess(0).IDENT().getText()
            tipo_campo, desplazamiento = estructura[0][nombre]
            instrucciones.append("i32.load")
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
            return instrucciones, tipo_campo
        if asignacion.tupleAccess():
            tupla = _distribucion_tupla(tipo_elemento, nombres_funcion.estructuras)
            if tupla is None:
                _error("El elemento de la matriz no es una tupla disponible.", asignacion)
            posicion = int(asignacion.tupleAccess(0).getText()[1:])
            tipo_campo, desplazamiento = tupla[0][posicion]
            instrucciones.append("i32.load")
            if desplazamiento:
                instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
            return instrucciones, tipo_campo
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
    if asignacion.fieldAccess():
        estructura = _distribucion_estructura(tipo_elemento, nombres_funcion.estructuras)
        if estructura is None:
            _error("El elemento del arreglo no tiene el campo solicitado.", asignacion)
        nombre = asignacion.fieldAccess(0).IDENT().getText()
        tipo_campo, desplazamiento = estructura[0][nombre]
        instrucciones.append("i32.load")
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        return instrucciones, tipo_campo
    if asignacion.tupleAccess():
        tupla = _distribucion_tupla(tipo_elemento, nombres_funcion.estructuras)
        if tupla is None:
            _error("El elemento del arreglo no es una tupla disponible.", asignacion)
        posicion = int(asignacion.tupleAccess(0).getText()[1:])
        tipo_campo, desplazamiento = tupla[0][posicion]
        instrucciones.append("i32.load")
        if desplazamiento:
            instrucciones.extend([f"i32.const {desplazamiento}", "i32.add"])
        return instrucciones, tipo_campo
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
        and not _referencia_admitida(
            tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
        )
        and _info_arreglo(tipo) is None
        and _info_matriz(tipo) is None
        and _distribucion_tupla(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _distribucion_estructura(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _info_enum(tipo, nombres_funcion.enumeraciones) is None
        for tipo in firma["parametros"]
    ):
        _error(f"La función '{nombre}' usa parámetros no soportados.", llamada)
    if (
        firma["retorno"] not in {"i32", "bool", "f64", "char", "String", "unit"}
        and _info_arreglo(firma["retorno"]) is None
        and _info_matriz(firma["retorno"]) is None
        and _distribucion_tupla(firma["retorno"], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _distribucion_estructura(firma["retorno"], nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _info_enum(firma["retorno"], nombres_funcion.enumeraciones) is None
    ):
        _error(f"La función '{nombre}' tiene un retorno no soportado.", llamada)

    argumentos = []
    lista = llamada.argumentList()
    if lista is not None:
        argumentos = lista.expression()
    instrucciones = []
    for argumento, tipo_parametro in zip(argumentos, firma["parametros"]):
        # Cada argumento se deja en la pila antes de call, como exige la firma WASM.
        if (_info_arreglo(tipo_parametro) is not None
            or _info_matriz(tipo_parametro) is not None
            or _info_enum(tipo_parametro, nombres_funcion.enumeraciones) is not None
            or _distribucion_tupla(tipo_parametro, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None
            or _distribucion_estructura(tipo_parametro, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is not None):
            instrucciones.extend(
                _compilar_valor_para_local(
                    argumento, tipo_parametro, referencias, locales, funciones,
                    nombres_funcion, tipos,
                )
            )
        else:
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
    if (
        tipo_retorno not in {"i32", "bool", "f64", "char", "String", "unit"}
        and _info_arreglo(tipo_retorno) is None
        and _info_matriz(tipo_retorno) is None
        and _distribucion_tupla(tipo_retorno, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _distribucion_estructura(tipo_retorno, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None
        and _info_enum(tipo_retorno, nombres_funcion.enumeraciones) is None
    ):
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
            if not _referencia_admitida(
                tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
            ):
                _error("Solo se admiten parámetros referencia con layouts locales compatibles.", funcion)
            continue
    for identificador in variables:
        tipo = analisis["simbolos"][identificador]["tipo"]
        referencia = separar_referencia(tipo)
        if referencia is not None and not _referencia_admitida(
            tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
        ):
            _error("Solo se admiten referencias con layouts locales compatibles.", funcion)
        if tipo not in {"i32", "bool", "f64", "char", "String"} and referencia is None and _info_arreglo(tipo) is None and _info_matriz(tipo) is None and _distribucion_tupla(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None and _distribucion_estructura(tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones) is None and _info_enum(tipo, nombres_funcion.enumeraciones) is None:
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
        declaracion = declaraciones_por_id.get(identificador)
        if type(declaracion).__name__ == "PatternContext":
            if tipo not in {"i32", "f64", "bool", "char"}:
                _error("Solo se admiten préstamos de receptores escalares.", funcion)
            escalares_en_memoria.add(identificador)
            continue
        if identificador in parametros:
            _error("Solo se admiten préstamos de variables locales con layouts compatibles.", funcion)
        if (
            _escalar_prestable(tipo)
            or tipo == "String"
            or _info_enum(tipo, nombres_funcion.enumeraciones) is not None
        ):
            escalares_en_memoria.add(identificador)
        elif not _compuesto_prestable(
            tipo, nombres_funcion.estructuras, nombres_funcion.enumeraciones
        ):
            _error("Solo se admiten préstamos de variables locales con layouts compatibles.", funcion)
    parametros_wat = " ".join(
        f"(param $local_{identificador} "
        f"{_tipo_wasm(analisis['simbolos'][identificador]['tipo'], nombres_funcion.estructuras, nombres_funcion.enumeraciones)})"
        for identificador in sorted(parametros)
    )
    # Los parámetros referencia también son i32 porque transportan una dirección.
    resultado_wat = "" if tipo_retorno == "unit" else f" (result {_tipo_wasm(tipo_retorno, nombres_funcion.estructuras, nombres_funcion.enumeraciones)})"
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
        f"    (local ${temporal} {tipo})" for temporal, tipo in nombres_funcion.temporales_match
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
    return None


def _validar_enumeraciones(arbol, enumeraciones, estructuras):
    for declaracion in arbol.enumDecl():
        tipo = declaracion.IDENT().getText()
        enumeracion = enumeraciones[tipo]
        if (enumeracion.get("datos_variantes")
                and _distribucion_enum(tipo, enumeraciones, estructuras) is None):
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
        _validar_enumeraciones(arbol, analisis["enumeraciones"], analisis["estructuras"])
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
        metadatos_main = _metadatos_main(
            analisis, analisis["estructuras"], analisis["enumeraciones"]
        )
        descriptor_metadatos = None
        if metadatos_main is not None:
            descriptor_metadatos = estado.memoria.agregar(
                json.dumps(metadatos_main, ensure_ascii=False, separators=(",", ":")), arbol
            )
        # El módulo reúne memoria, helpers internos, funciones del programa y datos UTF-8.
        datos = estado.memoria.wat()
        imports = _imports_incorporados(estado.incorporadas_usadas)
        wat = (
            "(module\n"
            + (imports + "\n" if imports else "")
            + f"  (memory (export \"memory\") {estado.memoria.paginas_necesarias()})\n"
            + (
                f"  (global $rustiq_main_metadata (export \"__rustiq-main-metadata\") i32 (i32.const {descriptor_metadatos}))\n"
                if descriptor_metadatos is not None else ""
            )
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
