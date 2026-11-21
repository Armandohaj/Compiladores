"""Prueba salidas de brazos de match; no genera ni ejecuta WASM."""
from main import analizar_programa
from flujo_control import salidas_control


def ejecutar_pruebas():
    """Distingue brazos que producen valores de los que transfieren el control."""
    casos = [
        ('Return en un brazo', 'fn main()->i32{match true{true=>{return 1;},false=>2}}', None),
        ('Return en ambos brazos', 'fn main()->i32{match true{true=>{return 1;},false=>{return 2;}}}', None),
        ('Return exterior con return interior', 'fn main()->i32{return {return 1;};}', None),
        ('Retorno interno incompatible', 'fn main()->i32{match true{true=>{return false;},false=>2}}', 'Retorno incompatible'),
        ('Una rama retorna y otra inicializa', 'fn main()->i32{let x:i32;let y=match true{true=>{return 1;},false=>{x=2;0}};return x;}', None),
        ('Continuación sin inicializar', 'fn main()->i32{let x:i32;let y=match true{true=>{return 1;},false=>0};return x;}', 'antes de inicializarla'),
        ('Break en brazo dentro de while', 'fn main(){while true{let y=match true{true=>{break;},false=>1};}}', None),
        ('Continue en brazo dentro de while', 'fn main(){while true{let y=match true{true=>{continue;},false=>1};}}', None),
        ('Break fuera de ciclo', 'fn main(){let y=match true{true=>{break;},false=>1};}', 'solo puede usarse dentro de un ciclo'),
        ('Continue fuera de ciclo', 'fn main(){let y=match true{true=>{continue;},false=>1};}', 'solo puede usarse dentro de un ciclo'),
        ('Ciclo interior consume break', 'fn main()->i32{match true{true=>{loop{break;}},false=>1}}', 'Brazos de match incompatibles'),
        ('Return condicional conserva continuación', 'fn main()->i32{match true{true=>{if true{return 1;}},false=>1}}', 'Brazos de match incompatibles'),
        ('Cortocircuito puede omitir return', 'fn main()->bool{false && {return true;false}}', None),
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
    r = analizar_programa('fn main()->i32{match true{true=>{return 1;},false=>2}}')
    cumple = r['valido'] and salidas_control(r['arbol'].functionDecl(0).block()) == {'normal', 'return'}
    correctas += cumple
    print(f'Clasificación de salidas: {"OK" if cumple else "FALLO"}')
    total = len(casos) + 1
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
