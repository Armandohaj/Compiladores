# Guía para defender el frontend de RustiQ

Esta guía explica la gramática y el análisis del código. El frontend comprueba
programas y entrega información al generador WebAssembly. Las pruebas de análisis
no demuestran que el módulo WASM ya se genere y ejecute correctamente.

## Cómo explicar el recorrido de un programa

1. El lexer generado por ANTLR convierte texto en tokens: nombres, números,
   palabras reservadas y símbolos. Un carácter no reconocido produce un error léxico.
2. El parser comprueba cómo se combinan los tokens según RustiQ.g4 y construye
   el árbol ANTLR. Un return sin punto y coma produce un error sintáctico.
3. AnalizadorSemantico recorre ese árbol para comprobar nombres, ámbitos,
   tipos, inicialización, mutabilidad, llamadas, retornos y patrones.
4. ResolucionVariables vincula cada declaración con sus lecturas y asignaciones
   mediante identificadores únicos. Dos variables llamadas igual pueden tener
   identidades diferentes si pertenecen a ámbitos distintos.
5. analizar_programa entrega el árbol y los mapas semánticos al backend.
   Si encuentra errores, entrega arbol=None y mapas vacíos para impedir que
   se trate el programa como una compilación válida.

Una explicación breve: «Mi parte determina si el programa está bien escrito
y tiene sentido según las reglas del lenguaje. Además, registra los tipos y
las identidades de los símbolos para que el generador pueda producir WASM».

## Archivos que debo saber explicar

| Archivo | Responsabilidad |
|---|---|
| RustiQ.g4 | Tokens y reglas sintácticas del lenguaje |
| main.py | Coordina las fases mediante analizar_programa |
| analizador_semantico.py | Tipos, ámbitos, inicialización y validaciones |
| resolucion_variables.py | Identidades de símbolos y vínculos con sus usos |
| semantica_match.py | Patrones, brazos y comprobación de exhaustividad |
| flujo_control.py | Salidas posibles: normal, return, break y continue |
| gestor_constantes.py | Registro y dependencias de constantes globales |
| evaluador_constantes.py | Cálculo de sus valores durante la compilación |
| match_constante.py | Coincidencia de patrones y dependencias con ámbitos |
| generated/ | Archivos generados por ANTLR, que no se editan manualmente |

## Ejemplo válido 1 Funciones y retorno implícito

```rust
fn sumar(a: i32, b: i32) -> i32 {
    // Sin punto y coma: esta expresión es el retorno implícito.
    a + b
}

fn main() -> i32 {
    let resultado = sumar(10, 20);
    return resultado;
}
```

Explicar: se registran primero las firmas de las funciones. Después se validan
los argumentos, los tipos y el retorno. Los parámetros están inicializados
al entrar en la función. El resultado esperado al ejecutarlo es 30; aquí se
verificó su aceptación por el frontend, no su ejecución WASM.

## Ejemplo válido 2 Mutabilidad y ciclos

```rust
fn main() -> i32 {
    // mut permite modificar el contador después de inicializarlo.
    let mut contador: i32 = 0;
    while contador < 3 {
        contador += 1;
    }
    return contador;
}
```

Explicar: la comparación produce bool, el while exige bool y += lee el valor
anterior antes de actualizarlo. Una asignación compuesta no sirve para
inicializar una variable que todavía no tiene valor. El resultado esperado
al ejecutarlo es 3; la comprobación realizada aquí es de análisis.

## Ejemplo válido 3 Constantes y patrones con datos

```rust
struct Punto { valor: i32 }
enum Estado { Vacio, Listo((i32, bool)) }

const BASE: i32 = match true {
    true => {
        // Este let pertenece únicamente al bloque constante.
        let numero = 5;
        numero * 2
    },
    false => 0,
};

fn main() -> i32 {
    let punto = Punto { valor: BASE };
    let estado = Estado::Listo((punto.valor, true));
    match estado {
        Estado::Vacio => 0,
        // El patrón descompone una tupla; _ ignora su segundo componente.
        Estado::Listo((numero, _)) => numero,
    }
}
```

Explicar: BASE se calcula como 10 durante la compilación. Estado::Listo lleva
una tupla como dato asociado. El receptor numero existe solo en su brazo.
La exhaustividad comprueba que no queden variantes ni combinaciones de datos
sin cubrir. El backend recibe BASE ya calculada. El análisis de propiedad de
estos valores todavía está pendiente y no debe presentarse como implementado.

## Ejemplo válido 4 Entrada y salida reconocidas

```rust
fn main() -> i32 {
    // El frontend reconoce read como incorporada con retorno i32.
    let numero = read();
    // print exige exactamente un i32 y no devuelve valor.
    print(numero + 1);
    return 0;
}
```

Explicar: el analizador no pide datos ni imprime los valores del programa.
llamadas_incorporadas identifica las llamadas para que el backend genere las
importaciones acordadas env.read_i32 y env.print_i32. La ejecución necesita
que Armando implemente y pruebe esas importaciones en web y escritorio.

## Ejemplo inválido 1 Error léxico

```rust
fn main() -> i32 {
    return 1 @ + 2;
}
```

El lexer rechaza @. Aunque pueda continuar reconociendo el resto de los tokens,
el programa completo es inválido y no se entrega un árbol válido al backend.

## Ejemplo inválido 2 Error sintáctico

```rust
fn main() -> i32 {
    return 1
}
```

Falta el punto y coma de return. No se ejecuta el análisis semántico sobre
un árbol con errores léxicos o sintácticos.

## Ejemplo inválido 3 Error semántico

```rust
fn main() -> i32 {
    return true + 1;
}
```

La forma sintáctica es válida, pero + requiere números compatibles.
El diagnóstico conserva fase, mensaje, línea y columna desde 1.

## Cómo analizar uno de los ejemplos

Guardar el código elegido en ejemplo_defensa.rq, en la raíz del proyecto.
Con el entorno virtual activo, ejecutar desde esa misma carpeta:

```bash
python -c "from pathlib import Path; from main import analizar; analizar(Path('ejemplo_defensa.rq').read_text(encoding='utf-8'))"
```

Este comando muestra el resultado del análisis; no ejecuta el programa RustiQ.
python main.py analiza el ejemplo integrado en ese archivo: no recibe una ruta
como argumento en la versión actual.

Para las regresiones del frontend:

```bash
python ejecutar_pruebas.py
```

Último resultado verificado antes de preparar esta guía: 752/752 comprobaciones
en 31 suites. Los siete ejemplos anteriores se verificaron adicionalmente
sin modificar ese contador ni agregar otra suite.

## Preguntas habituales

¿Por qué usar un visitor? Porque ANTLR permite recorrer cada tipo de nodo
con un método específico. La gramática reconoce la forma; el visitor comprueba
las reglas de significado que no conviene expresar en la gramática.

¿Por qué un mapa de tipos? Para conservar el tipo de cada expresión y evitar
que el generador tenga que inferirlo otra vez.

¿Por qué declaraciones y referencias? El nombre por sí solo no distingue
variables sombreadas. Los identificadores únicos indican a qué declaración
se refiere cada lectura o escritura.

¿Por qué separar tipos y flujo? Una expresión puede tener un tipo registrado,
pero terminar mediante return, break o continue antes de entregar un valor.
El backend debe respetar ambas informaciones.

¿Por qué se revisan todos los brazos de match? Todos deben ser semánticamente
válidos. En una constante solo se calcula el brazo seleccionado, pero las
reglas de dependencias también detectan ciclos en brazos no seleccionados.

¿Qué significa que todas las pruebas pasen? Que los casos de las suites del
frontend dieron los resultados esperados. No garantiza ausencia de errores
fuera de esos casos ni sustituye la validación y ejecución de WASM.

## Pendientes que debo declarar

- Ownership y borrowing requieren acuerdo con Armando antes de implementar
  las reglas de copia, movimiento, referencias y duración de préstamos.
- No se detectan brazos redundantes de match.
- Los ciclos mantienen un análisis conservador: un ciclo por sí solo no
  garantiza retorno ni inicialización de variables externas al salir.
- Un bloque anidado como retorno implícito puede necesitar paréntesis,
  por ejemplo fn vacio() -> [i32; 0] { ({ [] }) }.
- Las constantes admiten bloques puros con let inmutable; no admiten llamadas,
  asignaciones, ciclos, saltos ni variables locales mutables.
- La revisión de combinaciones adicionales de flujo y expresiones sigue
  abierta. No afirmar que todos los casos posibles de saltos están resueltos.
- La integración, validación del binario y ejecución real WASM se comprueban
  junto con Armando. Los avances del frontend no sustituyen esas evidencias.
