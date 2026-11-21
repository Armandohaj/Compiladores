"""Regresión del frontend: saltos en argumentos e inicializadores let."""
from main import analizar_programa


def ejecutar_pruebas():
    """Verifica tipos, firmas, errores y ausencia de declaraciones no alcanzadas."""
    prefijo = 'fn identidad(x:i32)->i32{x} '
    casos = [
        ('Return en argumento', prefijo+'fn main()->i32{identidad({return 7;})}', None),
        ('Return en argumento de print', 'fn main()->i32{print({return 7;});}', None),
        ('Retorno interior incompatible', prefijo+'fn main()->i32{identidad({return false;})}', 'Retorno incompatible'),
        ('Argumento unit sin salto', prefijo+'fn main()->i32{identidad({})}', 'se esperaba i32'),
        ('Función inexistente se rechaza', 'fn main()->i32{inexistente({return 7;})}', 'no está declarada'),
        ('Aridad incorrecta se rechaza', prefijo+'fn main()->i32{identidad({return 7;},2)}', 'espera 1 argumentos'),
        ('Let inferido que retorna', 'fn main()->i32{let x={return 7;};}', None),
        ('Let anotado que retorna', 'fn main()->i32{let x:bool={return 7;};}', None),
        ('Let mutable que retorna', 'fn main()->i32{let mut x={return 7;};}', None),
        ('Let con llamada que retorna al evaluar argumento', prefijo+'fn main()->i32{let x=identidad({return 7;});}', None),
        ('Break en argumento dentro de ciclo', prefijo+'fn main(){while true{identidad({break;});}}', None),
        ('Continue en argumento dentro de ciclo', prefijo+'fn main(){while true{identidad({continue;});}}', None),
        ('Break en inicializador dentro de ciclo', 'fn main(){while true{let x={break;};}}', None),
        ('Continue en inicializador dentro de ciclo', 'fn main(){while true{let x={continue;};}}', None),
        ('Break fuera de ciclo', 'fn main(){let x={break;};}', 'solo puede usarse dentro de un ciclo'),
        ('Let unit normal sigue inválido', 'fn main(){let x={};}', 'no devuelve un valor'),
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
    r = analizar_programa('fn main()->i32{let x={return 7;};}')
    cumple = r['valido'] and not r['simbolos'] and not r['declaraciones']
    correctas += cumple
    print(f'Declaración no alcanzada sin símbolo: {"OK" if cumple else "FALLO"}')
    r = analizar_programa(prefijo+'fn main()->i32{identidad({return 7;})}')
    cumple = r['valido'] and r['funciones']['identidad'] == {'parametros':['i32'], 'retorno':'i32'}
    correctas += cumple
    print(f'Firma del usuario conservada: {"OK" if cumple else "FALLO"}')
    total = len(casos) + 2
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
