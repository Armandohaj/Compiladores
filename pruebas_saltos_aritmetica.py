"""Regresión de saltos en operandos aritméticos y unarios del frontend."""
from main import analizar_programa


def ejecutar_pruebas():
    """Un salto no produce un valor numérico; un bloque unit normal sí es error."""
    casos = [
        ('Return a la derecha de suma', 'fn main()->i32{return 1+{return 7;};}', None),
        ('Return a la izquierda de suma', 'fn main()->i32{{return 7;}+1}', None),
        ('Return en multiplicación', 'fn main()->i32{2*{return 7;}}', None),
        ('Return en división', 'fn main()->i32{10/{return 7;}}', None),
        ('Return en residuo', 'fn main()->i32{10%{return 7;}}', None),
        ('Return en signo negativo', 'fn main()->i32{-{return 7;}}', None),
        ('Return en negación lógica', 'fn main()->bool{!{return true;}}', None),
        ('Retorno interior conserva su tipo', 'fn main()->i32{1+{return false;}}', 'Retorno incompatible'),
        ('Bloque unit normal no es número', 'fn main()->i32{1+{print(1);}}', 'requiere números'),
        ('Break aritmético en brazo de match', 'fn main(){while true{let x=match true{true=>1+{break;},false=>2};}}', None),
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
