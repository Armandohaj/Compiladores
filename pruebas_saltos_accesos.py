"""Pruebas del frontend para saltos en índices, bases y escrituras compuestas."""
from main import analizar_programa


def ejecutar_pruebas():
    """Conserva diagnósticos normales y no confunde un salto con un valor unit."""
    casos = [
        ('Lectura con return en índice', 'fn main()->i32{let a=[1,2];a[{return 7;}]}', None),
        ('Índice con retorno incorrecto', 'fn main()->i32{let a=[1,2];a[{return false;}]}', 'Retorno incompatible'),
        ('Índice unit sin salto', 'fn main()->i32{let a=[1,2];a[{}]}', 'debe ser i32'),
        ('Arreglo vacío con índice que retorna', 'fn main()->i32{let a:[i32;0]=[];a[{return 7;}]}', None),
        ('Base con return antes de indexar', 'fn main()->i32{({return 7;})[0]}', None),
        ('Base con return antes de campo', 'fn main()->i32{{return 7;}.edad}', None),
        ('Base con return antes de campo de tupla', 'fn main()->i32{{return 7;}.0}', None),
        ('Escritura con índice que retorna', 'fn main()->i32{let mut a=[1,2];a[{return 7;}]=1;}', None),
        ('Escritura con valor que retorna', 'fn main()->i32{let mut a=[1,2];a[0]={return 7;};}', None),
        ('Sin escritura no exige mut', 'fn main()->i32{let a=[1,2];a[0]={return 7;};}', None),
        ('Compuesta con salto', 'fn main()->i32{let mut a=[1,2];a[0]+={return 7;};}', None),
        ('Campo de tupla con salto', 'fn main()->i32{let mut a=(1,true);a.0={return 7;};}', None),
        ('Campo de estructura con salto', 'struct P{x:i32} fn main()->i32{let mut a=P{x:1};a.x={return 7;};}', None),
        ('Break en índice dentro de ciclo', 'fn main(){let a=[1];while true{let x=a[{break;}];}}', None),
        ('Continue en índice dentro de ciclo', 'fn main(){let a=[1];while true{let x=a[{continue;}];}}', None),
        ('Escritura normal conserva mutabilidad', 'fn main(){let a=[1];a[0]=2;}', 'no fue declarada con'),
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
