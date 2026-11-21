# Suite del frontend: pureza del inicializador, ámbito y sombreado de const locales. Se
# analiza código y se comprueban diagnósticos o mapas; la ejecución WASM corresponde a las
# pruebas de integración.
"""Constantes locales evaluadas al compilar: ámbitos, pureza y contrato."""
from main import analizar_programa


def ejecutar_pruebas():
    """Incluye casos negativos: aceptar una constante no equivale a ejecutar WASM."""
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    casos = [
        ('Entero', 'fn main()->i32{const N:i32=10;N}', True),
        ('Dependencia local', 'fn main()->i32{const A:i32=2;const B:i32=A+3;B}', True),
        ('Dependencia global', 'const A:i32=2;fn main()->i32{const B:i32=A+3;B}', True),
        ('Sombreado en bloque', 'fn main()->i32{const A:i32=2;let b={const A:i32=3;A};A+b}', True),
        ('Mismo nombre en funciones diferentes', 'fn f()->i32{const N:i32=1;N} fn main()->i32{const N:i32=2;N+f()}', True),
        ('Arreglo', 'fn main()->i32{const A:[i32;2]=[2,3];A[0]}', True),
        ('Tupla', 'fn main()->i32{const A:(i32,bool)=(2,true);A.0}', True),
        ('Match constante', 'fn main()->i32{const N:i32=match true{true=>2,false=>3};N}', True),
        ('Bloque puro', 'fn main()->i32{const N:i32={let x=2;x+1};N}', True),
        ('String materializado por uso', 'fn main()->String{const S:String="hola";let x=S;S}', True),
        ('Tipo incorrecto', 'fn main(){const N:i32=true;}', False),
        ('Duplicada', 'fn main(){const N:i32=1;const N:i32=2;}', False),
        ('Conflicto con parámetro', 'fn f(N:i32){const N:i32=1;}', False),
        ('No depende de let', 'fn main(){let x=2;const N:i32=x;}', False),
        ('No depende de parámetro', 'fn f(x:i32){const N:i32=x;}', False),
        ('No lee variable en rama omitida', 'fn f(x:bool){const B:bool=true||x;}', False),
        ('Llamada read', 'fn main(){const N:i32=read();}', False),
        ('Función normal', 'fn f()->i32{1} fn main(){const N:i32=f();}', False),
        ('No reasignable', 'fn main(){const N:i32=1;N=2;}', False),
        ('Fuera de ámbito', 'fn main()->i32{{const N:i32=1;}N}', False),
        ('Sin adelantamiento local', 'fn main(){const A:i32=B;const B:i32=2;}', False),
        ('Nombre protegido', 'fn main(){const read:i32=1;}', False),
        ('Sin tipo', 'fn main(){const N=1;}', False),
        ('División por cero', 'fn main(){const N:i32=1/0;}', False),
        ('Sombreado de global por variable', 'const X:i32=1;fn main(){let X=2;const N:i32=X;}', False),
        ('No presta constante local', 'fn main(){const N:i32=1;let r=&N;}', False),
    ]
    resultados = []
    for nombre, codigo, valido in casos:
        r = analizar_programa(codigo)
        correcto = r['valido'] == valido
        if not valido:
            correcto = correcto and bool(r['errores']) and r['arbol'] is None and r['prestamos']=={}
        resultados.append(correcto)
        print(f'{nombre}: {"OK" if correcto else "FALLO"}')
        if not correcto:
            print(r['errores'])
    r = analizar_programa('fn main()->i32{const N:i32=2+3;N}')
    simbolos = [s for s in r['simbolos'].values() if s['nombre']=='N']
    resultados.append(len(simbolos)==1 and simbolos[0]['valor']==5 and simbolos[0]['es_constante'] and simbolos[0]['funcion']=='main')
    resultados.append(any(type(n).__name__=='ConstLocalDeclContext' for n in r['declaraciones']))
    print(f'Resultado: {sum(resultados)}/{len(resultados)} pruebas OK')
    if not all(resultados):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
