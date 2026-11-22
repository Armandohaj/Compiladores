# Borrowing de valores completos

Base de la integración inicial: 015138c, posterior a la validación de
ownership. El frontend valida los préstamos y el generador WASM implementa
el subconjunto de referencias descrito al final de este documento.

## Reglas admitidas

- &variable crea un préstamo compartido. Puede coexistir con otros compartidos.
- &mut variable crea un préstamo exclusivo y exige que el origen sea mutable.
- *referencia lee el valor prestado. *referencia = valor y las asignaciones
  compuestas escriben si el tipo es &mut T; el binding de la referencia no
  necesita let mut para escribir el valor apuntado.
- Un préstamo compartido impide modificar o mover el origen, pero permite leer
  y copiar sus datos Copy. Un exclusivo impide también el acceso directo al origen.
- Se puede prestar un arreglo, tupla, estructura, enum o String completos.
  No se permite sacar un valor Move mediante desreferenciación.
- Los préstamos guardados en variables viven hasta salir del ámbito de esas
  variables. Los temporales de argumentos se liberan al terminar la sentencia.
  No se implementa el análisis de último uso de Rust.
- Una referencia compartida es Copy. Una exclusiva es Move: transferirla
  invalida su variable anterior y no crea dos capacidades de escritura.
- Los parámetros &T y &mut T se admiten; los conflictos de sus argumentos se
  comprueban en el caller. La vida del origen debe cubrir la llamada.
- Un bloque puede entregar una referencia a un origen exterior vivo, pero
  se rechaza si entrega una referencia a una variable local que desaparece.

## Nuevos nodos y tipos de ANTLR

BorrowExprContext corresponde a &x o &mut x y tiene unary() como operando.
DereferenceExprContext corresponde a *r y también tiene unary() como operando.
DereferenceTargetContext corresponde al destino simple *r de una asignación.
AssignmentContext.dereferenceTarget() lo distingue de los destinos anteriores.
Los destinos anteriores conservan IDENT(), indexAccess(), tupleAccess() y fieldAccess().

Los tipos canónicos permanecen en RustiQ: &i32, &mut i32, &[i32;2], etc.
La representación como dirección i32 es responsabilidad del generador WASM.
No se reemplaza el árbol ANTLR ni se agrega otro parser.

## Contrato prestamos

analizar_programa(codigo) conserva los campos anteriores y agrega prestamos:

```python
resultado['prestamos'][nodo_borrow] = {
    'simbolo_id': id_del_origen,
    'tipo': tipo_del_valor_prestado,
    'mutable': es_exclusivo,
}
```

La clave es el BorrowExprContext original del árbol entregado. simbolo_id es
un ID ya existente en simbolos. tipo es el tipo del origen, por ejemplo i32;
el tipo de la expresión de préstamo, guardado en tipos_expresiones, será &i32
(o &mut i32). El mapa no contiene direcciones ni préstamos sintéticos de parámetros.
Las llamadas y préstamos ubicados en código no alcanzado por el recorrido de flujo
pueden no aparecer en sus mapas: el generador debe respetar los saltos del árbol.

Si hay cualquier error léxico, sintáctico, de tipos, ownership o borrowing,
prestamos es {}, arbol es None y los mapas anteriores también quedan vacíos.
Las claves de nodos no se serializan directamente como JSON para el navegador.

## Cómo identificar los usos y desreferenciaciones

En let r = &x hay dos identidades: el ID de x identifica el origen prestado;
el ID de r identifica la variable que contiene la referencia.

- declaraciones[nodo_let_de_r] identifica a r. simbolos[id_r]['tipo'] es &T
  o &mut T.
- Una lectura posterior de r es un PrimaryContext y referencias[nodo_primary]
  sigue apuntando a id_r, igual que las demás lecturas.
- Para leer *r, el backend visita DereferenceExprContext.unary(). El PrimaryContext
  interior se vincula con r mediante referencias. tipos_expresiones[nodo_deref]
  es T: indica el tipo que debe leerse, no la dirección.
- Para escribir *r = valor, AssignmentContext.dereferenceTarget() identifica el
  destino. referencias[nodo_assignment] y referencias[nodo_destino] son id_r.
  tipos_expresiones guarda T para el destino y la asignación. El backend debe
  cargar la dirección contenida en r y escribir allí el valor; no sustituir r.
- Las expresiones entre paréntesis conservan sus nodos y tipos. Los parámetros
  referencia se identifican con los símbolos y firmas de funciones existentes.

El generador reserva almacenamiento para un origen escalar prestado y reutiliza
el layout de los compuestos que ya viven en memoria. Los campos anteriores y
los IDs no cambian de formato.

## Ejemplos

Compartidos compatibles:

```rust
fn main() -> i32 {
    let numero = 10;
    let a = &numero;
    let b = &numero;
    return *a + *b;
}
```

Modificación exclusiva y liberación por ámbito:

```rust
fn incrementar(r: &mut i32) {
    *r += 1;
}
fn main() -> i32 {
    let mut numero = 10;
    incrementar(&mut numero); // Préstamo temporal de esta sentencia.
    {
        let r = &mut numero;
        *r = 20;
    } // r deja de existir y termina el préstamo.
    return numero;
}
```

Conflicto que debe rechazarse:

```rust
fn main() {
    let mut numero = 10;
    let a = &numero;
    let b = &mut numero; // No es exclusivo: a sigue vivo.
}
```

Referencia fuera de la vida de su origen que debe rechazarse:

```rust
fn main() -> i32 {
    let referencia = {
        let local = 10;
        &local
    };
    return *referencia;
}
```

## Límites del frontend

Se rechazan de forma controlada préstamos a campos, elementos, constantes
globales y temporales; représtamos y referencias anidadas; y patrones sobre
referencias. El frontend sí permite prestar valores completos de arreglos,
tuplas, estructuras, enums y `String`, pero el backend solo materializa el
subconjunto indicado más abajo.

No se admite todavía asignar o reasignar una variable referencia: utilizar
let r = &x con inicializador. Se rechazan todas las funciones que declaran
retorno referencia, incluso si procediera de un parámetro. Esto es más
restrictivo que Rust y queda pendiente de ampliar si se necesita ese caso.

Las escrituras por desreferenciación tienen destino simple *r. No se admite
(*r).campo = valor como destino en esta gramática inicial.

Los préstamos producidos por alternativas se acumulan conservadoramente;
esto puede rechazar préstamos exclusivos mutuamente excluyentes. Tampoco se
acortan las vidas de préstamos de bindings movidos ni por su último uso.
Para liberar un préstamo antes, usar un bloque interior explícito.

Se mantienen las restricciones anteriores de inicialización y ciclos.
Estos límites no deben presentarse como compatibilidad completa con Rust.

## Archivos y verificación

RustiQ.g4 define la sintaxis; los archivos de generated se regeneran con:

```bash
java -jar tools/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -no-listener -o generated RustiQ.g4
```

tipos_referencias.py identifica tipos y destinos permitidos.
analizador_semantico.py comprueba tipos y escrituras por referencia.
resolucion_variables.py conserva los IDs de lecturas y destinos.
analizador_ownership.py impide transferir el valor prestado por desreferenciación.
analizador_prestamos.py comprueba conflictos y vidas útiles y produce el mapa.
main.py conecta la fase nueva y bloquea datos del backend cuando hay errores.

Ejecutar:

```bash
python pruebas_prestamos.py
python ejecutar_pruebas.py
```

Resultado histórico de esta etapa: 68/68 pruebas nuevas. Las pruebas de
frontend verifican el contrato de nodos; las pruebas del generador validan y
ejecutan con Wasmtime las referencias que el backend admite.

## Corrección: receptores de patrones de match

Los receptores introducidos por patrones, incluso tuplas y variantes anidadas,
se consideran vivos dentro de su brazo. Pueden prestarse como otras variables
inmutables. Su préstamo no puede sobrevivir al brazo que declara el receptor.

El mapa prestamos conserva exactamente su formato. El simbolo_id de un préstamo
a un receptor es el ID existente de declaraciones[PatternContext], aunque tenga
el mismo nombre que una variable exterior. No cambia la gramática ni el backend.

Pruebas: `python pruebas_prestamos_match.py`. El generador admite préstamos
compartidos de receptores de patrones escalares y de variantes compatibles;
los demás receptores se rechazan controladamente.

## Accesos mediante referencias a valores compuestos

Se admite leer p.campo cuando p tiene tipo &T o &mut T. Se admite escribir
p.campo = valor y asignaciones compuestas únicamente mediante &mut T.
El binding de p no requiere mut: la capacidad de escritura proviene del préstamo.
También se admiten accesos de tupla e índices de arreglo por la misma regla.
Los préstamos siguen cubriendo la variable completa; no se crean préstamos
parciales y no se permite extraer un campo Move para transferir su propiedad.

### Representación en el backend

No cambia la gramática ni se agregan claves a analizar_programa.
PostfixContext conserva su PrimaryContext y los accesos existentes. Si el tipo
de la base es &T o &mut T y hay accesos, el generador debe aplicar esos accesos
al valor apuntado. El tipo de la base se conserva como referencia; el tipo del
PostfixContext y de cada acceso es el tipo del resultado.

En AssignmentContext con accesos, referencias[nodo] sigue identificando a p,
cuyo tipo en simbolos es &mut T. tipos_expresiones[nodo] es el tipo del campo
o elemento destino. Se debe escribir en la dirección apuntada más los
desplazamientos de acceso; no sustituir la dirección guardada en p.
Una asignación sin accesos p = ... continúa siendo reasignación del binding
y permanece limitada como se explicó antes. prestamos conserva su formato.

Ejemplo tomado del estilo oficial:

```rust
struct Punto { x: f64, y: f64 }
fn mover_x(p: &mut Punto, dx: f64) {
    p.x = p.x + dx;
}
fn main() -> f64 {
    let mut punto = Punto { x: 1.0, y: 2.0 };
    mover_x(&mut punto, 3.0);
    punto.x
}
```

El ejemplo genera WASM y devuelve `4.0` con Wasmtime. El backend también
admite accesos por referencia a tuplas, arreglos, matrices, estructuras,
enums y `String` dentro de los layouts recursivos admitidos. La
desreferenciación de un compuesto Copy materializa una copia profunda
independiente; la de un compuesto Move continúa rechazada para no extraer su
propiedad desde una referencia. Se mantienen rechazados los préstamos de
parámetros normales, los retornos y las reasignaciones de
referencias, además de représtamos y referencias anidadas definidos como
límites del frontend.
