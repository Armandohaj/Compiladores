# Expresiones como sentencia

Una expresión seguida de ; se evalúa y su valor se descarta. Sin ;, la
expresión final del bloque conserva su valor y puede ser un retorno implícito.
Los errores de tipos, movimientos, préstamos y saltos se comprueban igual que
en otras expresiones. Descartar un valor Move consume el origen; descartar
un Copy no lo invalida. Los préstamos temporales terminan al acabar la sentencia.

## Contrato del backend

No hay nuevos nodos ni mapas. StatementContext.expression() identifica la
nueva alternativa, junto con SEMICOLON(). La expresión conserva su tipo en
tipos_expresiones. Las llamadas directas conservan la alternativa anterior
StatementContext.functionCall() y llamadas_incorporadas conserva su formato.

El generador evalúa la expresión y descarta el resultado si produce
un valor. En WASM esto suele requerir drop según la representación y cantidad
de valores de la expresión; unit no produce valor. Si hay return, break o
continue, se debe respetar el salto, sin intentar descartar un resultado que
no se produjo. BlockContext.expression() sigue representando el valor final.

```rust
fn main() -> i32 {
    10 + 20; // Se descarta 30.
    5        // Retorno implícito.
}
```

```rust
fn main() -> String {
    let texto = "hola";
    texto; // Consume el String aunque se descarte.
    texto  // Error: uso después de movimiento.
}
```

Se conserva la adaptación previa para bloques aislados: usar paréntesis
cuando se desea tratarlos expresamente como una expresión, por ejemplo
({ let x = 1; x + 2 });. No se admiten asignaciones como expresión.
El subconjunto de inicializadores constantes sigue exigiendo bloques puros:
no se amplía su evaluación con esta modificación.

Ejecutar python pruebas_expresiones_sentencia.py (17/17) y
python ejecutar_pruebas.py. Estas pruebas validan el frontend; el generador
emite `drop` cuando corresponde y sus pruebas WASM cubren esa alternativa.
