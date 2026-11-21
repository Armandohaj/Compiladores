"""Propiedad de valores completos: Copy, Move, reinicialización y caminos."""
from main import analizar_programa


def ejecutar_pruebas():
    """Comprueba errores ubicados y que un rechazo vacíe el contrato del backend."""
    casos = [
        ('Copy entero conserva origen', 'fn main()->i32{let a=1;let b=a;a+b}', None),
        ('Move String una vez', 'fn main()->String{let a="hola";let b=a;b}', None),
        ('String después de mover', 'fn main()->String{let a="hola";let b=a;a}', 'después de mover'),
        ('Doble transferencia', 'fn main()->String{let a="hola";let b=a;let c=a;c}', 'después de mover'),
        ('Leer movida en comparación', 'fn main()->bool{let a="hola";let b=a;a=="hola"}', 'después de mover'),
        ('Comparación no consume String', 'fn main()->String{let a="hola";let b=a=="hola";a}', None),
        ('Reinicialización mutable', 'fn main()->String{let mut a="hola";let b=a;a="otra";a}', None),
        ('Reinicialización sin mut rechazada', 'fn main()->String{let a="hola";let b=a;a="otra";a}', 'no fue declarada con'),
        ('Asignación transfiere', 'fn main()->String{let a="hola";let mut b="otra";b=a;a}', 'después de mover'),
        ('Asignación Copy', 'fn main()->i32{let a=2;let mut b=0;b=a;a+b}', None),
        ('Sombreado conserva identidades', 'fn main()->String{let a="afuera";{let a="adentro";let b=a;}a}', None),
        ('Sombreado inicializador mueve origen', 'fn main()->String{let a="afuera";{let a=a;}a}', 'después de mover'),
        ('Parámetro por valor consume', 'fn usar(x:String){} fn main()->String{let a="hola";usar(a);a}', 'después de mover'),
        ('Resultado de función disponible', 'fn crear()->String{"hola"} fn main()->String{let a=crear();a}', None),
        ('Parámetro Copy reutilizable', 'fn usar(x:i32)->i32{x} fn main()->i32{let a=1;usar(a);a}', None),
        ('Dos argumentos mismo Move', 'fn usar(x:String,y:String){} fn main(){let a="hola";usar(a,a);}', 'después de mover'),
        ('Retorno de parámetro', 'fn devolver(x:String)->String{x}', None),
        ('Tupla Copy conserva origen', 'fn main()->(i32,bool){let a=(1,true);let b=a;a}', None),
        ('Tupla Move invalida origen', 'fn main()->(String,bool){let a=("hola",true);let b=a;a}', 'después de mover'),
        ('Arreglo Move invalida origen', 'fn main()->[String;1]{let a=["hola"];let b=a;a}', 'después de mover'),
        ('Estructura Copy conserva origen', 'struct P{x:i32} fn main()->P{let a=P{x:1};let b=a;a}', None),
        ('Estructura Move invalida origen', 'struct P{x:String} fn main()->P{let a=P{x:"hola"};let b=a;a}', 'después de mover'),
        ('Construir consume componente', 'fn main()->String{let a="hola";let b=(a,true);a}', 'después de mover'),
        ('Movimiento parcial rechazado', 'struct P{x:String} fn main()->String{let a=P{x:"hola"};a.x}', 'mover parcialmente'),
        ('Campo Copy de contenedor Move', 'struct P{x:String,n:i32} fn main()->i32{let a=P{x:"hola",n:1};let b=a.n;a.n}', None),
        ('Move en una rama', 'fn main()->String{let a="hola";if true{let b=a;}a}', 'después de mover'),
        ('Ramas exclusivas permiten consumir', 'fn main()->String{let a="hola";if true{return a;}else{return a;}}', None),
        ('Rama que retorna no contamina', 'fn main()->String{let a="hola";if true{return a;}a}', None),
        ('Reinicialización en ambas ramas', 'fn main()->String{let mut a="hola";let b=a;if true{a="x";}else{a="y";}a}', None),
        ('Match consume enum Move completo', 'enum E{A(String),B} fn main()->E{let a=E::A("hola");let b=match a{E::A(x)=>x,E::B=>""};a}', 'después de mover'),
        ('Capturas disponibles en brazo', 'enum E{A(String),B} fn main()->String{let a=E::A("hola");match a{E::A(x)=>x,E::B=>""}}', None),
        ('Move externo en ciclo repetible', 'fn usar(x:String){} fn main(){let a="hola";while true{usar(a);}}', 'después de mover'),
        ('Reinicializar en cada iteración', 'fn usar(x:String){} fn main(){let mut a="hola";while true{usar(a);a="otra";}}', None),
        ('Move seguido de break', 'fn usar(x:String){} fn main(){let a="hola";loop{usar(a);break;}}', None),
        ('Uso después de break que movió', 'fn usar(x:String){} fn main()->String{let a="hola";loop{usar(a);break;}a}', 'después de mover'),
        ('Continue repite Move', 'fn usar(x:String){} fn main(){let a="hola";loop{usar(a);continue;}}', 'después de mover'),
        ('Cortocircuito puede mover', 'fn usar(x:String)->bool{true} fn main()->String{let a="hola";let b=false&&usar(a);a}', 'después de mover'),
        ('Constante es valor por uso', 'const A:String="hola";fn main()->String{let b=A;A}', None),
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
    r = analizar_programa('fn main()->String{\nlet a="hola";\nlet b=a;\nreturn a;\n}')
    cumple = not r['valido'] and all(r[campo] == {} for campo in (
        'funciones','tipos_expresiones','simbolos','declaraciones','referencias',
        'estructuras','enumeraciones','llamadas_incorporadas',
    )) and r['arbol'] is None
    correctas += cumple
    print(f'Error de propiedad bloquea backend: {"OK" if cumple else "FALLO"}')
    cumple = any(e['fase']=='semantico' and e['linea']==4 and e['columna']==8 for e in r['errores'])
    correctas += cumple
    print(f'Ubicación del uso movido: {"OK" if cumple else "FALLO"}')
    total = len(casos)+2
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
