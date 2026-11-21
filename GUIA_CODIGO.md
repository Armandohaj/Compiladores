# Cómo leer el compilador RustiQ

Esta guía acompaña a los comentarios del código. Los ejemplos describen
el frontend implementado; la generación y ejecución Wasm son otra etapa.

## Orden recomendado de lectura

| Archivo | Qué explica |
|---|---|
| `RustiQ.g4` | Qué formas de texto admite el lenguaje y la prioridad de operadores. |
| `main.py` | Cómo se conectan las fases y qué devuelve el analizador. |
| `analizador_semantico.py` | Tipos, declaraciones, ámbitos, mutabilidad e inicialización. |
| `gestor_estructuras.py` | Registro de estructuras y validación de sus campos y tipos. |
| `gestor_constantes.py` | Referencias adelantadas, dependencias y valores constantes. |
| `evaluador_constantes.py` | Cómo calcular valores constantes sin ejecutar funciones RustiQ. |
| `tipos_compuestos.py` | Representación de arreglos y tuplas y orden de los accesos. |
| `resolucion_variables.py` | Cómo vincular un uso con la declaración correcta. |
| `ejecutar_pruebas.py` | Cómo ejecutar todas las suites y detectar fallos. |

## Qué significa `ctx`

ANTLR convierte el texto en un árbol. Cada regla de la gramática crea
un tipo de nodo. `ctx` es el nodo que está visitando un método.

Por ejemplo, en `visitFunctionDecl(ctx)`, `ctx.IDENT()` representa el nombre
de la función y `ctx.block()` representa su cuerpo. `self.visit(nodo)`
continúa el recorrido con el método correspondiente a ese nodo.

El semántico devuelve nombres de tipos, como `i32`, `(i32,bool)` o `Persona`.
El evaluador de constantes devuelve valores, como `10`, `(10, True)` o
un diccionario de estructura. Son recorridos distintos del mismo árbol.

## Variables y ámbitos

Un ámbito es un diccionario de nombres visibles. La pila de ámbitos permite
buscar primero en el bloque más interior. Al salir de un bloque, se retiran
sus declaraciones. Por eso dos bloques pueden tener variables del mismo nombre.

Cada variable registra su tipo, si admite cambios y si ya recibió un valor.
`inicializada` significa que tiene valor en todos los caminos que llegan al uso.
`puede_inicializada` significa que ya pudo recibir valor en alguno de esos caminos.
La diferencia evita permitir una segunda asignación accidental a una variable sin `mut`.

Al analizar `if`, se copian los estados antes de estudiar cada rama.
Después se combinan los caminos que continúan. Este análisis sigue siendo
conservador en ciclos y saltos: todavía no modela todos los caminos posibles.

## Tipos y valores

`None` como resultado de tipo indica que un nodo ya falló; no es el tipo
`unit`. `unit` significa que una función no devuelve valor.

Los arreglos conservan tipo de elemento y tamaño. Las tuplas conservan un
tipo por posición. Una estructura es nominal: dos estructuras de distinto
nombre son tipos diferentes aunque tengan los mismos campos.

Un arreglo vacío necesita contexto, por ejemplo `let a: [i32;0] = [];`.
El tipo también puede venir de un parámetro, un retorno o un campo de estructura.

## Constantes

Se registran sus nombres y tipos antes de calcular valores. Esto permite
que una constante use otra declarada más abajo. Una caché evita calcular
varias veces el mismo valor. El conjunto `en_proceso` detecta ciclos.

El evaluador visita todos los elementos de arreglos, tuplas y estructuras.
Para `&&` y `||` respeta el cortocircuito al calcular valores, aunque el
semántico comprueba los tipos de todos los operandos.

## Qué recibe el backend

`analizar_programa(codigo)` devuelve un diccionario. Si el programa es
inválido, entrega errores y deja vacíos los mapas destinados al backend.

- `arbol`: árbol original de ANTLR.
- `funciones`: tipos de parámetros y retorno por nombre.
- `estructuras`: tipos de campos por nombre de estructura.
- `tipos_expresiones`: nodo -> tipo calculado.
- `simbolos`: ID de declaración -> información de variable o constante.
- `declaraciones`: nodo de declaración -> ID.
- `referencias`: nodo de lectura o asignación -> ID de su declaración.

Los identificadores numéricos distinguen declaraciones del mismo nombre.
Los nodos son claves dentro de Python; el árbol y esos mapas no se envían
directamente como JSON al navegador. Los errores sí son serializables.

## Cómo interpretar las pruebas

Un caso inválido debe producir el error esperado: eso cuenta como prueba
correcta. Un error de sintaxis no debe confundirse con el error semántico
que quería comprobar la prueba. Las suites comparan fases y mensajes,
valores constantes y referencias de símbolos.

`python ejecutar_pruebas.py` ejecuta cada archivo `pruebas_*.py` por separado
usando el mismo Python con el que se lanzó el comando.

Los archivos de `generated/` se regeneran desde la gramática. Las
explicaciones se mantienen en los archivos escritos a mano para que no
se pierdan al volver a generar el parser.

## Qué sigue pendiente

Enumeraciones, `match`, ownership, movimientos, préstamos y revisión final
de caminos de control e integración. También hacen falta las pruebas del
backend y de ejecución Wasm. Una colección grande de pruebas de frontend
no equivale a haber completado todos los requisitos del proyecto.
