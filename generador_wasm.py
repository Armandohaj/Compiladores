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


def _compilar_expresion(expresion):
    return _compilar_logical_or(expresion.logicalOr())


def _compilar_logical_or(contexto):
    if len(contexto.logicalAnd()) != 1:
        _error("El operador lógico '||' todavía no está implementado.", contexto)
    return _compilar_logical_and(contexto.logicalAnd(0))


def _compilar_logical_and(contexto):
    if len(contexto.comparison()) != 1:
        _error("El operador lógico '&&' todavía no está implementado.", contexto)
    return _compilar_comparacion(contexto.comparison(0))


def _compilar_comparacion(contexto):
    if len(contexto.additive()) != 1:
        _error("Las comparaciones todavía no están implementadas.", contexto)
    return _compilar_aditiva(contexto.additive(0))


def _compilar_aditiva(contexto):
    operandos = contexto.multiplicative()
    instrucciones = _compilar_multiplicativa(operandos[0])
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(_compilar_multiplicativa(operando))
        instrucciones.append("i32.add" if operador == "+" else "i32.sub")
    return instrucciones


def _compilar_multiplicativa(contexto):
    operandos = contexto.unary()
    instrucciones = _compilar_unaria(operandos[0])
    for indice, operando in enumerate(operandos[1:], start=1):
        operador = contexto.getChild(indice * 2 - 1).getText()
        instrucciones.extend(_compilar_unaria(operando))
        instrucciones.append({
            "*": "i32.mul",
            "/": "i32.div_s",
            "%": "i32.rem_s",
        }[operador])
    return instrucciones


def _compilar_unaria(contexto):
    if contexto.getChildCount() == 1:
        return _compilar_postfija(contexto.postfix())
    if contexto.getChild(0).getText() != "-":
        _error("El operador unario '!' todavía no está implementado.", contexto)

    postfija = contexto.postfix()
    primaria = postfija.primary() if postfija.getChildCount() == 1 else None
    literal = primaria.INT() if primaria is not None else None
    if literal is not None:
        valor = int(literal.getText())
        if valor == 2**31:
            return ["i32.const -2147483648"]
        if valor > 2**31 - 1:
            _error("El literal excede el rango de i32.", literal)

    return ["i32.const 0", *_compilar_postfija(postfija), "i32.sub"]


def _compilar_postfija(contexto):
    if contexto.getChildCount() != 1:
        _error("El acceso a arreglos todavía no está implementado.", contexto)
    return _compilar_primaria(contexto.primary())


def _compilar_primaria(contexto):
    literal = contexto.INT()
    if literal is not None:
        valor = int(literal.getText())
        if valor > 2**31 - 1:
            _error("El literal excede el rango de i32.", contexto)
        return [f"i32.const {valor}"]
    expresion = contexto.expression()
    if expresion is not None:
        return _compilar_expresion(expresion)
    _error(
        "Solo se admiten literales i32 y expresiones aritméticas entre paréntesis.",
        contexto,
    )


def _compilar_funcion(funcion, tipos_expresiones, indice):
    nombre = funcion.IDENT().getText()
    if funcion.parameterList() is not None:
        _error(f"La función '{nombre}' tiene parámetros no soportados.", funcion)
    if funcion.type_() is None or funcion.type_().getText() != "i32":
        _error(f"La función '{nombre}' debe retornar i32.", funcion)
    sentencias = funcion.block().statement()
    if len(sentencias) != 1 or sentencias[0].returnStmt() is None:
        _error(
            f"La función '{nombre}' debe contener únicamente un return con una expresión.",
            funcion.block(),
        )
    expresion = sentencias[0].returnStmt().expression()
    if expresion is None:
        _error(f"La función '{nombre}' debe retornar una expresión i32.", funcion)
    if tipos_expresiones.get(expresion) != "i32":
        _error(f"La expresión retornada por '{nombre}' no es i32.", expresion)
    instrucciones = _compilar_expresion(expresion)
    cuerpo = "\n    ".join(instrucciones)
    return (
        f"  (func $funcion_{indice} (result i32)\n"
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
            _compilar_funcion(funcion, analisis["tipos_expresiones"], indice)
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
