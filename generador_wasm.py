"""Backend WebAssembly mínimo para el subconjunto aritmético de RustiQ."""

from __future__ import annotations

from dataclasses import dataclass

import wasmtime

from main import analizar_programa


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


def _compilar_expresion(expresion, referencias, locales):
    return _compilar_logical_or(expresion.logicalOr(), referencias, locales)


def _compilar_logical_or(contexto, referencias, locales):
    operandos = contexto.logicalAnd()
    instrucciones = _compilar_logical_and(operandos[0], referencias, locales)
    for operando in operandos[1:]:
        derecho = _compilar_logical_and(operando, referencias, locales)
        instrucciones.append(_wat_condicional(["i32.const 1"], derecho))
    return instrucciones


def _compilar_logical_and(contexto, referencias, locales):
    operandos = contexto.comparison()
    instrucciones = _compilar_comparacion(operandos[0], referencias, locales)
    for operando in operandos[1:]:
        derecho = _compilar_comparacion(operando, referencias, locales)
        instrucciones.append(_wat_condicional(derecho, ["i32.const 0"]))
    return instrucciones


def _compilar_comparacion(contexto, referencias, locales):
    operandos = contexto.additive()
    instrucciones = _compilar_aditiva(operandos[0], referencias, locales)
    if len(operandos) == 1:
        return instrucciones
    operador = contexto.relOp().getText()
    instrucciones.extend(_compilar_aditiva(operandos[1], referencias, locales))
    instrucciones.append({
        "==": "i32.eq",
        "!=": "i32.ne",
        "<": "i32.lt_s",
        "<=": "i32.le_s",
        ">": "i32.gt_s",
        ">=": "i32.ge_s",
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


def _compilar_aditiva(contexto, referencias, locales):
    operandos = contexto.multiplicative()
    instrucciones = _compilar_multiplicativa(operandos[0], referencias, locales)
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(_compilar_multiplicativa(operando, referencias, locales))
        instrucciones.append("i32.add" if operador == "+" else "i32.sub")
    return instrucciones


def _compilar_multiplicativa(contexto, referencias, locales):
    operandos = contexto.unary()
    instrucciones = _compilar_unaria(operandos[0], referencias, locales)
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(_compilar_unaria(operando, referencias, locales))
        instrucciones.append({
            "*": "i32.mul",
            "/": "i32.div_s",
            "%": "i32.rem_s",
        }[operador])
    return instrucciones


def _compilar_unaria(contexto, referencias, locales):
    if contexto.getChildCount() == 1:
        return _compilar_postfija(contexto.postfix(), referencias, locales)
    operador = contexto.getChild(0).getText()
    if operador == "!":
        return [*_compilar_postfija(contexto.postfix(), referencias, locales), "i32.eqz"]

    postfija = contexto.postfix()
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
        *_compilar_postfija(postfija, referencias, locales),
        "i32.sub",
    ]


def _compilar_postfija(contexto, referencias, locales):
    if contexto.getChildCount() != 1:
        _error("El acceso a arreglos todavía no está implementado.", contexto)
    return _compilar_primaria(contexto.primary(), referencias, locales)


def _compilar_primaria(contexto, referencias, locales):
    literal = contexto.INT()
    if literal is not None:
        valor = int(literal.getText())
        if valor > 2**31 - 1:
            _error("El literal excede el rango de i32.", contexto)
        return [f"i32.const {valor}"]
    if contexto.TRUE() is not None:
        return ["i32.const 1"]
    if contexto.FALSE() is not None:
        return ["i32.const 0"]
    expresion = contexto.expression()
    if expresion is not None:
        return _compilar_expresion(expresion, referencias, locales)
    if contexto.IDENT() is not None:
        identificador = referencias[contexto]
        if identificador not in locales:
            _error("La referencia no corresponde a una variable local i32.", contexto)
        return [f"local.get $local_{identificador}"]
    _error(
        "Solo se admiten literales i32 y expresiones aritméticas entre paréntesis.",
        contexto,
    )


def _compilar_declaracion(declaracion, declaraciones, simbolos, referencias, locales):
    identificador = declaraciones[declaracion]
    if identificador not in locales:
        _error("La declaración no corresponde a una variable local i32.", declaracion)
    expresion = declaracion.expression()
    if expresion is None:
        return []
    return [
        *_compilar_expresion(expresion, referencias, locales),
        f"local.set $local_{identificador}",
    ]


def _compilar_asignacion(asignacion, referencias, locales):
    identificador = referencias[asignacion]
    if identificador not in locales:
        _error("La asignación no corresponde a una variable local i32.", asignacion)
    operador = asignacion.assignmentOp().getText()
    expresion = _compilar_expresion(asignacion.expression(), referencias, locales)
    if operador == "=":
        return [*expresion, f"local.set $local_{identificador}"]
    instrucciones = [f"local.get $local_{identificador}", *expresion]
    instrucciones.append({
        "+=": "i32.add",
        "-=": "i32.sub",
        "*=": "i32.mul",
        "/=": "i32.div_s",
    }[operador])
    instrucciones.append(f"local.set $local_{identificador}")
    return instrucciones


def _compilar_sentencia(
    sentencia, declaraciones, referencias, simbolos, locales,
    tipos_expresiones, tipo_retorno,
):
    if sentencia.letDecl() is not None:
        return _compilar_declaracion(
            sentencia.letDecl(), declaraciones, simbolos, referencias, locales
        )
    if sentencia.assignment() is not None:
        return _compilar_asignacion(sentencia.assignment(), referencias, locales)
    if sentencia.returnStmt() is not None:
        expresion = sentencia.returnStmt().expression()
        if expresion is None:
            _error("La función debe retornar una expresión.", sentencia)
        if tipos_expresiones.get(expresion) != tipo_retorno:
            _error("El tipo de retorno no coincide con la función.", expresion)
        return [*_compilar_expresion(expresion, referencias, locales), "return"]
    if sentencia.block() is not None:
        instrucciones = []
        for interna in sentencia.block().statement():
            instrucciones.extend(
                _compilar_sentencia(
                    interna, declaraciones, referencias, simbolos, locales,
                    tipos_expresiones, tipo_retorno,
                )
            )
        return instrucciones
    _error("Esta sentencia todavía no está implementada.", sentencia)


def _compilar_funcion(funcion, analisis, indice):
    nombre = funcion.IDENT().getText()
    if funcion.parameterList() is not None:
        _error(f"La función '{nombre}' tiene parámetros no soportados.", funcion)
    if funcion.type_() is None or funcion.type_().getText() not in {"i32", "bool"}:
        _error(f"La función '{nombre}' debe retornar i32 o bool.", funcion)
    tipo_retorno = funcion.type_().getText()
    locales = {
        identificador
        for identificador, simbolo in analisis["simbolos"].items()
        if simbolo["funcion"] == nombre and not simbolo["es_parametro"]
        and not simbolo["es_constante"]
    }
    for identificador in locales:
        if analisis["simbolos"][identificador]["tipo"] not in {"i32", "bool"}:
            _error("Solo se admiten variables locales i32 o bool.", funcion)
    declaraciones_locales = "\n".join(
        f"    (local $local_{identificador} i32)" for identificador in sorted(locales)
    )
    instrucciones = []
    for sentencia in funcion.block().statement():
        instrucciones.extend(
            _compilar_sentencia(
                sentencia,
                analisis["declaraciones"],
                analisis["referencias"],
                analisis["simbolos"],
                locales,
                analisis["tipos_expresiones"],
                tipo_retorno,
            )
        )
    cuerpo = "\n    ".join(instrucciones)
    locales_wat = f"\n{declaraciones_locales}" if declaraciones_locales else ""
    return (
        f"  (func $funcion_{indice} (result i32){locales_wat}\n"
        f"    {cuerpo}\n"
        f"  )\n"
        f"  (export \"{nombre}\" (func $funcion_{indice}))"
    )


def compilar_programa(codigo):
    """Compila RustiQ a WebAssembly y devuelve ``valido`, `errores`, `wat`, `wasm`."""
    analisis = analizar_programa(codigo)
    if not analisis["valido"]:
        return {"valido": False, "errores": analisis["errores"], "wat": None, "wasm": None}
    arbol = analisis["arbol"]
    try:
        if arbol.constDecl():
            _error("Las constantes globales todavía no están implementadas.", arbol.constDecl(0))
        funciones = arbol.functionDecl()
        if not funciones:
            _error("El programa debe declarar al menos una función.", arbol)
        wat_funciones = [
            _compilar_funcion(funcion, analisis, indice)
            for indice, funcion in enumerate(funciones)
        ]
        wat = "(module\n" + "\n".join(wat_funciones) + "\n)"
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


def ejecutar_modulo_wasm(wasm, funcion="main"):
    """Instancia un binario generado y ejecuta una exportación sin parámetros."""
    motor = wasmtime.Engine()
    modulo = wasmtime.Module(motor, wasm)
    almacen = wasmtime.Store(motor)
    instancia = wasmtime.Instance(almacen, modulo, [])
    return instancia.exports(almacen)[funcion](almacen)
