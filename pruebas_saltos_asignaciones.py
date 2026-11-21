# Suite del frontend: destinos, valores y condiciones que no llegan a continuar normalmente.
# Se analiza código y se comprueban diagnósticos o mapas; la ejecución WASM corresponde a
# las pruebas de integración.
"""Comprueba saltos en asignaciones simples, compuestas y condiciones."""
from main import analizar_programa


def ejecutar_pruebas():
    """Verifica aceptación, diagnósticos y conservación de los ámbitos vigentes."""
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    casos = [
        ('Asignación simple con return', 'fn main()->i32{let mut x=0;x={return 7;};}', None),
        ('Primera asignación con return', 'fn main()->i32{let x:i32;x={return 7;};}', None),
        ('Sin escritura no exige mut', 'fn main()->i32{let x=0;x={return 7;};}', None),
        ('Compuesta con return', 'fn main()->i32{let mut x=0;x+={return 7;};}', None),
        ('Compuesta lee antes de inicializar', 'fn main()->i32{let mut x:i32;x+={return 7;};}', 'antes de inicializarla'),
        ('Destino inexistente', 'fn main()->i32{x={return 7;};}', 'no está declarada'),
        ('Tipo de return interior', 'fn main()->i32{let mut x=0;x={return false;};}', 'Retorno incompatible'),
        ('Unit normal sigue incompatible', 'fn main()->i32{let mut x=0;x={};return x;}', 'Tipos incompatibles'),
        ('Break en asignación', 'fn main(){let mut x=0;while true{x={break;};}}', None),
        ('Continue en asignación', 'fn main(){let mut x=0;while true{x={continue;};}}', None),
        ('If con condición que retorna', 'fn main()->i32{if {return 7;}{} }', None),
        ('While con condición que retorna', 'fn main()->i32{while {return 7;}{} }', None),
        ('If unit sin salto', 'fn main(){if {}{} }', 'La condición del if debe ser bool'),
        ('While unit sin salto', 'fn main(){while {}{} }', 'La condición del while debe ser bool'),
        ('Declaración tras if en inicializador', 'fn main()->i32{let x={if true{} 7};return x;}', None),
        ('Asignación tras if en RHS', 'fn main()->i32{let mut x:i32;x={if true{} 7};return x;}', None),
    ]
    correctas = 0
    for nombre, codigo, mensaje in casos:
        r = analizar_programa(codigo)
        cumple = r['valido'] if mensaje is None else (
            not r['valido'] and any(mensaje in e['mensaje'] for e in r['errores'])
        )
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(r['errores'])
        correctas += cumple
    print(f'Resultado: {correctas}/{len(casos)} pruebas OK')
    if correctas != len(casos):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
