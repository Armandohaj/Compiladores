# Arreglos: contrato del frontend

Base de esta entrega: `f670db0` en `feature/gramatica-semantica`.

## Comportamiento

- Los arreglos vacíos necesitan contexto de tipo, por ejemplo `[i32;0]`.
- El contexto se obtiene de una declaración, constante, parámetro, retorno o asignación.
- Los arreglos anidados propagan el tipo esperado a sus elementos.
- Escribir elementos exige un arreglo inicializado y una variable `mut`.
- Se admiten `=`, `+=`, `-=`, `*=` y `/=` en elementos.
- Cambiar un elemento no inicializa un arreglo que estaba sin inicializar.
- La comparación de tipos incluye el tipo de elemento y todos los tamaños.

## Datos para el backend

La estructura del resultado de `analizar_programa` se conserva.

Para una asignación `a[i][j] += x`:

- `ctx.IDENT()` sigue siendo `a`.
- `ctx.expression()` sigue siendo el valor derecho, `x`.
- `ctx.assignmentOp()` indica `+=`.
- `ctx.indexAccess()` entrega los accesos en orden; cada acceso tiene `expression()`.
- `referencias[ctx]` apunta al símbolo del arreglo base.
- Las variables usadas en índices también aparecen en `referencias`.
- `tipos_expresiones[ctx]` indica el tipo del elemento de destino.
- `tipos_expresiones[acceso]` indica el tipo después de cada índice.

El backend debe evaluar cada índice una vez, en orden, y comprobar
`0 <= indice < tamaño` antes de leer o escribir. El frontend detecta
índices literales fuera de rango; el evaluador comprueba también índices
calculados en constantes. Los índices dinámicos necesitan guardas Wasm.

Esta entrega valida el frontend; no implementa ejecución Wasm,
inicialización parcial, ownership ni préstamos.

## Verificación

Usar el entorno virtual del proyecto y ANTLR/runtime 4.13.2:

```bash
java -jar tools/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -no-listener -o generated RustiQ.g4
python ejecutar_pruebas.py
```

Resultado verificado con Python 3.12.14: 319/319 comprobaciones,
15 suites, sin fallos. Confirmar también en el entorno Python del equipo.
