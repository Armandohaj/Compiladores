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

Para recuperar el resultado de una función `String`, usa el decodificador
explícito que lee la memoria exportada:

```python
from generador_wasm import ejecutar_string_wasm

texto = ejecutar_string_wasm(resultado["wasm"])
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

Se admiten funciones que retornan `i32`, `f64`, `char` o `bool` (este último
representado como `i32` 0/1 en WebAssembly), con declaraciones `let` y `let
mut`, y asignaciones
simples o compuestas. Las variables locales usan los identificadores resueltos
por el analizador para mantener correctamente los ámbitos. Las expresiones
permiten literales `i32`, `f64` y booleanos, variables, paréntesis,
aritmética, comparaciones, `!`, `&&` y `||`. Los operadores lógicos generan
cortocircuito real con bloques `if (result i32)`. Cada función admitida
se exporta por su nombre. La división y el residuo usan la semántica con signo
de WebAssembly; dividir por cero y `-2147483648 / -1` generan un trap al
ejecutarse.

Las operaciones `f64` usan `f64.const`, aritmética y comparaciones nativas de
WebAssembly. Su división conserva la semántica IEEE 754: dividir por cero
puede producir infinito o `NaN`, sin el trap que ocurre con `i32.div_s`.

El tipo `char` se representa como un punto de código Unicode en un `i32` de
WebAssembly. Se admiten literales Unicode y los escapes `\n`, `\r`, `\t`,
`\0`, `\"`, `\'` y `\\`; `char` admite comparación por igualdad o diferencia,
pero no aritmética ni comparaciones de orden.

Cada `String` es un `i32` que apunta a un descriptor de ocho bytes en la
memoria WebAssembly exportada: cuatro bytes little-endian para la dirección
UTF-8 y cuatro para su longitud. Los literales se almacenan como segmentos de
datos; `==` y `!=` invocan una rutina WAT que compara longitud y bytes, no
direcciones. Se admiten cadenas vacías, Unicode y los mismos escapes que la
gramática reconoce.

El estado de esos segmentos pertenece a cada llamada a `compilar_programa`,
por lo que compilaciones simultáneas no comparten literales ni direcciones. La
memoria usa el mínimo de páginas de 64 KiB requerido por los datos estáticos
(como mínimo una página) y admite hasta 65 536 páginas, es decir 4 GiB. Si los
datos estáticos exceden ese límite, la compilación devuelve un error controlado
de generación.

Los arreglos locales unidimensionales `[i32; N]`, `[bool; N]`, `[char; N]`,
`[f64; N]` y `[String; N]` se representan mediante un puntero `i32` a celdas
consecutivas de memoria lineal. `i32`, `bool`, `char` y `String` ocupan cuatro
bytes y usan cargas y almacenamientos `i32`; una celda `String` contiene el
puntero a su descriptor UTF-8 existente. `f64` ocupa ocho bytes, se reserva
alineado a ocho y usa `f64.load/store align=8`. Comparar elementos `String`
invoca `$string_eq`, por lo que compara contenido y no direcciones. Un literal
reserva su bloque durante la ejecución, por lo que llamadas repetidas o
recursivas no sobrescriben datos de otra invocación; la memoria crece si es
necesario. El asignador es monotónico: un literal creado en cada iteración de
un ciclo consume una reserva adicional y no se libera durante la ejecución
actual. Los accesos `arreglo[indice]` comprueban en WebAssembly que el índice
sea no negativo y menor que `N`, y hacen `trap` antes de una lectura fuera del
bloque. En esta etapa solo se admiten literales, lectura e índices `i32` para
arreglos locales: no hay dimensiones adicionales, parámetros, retornos, copia,
comparación de arreglos ni asignación de arreglos o elementos.

También se admiten parámetros `i32`, `f64`, `bool` y `char`, incluidos parámetros mutables,
llamadas anidadas y declaraciones posteriores. Las llamadas usadas como
sentencia descartan resultados con `drop`; las funciones `unit` se generan sin
resultado WebAssembly.

Las sentencias `if`, `if/else` y `else if` se traducen a bloques WAT `if`,
`then` y `else`. Sus ramas conservan las variables locales identificadas por
el análisis semántico, permiten retornos anticipados y ejecutan solamente la
rama cuya condición sea verdadera.

Los ciclos `while` y `loop` se traducen a pares WAT `block`/`loop` con
etiquetas únicas. `break` salta a la salida del ciclo más cercano y `continue`
vuelve al encabezado de ese ciclo; en `while` esto vuelve a evaluar la
condición.

Se rechazan controladamente constantes globales, las formas de arreglos no
admitidas y todos los demás tipos o sentencias.
