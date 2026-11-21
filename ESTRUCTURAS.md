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
- Las referencias y ownership no se incorporan todavía; tampoco la inicialización parcial por campos.

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

No se modifica la interfaz web ni se implementa el backend. Los índices
dinámicos de arreglos todavía requieren guardas en la ejecución Wasm.

## Verificación

```bash
java -jar tools/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -no-listener -o generated RustiQ.g4
python ejecutar_pruebas.py
```

Resultado verificado con Python 3.12.14 y ANTLR/runtime 4.13.2:
460/460 comprobaciones en 17 suites, incluidos 73 casos de estructuras.
Confirmar en Python 3.14 del equipo antes de publicar los cambios.
