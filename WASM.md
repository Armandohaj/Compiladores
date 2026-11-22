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
comparación general de arreglos. Los arreglos Copy, incluidos los que contienen
tuplas, estructuras, enums u otros arreglos Copy, admiten copia y asignación
completas: se reserva un bloque independiente y se clonan recursivamente los
punteros internos. Admiten parámetros y retornos por valor. Los arreglos Move
con `String` transfieren su bloque completo cuando ownership lo permite, sin
copiar automáticamente sus descriptores.

También se admiten matrices locales de dos dimensiones `[[T; columnas];
filas]` y arreglos anidados de más dimensiones con layout recursivo válido.
Sus elementos se guardan
contiguamente por filas en el mismo bloque; `matriz[fila][columna]` usa
`$array_addr` para comprobar y calcular cada dimensión antes de cargar el
elemento. Las matrices conservan los tamaños y alineaciones de los arreglos,
incluida la alineación de ocho bytes para `f64` y los punteros a descriptores
para `String`. Sus elementos admiten las mismas asignaciones indexadas que los
arreglos. Las matrices Copy admitidas, incluso con elementos compuestos Copy,
también admiten copia y asignación completas en un bloque independiente mediante
`memory.copy` y clonación recursiva de punteros, incluido `f64` alineado a ocho
bytes, parámetros y retornos por valor. Las
matrices no admiten comparación general; las que contienen `String` son Move y
no admiten copias automáticas.

Con el análisis de ownership actual, `String` y los arreglos o matrices que lo
contienen son valores `Move`. Por ello, comparar un elemento `String` es válido,
pero retornarlo, asignarlo o pasarlo por valor intentaría hacer un movimiento
parcial y el frontend lo rechaza antes de generar WASM. El backend ya admite
préstamos de contenedores con elementos básicos, pero no de `String`; esta
restricción se mantiene para evitar transferencias parciales incorrectas.

También se admiten tuplas locales de dos o más campos `i32`, `f64`, `bool`,
`char`, `String`, otras tuplas y estructuras, declaradas con tipo explícito o
inferido. Cada tupla reserva un bloque
propio en la memoria lineal: los campos `i32`, `bool` y `char` ocupan cuatro
bytes; los campos `f64` se alinean y cargan/almacenan a ocho bytes. Se pueden
leer campos `.0`, `.1`, etc., y asignar campos de una tupla `mut`, incluidas
las operaciones `+=`, `-=`, `*=` y `/=` para `i32` y `f64`. Los arreglos y
matrices admitidos también pueden ser elementos de tuplas. Las copias y
asignaciones completas de tuplas Copy admitidas reservan
un bloque independiente y usan `memory.copy`, incluso si el valor proviene de
un bloque con valor; origen y destino no comparten almacenamiento.

Las estructuras locales con campos `i32`, `f64`, `bool`, `char`, `String`,
tuplas y otras estructuras usan la misma
memoria lineal y alineación que las tuplas. El layout sigue el orden de
declaración registrado por el frontend, incluso si el constructor escribe sus
campos en otro orden; las expresiones de ese constructor sí se evalúan y se
almacenan en el orden en que fueron escritas. Se admiten lecturas por nombre,
asignaciones simples y operaciones compuestas numéricas sobre campos de una
estructura `mut`. Se admiten parámetros y retornos por valor de estructuras.
Los arreglos y matrices admitidos también pueden ser campos de estructuras.
Las copias y asignaciones
completas de estructuras Copy admitidas usan un bloque independiente en la
memoria lineal, por lo que sus campos pueden modificarse sin alterar el origen.

Los bloques con valor se generan ejecutando primero sus sentencias y luego su
expresión final. Se admiten como inicializadores, argumentos, retornos y otras
expresiones para `i32`, `f64`, `bool`, `char` y `String`. La expresión final
del cuerpo de una función compatible con su firma se retorna implícitamente;
los `return` explícitos conservan prioridad. Los bloques sin expresión final
son `unit` y no dejan valores en la pila Wasm. Si una sentencia o expresión
termina mediante `return`, no se genera el resto de ese bloque ni la operación
que habría consumido su valor. Los valores de enums se generan con la
representación descrita más adelante.

Se admiten expresiones `match` sobre `i32`, `bool`, `char`, `f64`, `String` y
tuplas locales, incluidas tuplas anidadas. Los patrones de tupla admiten
literales compatibles, comodín `_`, receptores y patrones de tupla internos;
los patrones `String` usan `$string_eq` y comparan el UTF-8, no la dirección
del descriptor. Un literal usado directamente como valor del `match` se
materializa con el mismo layout de memoria de las tuplas locales. El valor se
evalúa una sola vez en un local Wasm y los brazos se prueban en el orden
escrito, por lo que sólo se ejecuta el primer brazo compatible. Los receptores
reutilizan su identificador resuelto por el frontend y los brazos pueden usar
bloques con valor, `return`, `read()` y `print()`.

Las enumeraciones sin datos se representan como `i32` usando exactamente las
etiquetas entregadas por el frontend. Si una enumeración contiene alguna
variante con datos, todos sus valores se almacenan independientemente en la
memoria lineal: la etiqueta ocupa los primeros 4 bytes y los datos `i32`,
`bool`, `char`, `f64` y `String` siguen con sus alineaciones naturales. Los
campos `String` guardan el puntero a su descriptor UTF-8 existente. Los datos
asociados también pueden ser tuplas, estructuras, arreglos y otras
enumeraciones admitidas; los valores compuestos se guardan como punteros a sus
bloques propios. Se admiten
variables locales inferidas o anotadas y reasignación de variables `mut`.
Las enumeraciones con sólo datos Copy mantienen sus copias locales independientes;
las que contienen `String` son Move y transfieren su puntero sin usar `memory.copy`.
`match` compara primero la
etiqueta y después los patrones literales compatibles; los receptores usan los
identificadores resueltos por el frontend y sólo se cargan en el brazo elegido.
Los patrones de tupla y de variantes enum pueden anidarse cuando sus tipos son
compatibles. Los enums Copy clonan recursivamente los bloques internos al
copiarse, mientras que los enums Move transfieren sus punteros.
Las comparaciones `==` y `!=` de enums con datos comparan etiqueta y datos de
forma estructural, incluidos `String`, tuplas, estructuras, arreglos y enums
anidados admitidos. Las enumeraciones admitidas pueden
usarse como parámetros y retornos: las variantes sin datos viajan como su
etiqueta `i32` y las variantes con datos Copy se copian a un bloque independiente
antes de una llamada; las variantes Move con `String` se transfieren. Los
patrones `String` comparan contenido mediante `$string_eq`. Los arreglos y
matrices de enums, y los campos enum dentro de estructuras o tuplas, reutilizan
la misma representación `i32`.

También se admiten parámetros `i32`, `f64`, `bool`, `char` y `String`, incluidos
parámetros mutables, llamadas anidadas y declaraciones posteriores. Las llamadas usadas como
sentencia descartan resultados con `drop`; las funciones `unit` se generan sin
resultado WebAssembly.

Los préstamos locales `&T` y `&mut T` de `i32`, `f64`, `bool` y `char` se
representan como direcciones `i32`. Cuando una variable escalar aparece como
origen en el mapa `prestamos` del frontend, el generador la reserva en memoria
lineal y sus lecturas y escrituras directas usan esa misma celda. Se admiten
lecturas `*r`, escrituras `*r = valor`, asignaciones compuestas numéricas y
parámetros referencia escalares. También se admiten préstamos de estructuras,
tuplas, arreglos y matrices locales con layouts recursivos admitidos. Estos
compuestos ya viven en memoria, de modo que
la referencia reutiliza su puntero original: `p.campo`, `r.0`, `r[i]` y
`r[i][j]` calculan sus desplazamientos con los layouts existentes y las
comprobaciones de límites de `$array_addr`; las escrituras por `&mut` actualizan
el bloque de origen. Los parámetros referencia de esos mismos tipos también se
admiten. Las enumeraciones prestadas se materializan en una celda que guarda su
etiqueta o puntero, por lo que `*r` sirve para leerlas en `match` y `&mut Enum`
puede reemplazar la variante del origen. Los receptores `i32`, `bool` y `char` de patrones `match` también
pueden prestarse de forma compartida. Al entrar únicamente en el brazo elegido,
su valor se materializa en una celda propia y el receptor y `*r` usan esa misma
dirección; esto conserva el sombreado resuelto por ID. Los receptores básicos de
variantes de enum siguen el mismo mecanismo. La exclusividad, las vidas y la
mutabilidad siguen siendo responsabilidad del frontend. Aún se rechazan
receptores `f64`, préstamos de parámetros normales, retornos o reasignaciones
de referencias. Los `String` prestados también usan una celda de descriptor y
pueden leerse y reemplazarse mediante `&mut`; extraerlos por valor sigue siendo
un movimiento rechazado por el frontend. La desreferenciación completa `*r` de
un compuesto Copy materializa una copia profunda independiente; los compuestos
Move siguen rechazados para no permitir extraerlos mediante una referencia.

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

Las constantes globales de tipos básicos, `String`, arreglos, tuplas,
estructuras y enums se materializan a partir del valor ya calculado por el
análisis semántico; por ello admiten dependencias y referencias adelantadas sin
reevaluarse en el generador. Los valores compuestos se reservan al usarse con
su layout recursivo y sin compartir un bloque mutable entre usos. Las
constantes `String` reutilizan los descriptores UTF-8 y la memoria exportada
existentes. Una variable local con el mismo nombre conserva prioridad mediante
los identificadores de la resolución de referencias.
Las constantes locales usan el mismo valor precomputado de su símbolo y no
emiten código para su inicializador; los ámbitos y el sombreado se resuelven
por ID. Las constantes compuestas reutilizan el layout de su tipo al
materializarse en una función.

Una expresión seguida de punto y coma se ejecuta como sentencia y descarta su
resultado con `drop` cuando produce un valor. Las expresiones `unit` no dejan
valores en la pila y no generan `drop`; si la expresión termina con `return`,
`break` o `continue`, tampoco se emite un descarte posterior. La expresión sin
punto y coma al final de un bloque mantiene su valor para el retorno implícito.
