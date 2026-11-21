# Ownership y borrowing de RustiQ

## Acuerdo con el backend

- i32, f64, bool y char son Copy.
- String es Move.
- Arreglos, tuplas, estructuras y enums son Copy si todos sus componentes
  son Copy; en caso contrario son Move.
- Un enum se clasifica usando todas sus variantes, no solo la variante activa.
- Los arreglos se clasifican por el tipo de elemento, incluso con longitud cero.
- Los movimientos parciales de campos quedan fuera del alcance inicial.

Un valor Move no podrá usarse después de transferir su propiedad hasta una
reinicialización válida según las reglas de mutabilidad. Esa validación aún
no se ha conectado al analizador en esta primera etapa.

## Primera etapa implementada

clasificacion_propiedad.py contiene:

clasificar_tipo(tipo, estructuras, enumeraciones)

Recibe los tipos canónicos y registros ya existentes. Devuelve Copy o Move.
Devuelve None si no puede clasificar un tipo desconocido, unit o un registro
recursivo inválido; None no debe interpretarse como Move.

No modifica la gramática ni los campos de analizar_programa. No copia memoria,
no mueve variables y no comprueba préstamos. El backend debe copiar los datos
de un compuesto Copy, no limitarse a compartir su dirección.

## Borrowing acordado para la implementación posterior

Se permitirán múltiples referencias inmutables &T o una mutable exclusiva
&mut T. Se impedirán movimientos y modificaciones que entren en conflicto
con préstamos activos. Los préstamos se controlarán por ámbitos y no podrán
sobrevivir a sus valores originales. Se rechazarán referencias devueltas a
variables locales que dejen de existir.

Armando representará las referencias mediante direcciones i32 en memoria
lineal, usando load/store y reservando memoria para valores prestados cuando
corresponda. Los registros semánticos seguirán describiendo tipos RustiQ,
no confundirán &T con el tipo fuente i32 por esa representación del backend.

El nuevo mapa de préstamos debe identificar el nodo ANTLR del préstamo,
el ID del símbolo prestado, el tipo y la mutabilidad. Su formato exacto
se coordinará antes de conectarlo al generador; todavía no se agrega ese mapa.

## Pruebas de esta etapa

python pruebas_clasificacion_propiedad.py
python ejecutar_pruebas.py

Resultado verificado en la copia de trabajo: 31/31 pruebas nuevas de
clasificación; total 783/783 comprobaciones del frontend en 32 suites.
No son pruebas de movimientos, préstamos ni ejecución WASM.

## Segunda etapa implementada Movimientos de valores completos

analizador_ownership.py ejecuta una comprobación después de validar tipos y
resolver los IDs. Usa el árbol ANTLR y los mapas existentes; no agrega un AST,
no modifica la gramática y no agrega campos públicos a analizar_programa.

Se distinguen estados disponible, movido y sin inicializar. El uso de un
valor posiblemente movido también se rechaza. Los errores conservan fase
semantico, mensaje, linea y columna. Un error de ownership vacía los mapas
del backend y deja arbol=None, igual que los otros errores semánticos.

### Transferencias

- let destino = origen y las asignaciones de valores completos transfieren
  un origen Move. Los valores Copy conservan disponible el origen.
- Los argumentos por valor, los retornos y los componentes utilizados para
  construir arreglos, tuplas, estructuras y variantes también transfieren.
- La expresión final de un bloque entrega su valor; un Move se transfiere
  incluso si el resultado del bloque luego se descarta.
- Las comparaciones de variables disponibles leen sus operandos sin moverlos.
- Match se analiza por valor: consume el valor completo si es Move. Después
  introduce los receptores del patrón como valores disponibles en su brazo.
- Las constantes globales representan valores calculados materializados por
  uso, no variables locales que se invaliden. Para compuestos Move el backend
  debe materializar valores independientes; no debe crear alias mutables
  accidentales al reutilizar un puntero del valor constante.

### Reinicialización y accesos parciales

Una asignación válida a una variable mutable movida vuelve a dejarla disponible.
Se mantienen las reglas previas de mutabilidad: mover una variable no autoriza
por sí solo una segunda asignación sin mut.

No se permite extraer por valor un campo o elemento Move mediante accesos.
Se rechaza con un error controlado, también cuando el acceso parte de un
valor temporal. Los campos Copy pueden leerse si su contenedor está disponible.
Modificar un campo de un contenedor completamente movido sigue siendo inválido:
para recuperarlo se requiere reemplazar el valor completo.

### Ramas, cortocircuito y ciclos

Las ramas parten de estados independientes. Solo los caminos que continúan se
combinan; los que retornan no contaminan una continuación que no los ejecuta.
Un consumo opcional a la derecha de && o || deja un posible movimiento.
No se deducen todas las condiciones literales: el análisis es conservador.

Los ciclos calculan un punto fijo de estados de propiedad. Se comprueban los
caminos de repetición normal y continue; break aporta estados de salida del
ciclo más cercano. Reinicializar en cada repetición evita un uso movido en la
siguiente vuelta. Las restricciones previas de inicialización de ciclos del
analizador de tipos se conservan; esta etapa no amplía esa parte del lenguaje.

### Contrato para Armando

Los IDs, declaraciones, referencias y tipos conservan su formato. Los contextos
anteriores indican dónde se transfiere un valor, y clasificar_tipo permite saber
si el backend debe copiar datos o transferir el valor completo. El frontend no
realiza copias físicas, liberaciones de memoria ni operaciones WASM.

El análisis de propiedades debe completarse antes de generar código. Es posible
que un programa aceptado antes ahora se rechace por usar un origen Move después
de transferirlo. En esta validación local las 783 comprobaciones previas se
conservaron sin cambiar sus expectativas.

Ejemplo válido:

```rust
fn main() -> String {
    let mut original = "hola";
    let destino = original;
    original = "nuevo";
    return original;
}
```

Ejemplo inválido:

```rust
fn main() -> String {
    let original = "hola";
    let destino = original;
    return original; // Uso después de movimiento.
}
```

Ejecutar python pruebas_movimientos.py y python ejecutar_pruebas.py.
Resultado local: 40/40 comprobaciones nuevas y 823/823 en 33 suites.
Son pruebas del frontend, no de ejecución WASM. Borrowing, referencias y el
mapa acordado de préstamos permanecen pendientes de implementación.

## Primera implementación de borrowing

Se agrega la fase de préstamos de variables completas y el campo prestamos
confirmado con Armando. Ver BORROWING.md para los nuevos nodos, los usos de
referencias, las escrituras, el formato del mapa y los límites explícitos.
Las referencias compartidas se clasifican Copy y las exclusivas Move.
Resultado local de esta etapa: 891/891 comprobaciones en 34 suites.
El acuerdo de representación WASM no sustituye las pruebas del backend.
