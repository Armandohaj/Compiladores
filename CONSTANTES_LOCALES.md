# Constantes locales

Se admite const N: i32 = 10; en funciones y bloques. Tipo e inicializador
son obligatorios. El nombre se registra después de validar el inicializador;
se admiten constantes previas visibles, no referencias locales adelantadas.
Se rechazan duplicados del mismo ámbito; se permite sombreado en ámbitos internos.

Los inicializadores se calculan al compilar: pueden usar constantes visibles,
aritmética, compuestos, match y bloques puros con let inmutable. No pueden
leer variables o parámetros, llamar funciones (incluidas read/print), crear
préstamos, asignar, ejecutar ciclos o saltos. Se revisan también ramas omitidas
por cortocircuito. Una constante no puede modificarse ni prestarse. Como en
constantes globales, cada uso de String/compuestos materializa su valor.

Limitación explícita: no se admiten declaraciones const anidadas dentro del
inicializador de otra constante; se rechazan con diagnóstico. Utilizar const
previas y referenciarlas en el inicializador.

## Contrato para Armando

Nuevo nodo ConstLocalDeclContext: IDENT(), type_() según el parser generado
(o getTypedRuleContext(TypeContext, 0)) y expression(). StatementContext
expone constLocalDecl(). Se conserva el árbol ANTLR y las claves públicas.

declaraciones[nodo_const_local] contiene su ID. simbolos[id] conserva
nombre, tipo, funcion, es_constante=True, mutable=False y valor calculado,
como las constantes globales. referencias sigue vinculando las lecturas
al ID correcto. El nombre por sí solo no basta: puede estar sombreado.
El generador reconoce esta sentencia y materializa el valor ya calculado sin
ejecutar el inicializador en runtime. No cambia prestamos ni
llamadas_incorporadas.

Los mapas internos de valores locales se indexan por nodo, no por nombre,
para evitar mezclar constantes de distintas funciones o bloques.

```rust
const BASE: i32 = 10;
fn main() -> i32 {
    const LIMITE: i32 = BASE + 2;
    LIMITE
}
```

El módulo WASM generado devuelve 12.

```rust
fn main() {
    let numero = read();
    const LIMITE: i32 = numero; // Error: depende de un valor de runtime.
}
```

Ejecutar python pruebas_constantes_locales.py (28/28) y
python ejecutar_pruebas.py. Estas pruebas validan el frontend; el generador
también tiene pruebas de Wasmtime para las constantes locales admitidas.
