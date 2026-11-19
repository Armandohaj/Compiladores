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
