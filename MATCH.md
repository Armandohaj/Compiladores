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