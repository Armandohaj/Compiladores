"""Prueba valores calculados de match constante, ámbitos y errores controlados."""
from main import analizar_programa


def ejecutar_pruebas():
    """Comprueba valores reales, no solo que el código sea aceptado."""
    validos = [
        ('Literal entero', 'const R:i32=match 1{1=>10,_=>20};', 10),
        ('Booleano', 'const R:i32=match false{true=>10,false=>20};', 20),
        ('Negativo', 'const R:i32=match -1{-1=>10,_=>20};', 10),
        ('Char', "const R:i32=match 'ñ'{'ñ'=>10,_=>20};", 10),
        ('String', 'const R:i32=match "hola"{"hola"=>10,_=>20};', 10),
        ('Decimal', 'const R:i32=match 1.5{1.5=>10,_=>20};', 10),
        ('Receptor', 'const R:i32=match 5{x=>x+1};', 6),
        ('Tupla', 'const R:i32=match (5,true){(x,true)=>x,(x,false)=>x+1};', 5),
        ('Enum con datos', 'enum E{A(i32),B} const R:i32=match E::A(5){E::A(x)=>x+1,E::B=>0};', 6),
        ('Patrón anidado', 'enum E{A((i32,bool)),B} const R:i32=match E::A((5,true)){E::A((x,_))=>x,E::B=>0};', 5),
        ('Referencia adelantada', 'const R:i32=match BASE{x=>x+1};const BASE:i32=5;', 6),
        ('Receptor oculta constante', 'const x:i32=99;const R:i32=match 5{x=>x+1};', 6),
        ('Receptor con nombre de su constante', 'const R:i32=match 5{R=>R+1};', 6),
        ('Let en bloque', 'const R:i32=match 5{x=>{let y=x+1;y*2}};', 12),
        ('Sombreado local', 'const R:i32=match 5{x=>{let x=x+1;x}};', 6),
        ('Inicializador usa constante antes del sombreado', 'const x:i32=5;const R:i32={let x=x+1;x};', 6),
        ('Match anidado', 'const R:i32=match true{true=>match 5{x=>x+1},false=>0};', 6),
        ('Solo evalúa brazo elegido', 'const R:i32=match true{true=>5,false=>1/0};', 5),
        ('Primer brazo compatible', 'const R:i32=match 5{_=>10,5=>20};', 10),
        ('Resultado compuesto', 'const R:(i32,bool)=match true{true=>(5,false),false=>(0,true)};', (5,False)),
    ]
    invalidos = [
        ('No exhaustivo', 'const R:i32=match true{true=>1};', 'no es exhaustivo'),
        ('Read prohibido', 'const R:i32=match true{true=>1,false=>read()};', 'llamada a función'),
        ('Print prohibido', 'const R:i32=match true{true=>1,false=>{print(1);0}};', 'llamada a función'),
        ('Ciclo entre constantes', 'const R:i32=match true{true=>1,false=>S};const S:i32=R;', 'Dependencia circular'),
        ('Captura fuera de ámbito', 'const R:i32=match 5{x=>x};const S:i32=x;', 'no está declarada'),
        ('Asignación prohibida', 'const R:i32={let x=1;x=2;x};', 'solo admite let inmutable'),
        ('Mut local prohibido', 'const R:i32={let mut x=1;x};', 'no admite variables locales mutables'),
        ('Return prohibido', 'const R:i32={return 1;};', 'solo admite let inmutable'),
        ('While prohibido', 'const R:i32={while false{} 1};', 'solo admite let inmutable'),
        ('Error en brazo elegido', 'const R:i32=match true{true=>1/0,false=>5};', 'cero'),
    ]
    correctas = 0
    for nombre, codigo, esperado in validos:
        r = analizar_programa(codigo)
        valores = {s['nombre']:s['valor'] for s in r['simbolos'].values() if s['es_constante']}
        cumple = r['valido'] and valores.get('R') == esperado
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(r['errores'], valores)
        correctas += cumple
    for nombre, codigo, mensaje in invalidos:
        r = analizar_programa(codigo)
        cumple = not r['valido'] and any(mensaje in e['mensaje'] for e in r['errores'])
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(r['errores'])
        correctas += cumple
    total = len(validos) + len(invalidos)
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
