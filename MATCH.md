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

## Pendiente

Aún no se incorporan bloques como expresiones ni expresiones finales sin punto
y coma. Usar por ahora return match ...; o let resultado = match ...;.
Los match en constantes globales se rechazan con un diagnóstico controlado;
su evaluación en compilación queda pendiente. No se detectan brazos redundantes.
Ownership y borrowing se implementarán después de acordar sus reglas.

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

Ejecutar python pruebas_match.py y python ejecutar_pruebas.py.
Validación local: 32/32 nuevas, total 582/582 en 21 suites,
Python 3.12 y runtime ANTLR 4.13.2.
