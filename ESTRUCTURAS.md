# Estructuras: entrega sobre ea734ce

```rust
struct Persona { edad: i32, activo: bool }

fn main() -> i32 {
    let mut persona = Persona { edad: 20, activo: true };
    persona.edad += 1;
    return persona.edad;
}
```

## Reglas implementadas

- Declaraciones y constructores, incluidos los de estructuras sin campos.
- Tipos nominales, anotaciones, inferencia, parámetros y retornos.
- Lecturas y asignaciones de campos con control de inicialización y `mut`.
- Combinaciones con arreglos y tuplas; contexto para arreglos vacíos.
- Constantes globales de estructuras y accesos a sus campos.
- Rechazo de campos duplicados, ausentes, desconocidos o de tipo incorrecto.
- Rechazo de tipos desconocidos y dependencias recursivas de estructuras por valor.
- Ownership y referencias ya se validan; la inicialización parcial por campos
  sigue fuera del alcance. El soporte WASM se limita a estructuras locales con
  campos básicos y al préstamo de la estructura completa.

## Contrato para Anthony

Se conservan los campos anteriores de `analizar_programa`. Se añade
`estructuras`: nombre -> diccionario de campos con sus tipos. Si hay errores,
este mapa también está vacío. El orden del diccionario de campos es el de
su declaración; usar ese orden para decidir el layout, aunque el constructor
escriba campos en otro orden.

Un valor constante de estructura se representa como:

```python
{"estructura": "Persona", "campos": {"edad": 20, "activo": True}}
```

Los helpers `accesos_lectura` y `accesos_escritura` admiten una tercera clase:
`nombre`. Su nodo es `fieldAccess` y `nodo.IDENT().getText()` da el campo.
Las clases previas `indice` y `campo` mantienen su significado.

`tipos_expresiones[nodo_fieldAccess]` entrega el tipo después del acceso.
En un destino, `referencias[asignacion]` sigue apuntando al símbolo base y
`tipos_expresiones[asignacion]` entrega el tipo final del destino.
No confundir nombres de tipos ni nombres de campos con variables locales.

El generador utiliza el orden de este registro para el layout de estructuras
locales con campos `i32`, `f64`, `bool` y `char`. Admite lectura, escritura,
copia independiente y parámetros por referencia de esas estructuras. No
admite estructuras con campos `String` o compuestos, ni parámetros o retornos
por valor de estructuras.

## Verificación

```bash
java -jar tools/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -no-listener -o generated RustiQ.g4
python ejecutar_pruebas.py
```

La validación actual del proyecto se ejecuta con `python ejecutar_pruebas.py`
y `python -m pytest tests -q`; la segunda suite valida la generación y
ejecución WASM del subconjunto admitido.
