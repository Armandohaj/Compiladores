# Suite del frontend: constructores que no se completan por return, break o continue. Se
# analiza código y se comprueban diagnósticos o mapas; la ejecución WASM corresponde a las
# pruebas de integración.
"""Regresión del frontend para saltos dentro de constructores compuestos."""
from main import analizar_programa


def ejecutar_pruebas():
    """Distingue elementos que entregan valores de los que transfieren control."""
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    casos = [
        ('Arreglo con return', 'fn main()->i32{let a=[1,{return 7;}];}', None),
        ('Arreglo que empieza con return', 'fn main()->i32{let a=[{return 7;},1];}', None),
        ('Arreglo sin elemento inferible', 'fn main()->i32{let a=[{return 7;}];}', None),
        ('Arreglo anotado con return', 'fn main()->i32{let a:[bool;2]=[true,{return 7;}];}', None),
        ('Arreglo con retorno interior incorrecto', 'fn main()->i32{let a=[1,{return false;}];}', 'Retorno incompatible'),
        ('Arreglo unit normal', 'fn main(){let a=[{}];}', 'no puede contener valores unit'),
        ('Tupla con return', 'fn main()->i32{let a=(1,{return 7;});}', None),
        ('Tupla anotada con return', 'fn main()->i32{let a:(bool,String)=(true,{return 7;});}', None),
        ('Tupla unit normal', 'fn main(){let a=(1,{});}', 'no puede contener valores unit'),
        ('Estructura con return', 'struct P{x:i32} fn main()->i32{let a=P{x:{return 7;}};}', None),
        ('Estructura con campo faltante', 'struct P{x:i32,y:i32} fn main()->i32{let a=P{x:{return 7;}};}', 'Falta el campo'),
        ('Estructura con campo inexistente', 'struct P{x:i32} fn main()->i32{let a=P{y:{return 7;}};}', 'no tiene el campo'),
        ('Estructura con campo repetido', 'struct P{x:i32} fn main()->i32{let a=P{x:{return 7;},x:1};}', 'está repetido'),
        ('Enum con return', 'enum E{A(bool)} fn main()->i32{let a=E::A({return 7;});}', None),
        ('Enum con aridad incorrecta', 'enum E{A(bool,i32)} fn main()->i32{let a=E::A({return 7;});}', 'espera 2 argumentos'),
        ('Enum con variante inexistente', 'enum E{A(bool)} fn main()->i32{let a=E::B({return 7;});}', 'no tiene la variante'),
        ('Constructor anidado', 'struct P{x:i32} enum E{A(P)} fn main()->i32{let a=(true,[E::A(P{x:{return 7;}})]);}', None),
        ('Break en arreglo dentro de ciclo', 'fn main(){while true{let a=[1,{break;}];}}', None),
        ('Continue en tupla dentro de ciclo', 'fn main(){while true{let a=(1,{continue;});}}', None),
        ('Error interno se conserva', 'fn main()->i32{let a=[1,{return desconocida;}];}', 'no está declarada'),
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
