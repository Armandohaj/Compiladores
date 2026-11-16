# Match como expresión

Primer bloque: brazos con expresiones, patrones de literales, comodines,
receptores inmutables, tuplas y variantes de enums con datos. La exhaustividad
considera combinaciones de bool, tuplas y variantes anidadas. Para dominios
abiertos como i32 se requiere un patrón receptor o comodín que cubra lo restante.
No basta mencionar una variante si su patrón de datos deja valores sin cubrir.

## Contrato del backend

No se reemplaza el árbol de ANTLR. Nuevos nodos: MatchExprContext,
MatchArmContext, PatternContext, PatternListContext y PatternLiteralContext.
MatchExprContext.expression() es el valor evaluado; matchArm() entrega los
brazos en orden. Cada brazo contiene pattern() y expression().
La ejecución selecciona el primer patrón compatible y evalúa únicamente su brazo.

Se conservan todos los campos de analizar_programa, incluido llamadas_incorporadas.
En tipos_expresiones se registran el match, los brazos y los patrones. En
PatternContext el tipo es el del valor reconocido. PatternLiteralContext tiene
el tipo del literal. Las declaraciones receptoras se agregan a declaraciones
con PatternContext como clave y un identificador de símbolo como valor.
Las lecturas del receptor se vinculan por referencias a esa misma identidad.
Cada brazo tiene su propio ámbito y los receptores son inmutables.
Los nombres read y print continúan protegidos también en los patrones.

Armando debe adaptar la generación de estos nodos; estas pruebas no ejecutan WASM.
No se modifica el backend ni se agregan claves al contrato público.

## Bloques con valor y retornos implícitos

Se admiten bloques con expresión final sin punto y coma.
También se admite el retorno implícito de las funciones.

BlockContext.expression() contiene la expresión final opcional.
Su tipo queda registrado en tipos_expresiones.

El backend debe evaluar esa expresión al finalizar el bloque y utilizarla
como retorno cuando corresponda al cuerpo de una función.

La inicialización posterior a match combina los estados de todos sus brazos.
Una variable queda definitivamente inicializada si recibe valor en todos ellos.

## Pendiente

Los match en constantes globales se rechazan con un diagnóstico controlado;
su evaluación en compilación queda pendiente.

No se detectan brazos redundantes. El tratamiento de saltos dentro de
expresiones requiere una revisión adicional.

Ownership y borrowing se implementarán después de acordar sus reglas.
La ejecución WASM de las nuevas construcciones requiere integración del backend.
## Ejemplos

```rust
enum Resultado { Vacio, Correcto(i32) }
fn main() -> i32 {
    let dato = Resultado::Correcto(10);
    return match dato {
        Resultado::Vacio => 0,
        Resultado::Correcto(numero) => numero,
    };
}
```

```rust
fn main() -> i32 {
    return match true { true => 1 }; // Falta cubrir false.
}
```

## Pruebas

Ejecutar desde la carpeta principal con el entorno virtual activo:

- python pruebas_match.py
- python pruebas_bloques.py
- python ejecutar_pruebas.py

Resultado verificado: 602/602 comprobaciones en 22 suites.
Estas pruebas validan el frontend; no ejecutan WebAssembly.


## Saltos en argumentos e inicializadores

Las llamadas conservan la validación de existencia, cantidad de argumentos
y tipos. Un argumento que no termina normalmente no necesita producir
un valor del tipo esperado.

El backend debe evaluar los argumentos en orden y respetar cualquier salto
antes de emitir la llamada.

Si el inicializador de un let no tiene continuación normal, la declaración
no se crea: su nodo no aparece en declaraciones ni genera un símbolo.

El auxiliar salidas_control, definido en flujo_control.py, permite distinguir
continuación normal, return, break y continue sobre el árbol ANTLR.
La ausencia de normal indica que la evaluación no produce un valor
para la operación siguiente.

Esta información debe considerarse junto con tipos_expresiones.
No se agregan campos al resultado público de analizar_programa.

Validación actual del frontend: 652/652 comprobaciones en 26 suites.
La ejecución WASM requiere adaptación y pruebas del backend.


## Saltos dentro de constructores

Se contemplan saltos dentro de elementos de arreglos y tuplas,
campos de estructuras y argumentos de variantes de enumeraciones.

Una expresión que no continúa normalmente no necesita producir
un valor del tipo esperado. Se conservan las comprobaciones de
campos obligatorios, nombres, duplicados y cantidad de argumentos.

El backend debe respetar los saltos durante la evaluación:
si ocurre uno, no se completa la construcción del valor.

tipos_expresiones debe consultarse junto con salidas_control.
Un tipo registrado no garantiza que la evaluación produzca un valor.

Validación actual del frontend: 704/704 comprobaciones en 29 suites.
Estas pruebas no verifican la ejecución WebAssembly.