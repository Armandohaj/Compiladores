# Suite del frontend: valor de la expresión final y retornos implícitos. Se analiza código y
# se comprueban diagnósticos o mapas; la ejecución WASM corresponde a las pruebas de
# integración.
"""Pruebas del frontend para bloques con valor y retornos implícitos."""
from main import analizar_programa


def ejecutar_pruebas():
    """Comprueba aceptación, diagnósticos y referencias de la expresión final."""
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    casos = [
        ('Retorno implícito entero', 'fn main()->i32{10}', None),
        ('Parámetro en retorno implícito', 'fn sumar(x:i32)->i32{x+1}', None),
        ('Variable local en retorno implícito', 'fn main()->i32{let x=10;x+1}', None),
        ('Retorno implícito incompatible', 'fn main()->bool{10}', 'Retorno implícito incompatible'),
        ('Función unit con valor final', 'fn main(){10}', 'Retorno implícito incompatible'),
        ('Bloque como inicializador', 'fn main()->i32{let x={let base=10;base+1};return x;}', None),
        ('Bloque en return', 'fn main()->i32{return {let base=10;base+1};}', None),
        ('Bloque como argumento', 'fn sumar(x:i32)->i32{x+1} fn main()->i32{sumar({let y=2;y})}', None),
        ('Bloque sin valor como inicializador', 'fn main(){let x={let y=1;};}', 'no devuelve un valor'),
        ('Variable del bloque fuera de ámbito', 'fn main()->i32{let x={let base=10;base};return base;}', 'no está declarada'),
        ('Expresión final no declarada', 'fn main()->i32{desconocida}', 'no está declarada'),
        ('Match como retorno implícito', 'fn main()->i32{match true{true=>{let x=10;x+1},false=>20}}', None),
        ('Brazos con tipos distintos', 'fn main()->i32{return match true{true=>{1},false=>{false}};}', 'Brazos de match incompatibles'),
        ('Inicialización en ambos brazos', 'fn main()->i32{let x:i32;let y=match true{true=>{x=1;0},false=>{x=2;0}};return x;}', None),
        ('Inicialización en un solo brazo', 'fn main()->i32{let x:i32;let y=match true{true=>{x=1;0},false=>0};return x;}', 'antes de inicializarla'),
        ('Un brazo no inicializa al otro', 'fn main()->i32{let x:i32;return match true{true=>{x=1;0},false=>x};}', 'antes de inicializarla'),
        ('Posible segunda asignación sin mut', 'fn main()->i32{let x:i32;let y=match true{true=>{x=1;0},false=>0};x=2;return x;}', 'no fue declarada con'),
        ('Asignación posterior con mut', 'fn main()->i32{let mut x:i32;let y=match true{true=>{x=1;0},false=>0};x=2;return x;}', None),
        ('Salida dentro de un bloque con valor', 'fn main()->i32{{print(1);2}+3}', None),
    ]
    correctas = 0
    for nombre, codigo, mensaje in casos:
        resultado = analizar_programa(codigo)
        if mensaje is None:
            cumple = resultado['valido']
        else:
            cumple = not resultado['valido'] and any(
                mensaje in error['mensaje'] for error in resultado['errores']
            )
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(resultado['errores'])
        correctas += cumple

    # La lectura final debe apuntar al símbolo del parámetro original.
    resultado = analizar_programa('fn sumar(x:i32)->i32{x+1}')
    ids = {i for i, s in resultado['simbolos'].items() if s['es_parametro']}
    cumple = bool(ids) and ids <= set(resultado['referencias'].values())
    correctas += cumple
    print(f'Referencia del retorno implícito: {"OK" if cumple else "FALLO"}')
    total = len(casos) + 1
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
