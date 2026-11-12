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

## Alcance actual

Se admiten funciones sin parámetros cuyo cuerpo contiene exactamente un
`return` de tipo `i32`. Las expresiones permiten literales `i32`, paréntesis,
`+`, `-` y `*`. Cada función admitida se exporta por su nombre.

Se rechazan controladamente variables, llamadas, constantes globales,
arreglos, operadores unarios, división, módulo, comparaciones, lógica y todos
los demás tipos o sentencias.
