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

## Ejecución desde PowerShell

Para compilar un archivo RustiQ, guardar el binario junto al archivo fuente y
ejecutar `main()` con Wasmtime en un proceso separado:

```powershell
python .\ejecutar_escritorio.py .\programa.rustiq
```

Por ahora el ejecutor admite `main()` sin parámetros con retorno `i32`. La
ejecución tiene un límite de tres segundos; si no termina, el proceso Wasm se
detiene y se informa el límite superado.

Para ejecutar directamente un archivo `.wasm` descargado desde el editor, sin
leer ni recompilar código RustiQ, instala Wasmtime y ejecuta:

```powershell
python -m pip install wasmtime==50.0.1
python .\ejecutar_wasm.py .\programa.wasm
```

Este ejecutor valida el módulo con Wasmtime y requiere que exporte `main()` sin
parámetros con retorno `i32`. No modifica el archivo recibido y aplica el mismo
límite de tres segundos a la ejecución.

Los módulos pueden importar `env.read_i32` y `env.print_i32`. Para entregar
valores a `read_i32` desde PowerShell, repite `--entrada`; las llamadas se
atienden en ese mismo orden y las salidas se muestran antes del resultado:

```powershell
python .\ejecutar_wasm.py .\programa.wasm --entrada 10 --entrada 20
```

Si el módulo solicita más valores de los indicados, la ejecución termina con un
error; no se inventan entradas. Esta primera versión recibe todos los números
antes de comenzar. Debe revisarse si se exige ingreso interactivo durante la
ejecución.

También hay una ventana de escritorio básica para demostrar el mismo binario
descargado desde el editor web. En Windows se abre con:

```powershell
python .\visor_wasm.py
```

Selecciona el archivo `.wasm` con **Abrir archivo** y después pulsa
**Ejecutar**. La ventana valida `main() -> i32`, conserva el binario solo en
memoria, ejecuta en segundo plano y muestra el resultado o el error sin
modificar el archivo seleccionado. Las entradas i32 se escriben antes de
ejecutar, separadas por espacios o comas; las salidas `print_i32` se muestran
en el área de resultados en el orden producido.

## Alcance actual

Se admiten funciones que retornan `i32`, `f64`, `char`, `bool` o `String`
(`bool` se representa como `i32` 0/1 en WebAssembly), con declaraciones `let`
y `let mut`, y asignaciones
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
actual. Si el crecimiento de memoria es rechazado por el runtime o se agota el
espacio direccionable, la ejecución hace `trap`. Los accesos `arreglo[indice]`
comprueban en WebAssembly que el índice
sea no negativo y menor que `N`, y hacen `trap` antes de una lectura fuera del
bloque. En esta etapa se admiten literales, lectura e índices `i32` para
arreglos locales. También se admite la asignación de elementos con `=` y, para
elementos `i32` y `f64`, con `+=`, `-=`, `*=` y `/=`; las direcciones conservan
las mismas comprobaciones de límites antes de cargar o almacenar. No hay
parámetros, retornos, copia, comparación ni asignación completa de arreglos.

También se admiten matrices locales de dos dimensiones `[[T; columnas];
filas]` para `i32`, `bool`, `char`, `f64` y `String`. Sus elementos se guardan
contiguamente por filas en el mismo bloque; `matriz[fila][columna]` usa
`$array_addr` para comprobar y calcular cada dimensión antes de cargar el
elemento. Las matrices conservan los tamaños y alineaciones de los arreglos,
incluida la alineación de ocho bytes para `f64` y los punteros a descriptores
para `String`. Sus elementos admiten las mismas asignaciones indexadas que los
arreglos. No se admiten más de dos dimensiones, ni parámetros, retornos,
copias, comparaciones o asignaciones completas de matrices.

Con el análisis de ownership actual, `String` y los arreglos o matrices que lo
contienen son valores `Move`. Por ello, comparar un elemento `String` es válido,
pero retornarlo, asignarlo o pasarlo por valor intentaría hacer un movimiento
parcial y el frontend lo rechaza antes de generar WASM. Esta restricción se
mantiene hasta que exista soporte de borrowing; el generador no la elude.

También se admiten tuplas locales de dos o más campos `i32`, `f64`, `bool` y
`char`, declaradas con tipo explícito o inferido. Cada tupla reserva un bloque
propio en la memoria lineal: los campos `i32`, `bool` y `char` ocupan cuatro
bytes; los campos `f64` se alinean y cargan/almacenan a ocho bytes. Se pueden
leer campos `.0`, `.1`, etc., y asignar campos de una tupla `mut`, incluidas
las operaciones `+=`, `-=`, `*=` y `/=` para `i32` y `f64`. Todavía no se
admiten tuplas con `String`, tuplas anidadas, copias o asignaciones completas,
parámetros ni retornos de tuplas; esos casos producen un error de generación
controlado para no compartir accidentalmente su almacenamiento.

Las estructuras locales con campos `i32`, `f64`, `bool` y `char` usan la misma
memoria lineal y alineación que las tuplas. El layout sigue el orden de
declaración registrado por el frontend, incluso si el constructor escribe sus
campos en otro orden; las expresiones de ese constructor sí se evalúan y se
almacenan en el orden en que fueron escritas. Se admiten lecturas por nombre,
asignaciones simples y operaciones compuestas numéricas sobre campos de una
estructura `mut`. No se admiten todavía campos `String`, arreglos, tuplas o
estructuras, copias ni asignaciones completas, parámetros o retornos de
estructuras; esas formas se rechazan controladamente.

Los bloques con valor se generan ejecutando primero sus sentencias y luego su
expresión final. Se admiten como inicializadores, argumentos, retornos y otras
expresiones para `i32`, `f64`, `bool`, `char` y `String`. La expresión final
del cuerpo de una función compatible con su firma se retorna implícitamente;
los `return` explícitos conservan prioridad. Los bloques sin expresión final
son `unit` y no dejan valores en la pila Wasm. Si una sentencia o expresión
termina mediante `return`, no se genera el resto de ese bloque ni la operación
que habría consumido su valor. Los valores de enums siguen fuera del backend
Wasm y se rechazan controladamente.

Se admiten expresiones `match` sobre `i32`, `bool` y `char` con patrones
literales, comodín `_` y receptor. El valor se evalúa una sola vez en un local
Wasm y los brazos se prueban en el orden escrito, por lo que sólo se ejecuta el
primer brazo compatible. Los receptores reutilizan su identificador resuelto
por el frontend y los brazos pueden usar bloques con valor, `return`, `read()`
y `print()`. Aún no se admiten patrones o valores de `f64` y `String`, ni
patrones de tuplas, enums o variantes con datos; se rechazan con un error de
generación controlado.

Las enumeraciones sin datos se representan como `i32` usando exactamente las
etiquetas entregadas por el frontend. Se admiten variables locales inferidas o
anotadas, lectura, reasignación de variables `mut`, comparaciones permitidas y
patrones `Enum::Variante` dentro de `match`; el orden de los brazos conserva la
primera coincidencia. No se admiten parámetros, retornos ni constantes globales
de enum, arreglos o compuestos que los contengan. Si una enumeración del módulo
tiene alguna variante con datos asociados, todo el módulo se rechaza antes de
generar WASM.

También se admiten parámetros `i32`, `f64`, `bool`, `char` y `String`, incluidos
parámetros mutables, llamadas anidadas y declaraciones posteriores. Las llamadas usadas como
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

Las llamadas incorporadas `read()` y `print(i32)` generan, respectivamente,
los imports `env.read_i32` y `env.print_i32`. Los módulos que no usan estas
operaciones no declaran imports adicionales. La validación de firmas y usos
incorrectos corresponde al frontend; el generador solo consulta
`llamadas_incorporadas` para emitir las llamadas WebAssembly.

Las constantes globales `i32`, `f64`, `bool`, `char` y `String` se incorporan
como literales Wasm a partir del valor ya calculado por el análisis semántico;
por ello admiten dependencias y referencias adelantadas sin reevaluarse en el
generador. Las constantes `String` reutilizan los descriptores UTF-8 y la
memoria exportada existentes. Una variable local con el mismo nombre conserva
prioridad mediante los identificadores de la resolución de referencias.
Las constantes de arreglos y matrices se rechazan controladamente, al igual que
las demás formas de arreglos no admitidas y tipos o sentencias pendientes.
