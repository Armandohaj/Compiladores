# Entrada y salida: contrato del frontend

Se conservan las reglas y los archivos generados de ANTLR. Las funciones
incorporadas se reconocen como FunctionCallContext mediante IDENT.

| Operación | Parámetros | Retorno | Importación WASM acordada |
|---|---|---|---|
| read | ninguno | i32 | env.read_i32 |
| print | i32 | unit | env.print_i32 |

`analizar_programa(codigo)["llamadas_incorporadas"]` contiene
FunctionCallContext -> "read" o "print". Son los mismos nodos del árbol
entregado, presentes también en tipos_expresiones, con i32 o unit.
Si hay cualquier error, el mapa se entrega vacío, igual que los demás
mapas del backend. No se serializa directamente a JSON.

`funciones` conserva exclusivamente las firmas de funciones del usuario.
No se agregan firmas incorporadas a ese campo: así se conservan sus
consumidores actuales. El registro interno de firmas reutiliza la misma
validación de cantidad y tipos de argumentos.

Los nombres read y print no pueden declararse como funciones, constantes,
variables ni parámetros (incluidos ámbitos interiores). No son palabras
reservadas del lexer; campos y variantes conservan su propio espacio de nombres.
Todas las llamadas en constantes globales continúan prohibidas.
print solo se permite como sentencia directa; no como valor, argumento,
inicializador, comparación o expresión de retorno. read sí produce un i32.
Los errores conservan fase, mensaje, linea y columna (desde 1).

Ejemplo válido:
```rust
fn main() -> i32 {
    let numero: i32 = read();
    print(numero + 1);
    return 0;
}
```

Ejemplos inválidos independientes:
```rust
fn main() { print(true); } // print requiere i32
```
```rust
const LIMITE: i32 = read(); // La lectura sucede en ejecución.
```

## Defensa y ejecución

El frontend comprueba tipos y registra llamadas: no solicita entrada ni
imprime los valores del programa. Armando debe emitir las importaciones
acordadas y proveerlas en web y escritorio. No se han probado aquí esas
importaciones ni la ejecución WASM.

Ejecutar desde la raíz con el entorno virtual activo:
```bash
python pruebas_entrada_salida.py
python ejecutar_pruebas.py
```

Validación local: Python 3.12, runtime ANTLR 4.13.2, 36/36 comprobaciones
nuevas; total 550/550 en 20 suites. No se modificó el código del backend.
