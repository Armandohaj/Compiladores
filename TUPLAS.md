# Tuplas: tipos y acceso por posición

Base: `fa8e564` de `feature/gramatica-semantica`.

## Sintaxis y comportamiento

```rust
const DATO: (i32, bool) = (10, true);

fn main() -> i32 {
    let mut dato = (10, true);
    dato.0 += 5;
    return dato.0;
}
```

- Las tuplas admiten dos o más campos de tipos diferentes, según la gramática del proyecto.
- `(x)` sigue siendo agrupación; `(x,)` y `()` no se incorporan como tuplas.
- Se admiten tipos explícitos, inferencia, parámetros, retornos y constantes globales.
- Se admiten tuplas anidadas y combinaciones con arreglos: `dato.0[1].1`.
- Los campos empiezan en cero y se comprueban durante el análisis semántico.
- Escribir campos requiere un valor inicializado y una variable `mut`.
- Las operaciones compuestas requieren un campo numérico de tipo compatible.
- El contexto de una tupla anotada permite arreglos vacíos en sus campos.
- La inicialización parcial por campos sigue pendiente. Ownership y préstamos
  se validan en el frontend; el soporte WASM se limita al subconjunto indicado
  a continuación.

## Datos para Anthony

No cambia la estructura del resultado de `analizar_programa`.
Los tipos canónicos se representan como `(i32,bool)` o `([i32;0],bool)`.
Los valores constantes usan `tuple` para tuplas y `list` para arreglos.

En asignaciones, `IDENT()`, `assignmentOp()` y `expression()` conservan
sus significados. Los accesos de arreglos y tuplas pueden mezclarse:

- `indexAccess()` entrega los accesos de arreglo.
- `tupleAccess()` entrega los accesos de tupla.
- Para recorrerlos en orden escrito, usar `accesos_escritura(ctx)`
  de `tipos_compuestos.py`; devuelve pares `(clase, nodo)`.
- Para lecturas `postfix`, usar `accesos_lectura(ctx)`.
- La clase es `indice` o `campo`. En un campo, la posición se obtiene
  con `int(nodo.getText()[1:])`.
- En lecturas, un nodo `indice` es directamente la expresión del índice.
- En escrituras, un nodo `indice` es `indexAccess` y contiene `expression()`.
- `referencias[asignacion]` apunta al símbolo base.
- `tipos_expresiones[asignacion]` indica el tipo del destino final.
- Los nodos `tupleAccess` y los `indexAccess` de escritura tienen su tipo
  en `tipos_expresiones`.

`TUPLE_FIELD` evita que `.0.1` se convierta accidentalmente en un decimal.
La alternativa `DOT INT` también admite espacios entre el punto y el campo.
Los literales decimales mantienen su sintaxis anterior.

Los índices dinámicos de arreglos requieren guardas en el backend. El
generador admite tuplas locales planas de campos `i32`, `f64`, `bool` y `char`,
incluyendo lectura, escritura, copia independiente, préstamos y patrones
`match` compatibles. No admite todavía tuplas con `String`, tuplas anidadas ni
parámetros o retornos de tuplas completas.

## Pruebas

```bash
java -jar tools/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -no-listener -o generated RustiQ.g4
python ejecutar_pruebas.py
```

Las pruebas de este documento corresponden al frontend. La validación actual
del proyecto debe ejecutarse con `python ejecutar_pruebas.py` y
`python -m pytest tests -q`.
