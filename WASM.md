# Backend WebAssembly mínimo

El generador usa `analizar_programa(codigo)` como única entrada de análisis y
recorre su árbol ANTLR4. No crea un segundo parser ni un AST alternativo.

## Instalación y pruebas

```powershell
python -m pip install -r requirements-wasm.txt
python -m pytest tests/test_generador_wasm.py
```

## Interfaz

```python
from generador_wasm import compilar_programa, ejecutar_modulo_wasm

resultado = compilar_programa('''fn main() -> i32 {
    return 10 + 20;
}''')

if resultado["valido"]:
    open("main.wasm", "wb").write(resultado["wasm"])
    assert ejecutar_modulo_wasm(resultado["wasm"]) == 30
else:
    print(resultado["errores"])
```

`compilar_programa` devuelve `valido`, `errores`, `wat` y `wasm`. Cuando el
análisis o la generación fallan, `wat` y `wasm` son `None`; los errores de
características no implementadas tienen fase `generacion` y posición fuente.
`ejecutar_modulo_wasm` conserva el uso sin argumentos y permite invocar una
exportación con argumentos, por ejemplo:

```python
ejecutar_modulo_wasm(resultado["wasm"], "doble", 21)
```

## Alcance actual

Se admiten funciones que retornan `i32` o `bool` (este último
representado como `i32` 0/1 en WebAssembly), con declaraciones `let` y `let
mut`, y asignaciones
simples o compuestas. Las variables locales usan los identificadores resueltos
por el analizador para mantener correctamente los ámbitos. Las expresiones
permiten literales `i32` y booleanos, variables, paréntesis, aritmética,
comparaciones, `!`, `&&` y `||`. Los operadores lógicos generan
cortocircuito real con bloques `if (result i32)`. Cada función admitida
se exporta por su nombre. La división y el residuo usan la semántica con signo
de WebAssembly; dividir por cero y `-2147483648 / -1` generan un trap al
ejecutarse.

También se admiten parámetros `i32` y `bool`, incluidos parámetros mutables,
llamadas anidadas y declaraciones posteriores. Las llamadas usadas como
sentencia descartan resultados con `drop`; las funciones `unit` se generan sin
resultado WebAssembly.

Las sentencias `if`, `if/else` y `else if` se traducen a bloques WAT `if`,
`then` y `else`. Sus ramas conservan las variables locales identificadas por
el análisis semántico, permiten retornos anticipados y ejecutan solamente la
rama cuya condición sea verdadera.

Se rechazan controladamente ciclos, constantes globales, arreglos y todos los
demás tipos o sentencias.
