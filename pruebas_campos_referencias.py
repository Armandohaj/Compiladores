# Suite del frontend: lecturas y escrituras a campos o elementos mediante &T y &mut T. Se
# analiza código y se comprueban diagnósticos o mapas; la ejecución WASM corresponde a las
# pruebas de integración.
"""Accesos al valor apuntado: tipos, mutabilidad y contrato del frontend."""
from main import analizar_programa


def ejecutar_pruebas():
    """Revisa lecturas Copy y escrituras sin mover ni reemplazar referencias."""
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    prefijo = 'struct Punto{x:f64,y:f64} '
    casos = [
        ('Ejemplo oficial', prefijo+'fn mover_x(p:&mut Punto,dx:f64){p.x=p.x+dx;}', True),
        ('Lectura compartida', prefijo+'fn leer(p:&Punto)->f64{p.x}', True),
        ('Lectura exclusiva', prefijo+'fn leer(p:&mut Punto)->f64{p.x}', True),
        ('Asignación compuesta', prefijo+'fn mover(p:&mut Punto){p.x+=1.0;}', True),
        ('Campo anidado', 'struct A{x:i32} struct B{a:A} fn f(p:&mut B){p.a.x=2;}', True),
        ('Referencia a arreglo', 'fn f(p:&mut [i32;2])->i32{p[0]=2;p[0]}', True),
        ('Referencia a tupla', 'fn f(p:&mut (i32,bool))->i32{p.0+=2;p.0}', True),
        ('Préstamo local completo', prefijo+'fn main()->f64{let mut p=Punto{x:1.0,y:2.0};{let r=&mut p;r.x=3.0;}p.x}', True),
        ('Referencia compartida no escribe', prefijo+'fn f(p:&Punto){p.x=2.0;}', False),
        ('Binding mutable no vuelve exclusivo el préstamo', prefijo+'fn f(mut p:&Punto){p.x=2.0;}', False),
        ('Tipo de campo incorrecto', prefijo+'fn f(p:&mut Punto){p.x=true;}', False),
        ('Campo inexistente', prefijo+'fn f(p:&Punto)->f64{p.z}', False),
        ('Origen no accesible con préstamo exclusivo', prefijo+'fn main()->f64{let mut p=Punto{x:1.0,y:2.0};let r=&mut p;r.x=3.0;p.x}', False),
        ('Referencia movida', prefijo+'fn f(p:&mut Punto)->f64{let q=p;p.x}', False),
        ('No extrae campo Move', 'struct A{s:String} fn f(p:&A)->String{p.s}', False),
        ('Índice incorrecto', 'fn f(p:&[i32;2])->i32{p[true]}', False),
    ]
    resultados = []
    for nombre, codigo, valido in casos:
        r = analizar_programa(codigo)
        correcto = r['valido'] == valido
        if not valido:
            correcto = correcto and bool(r['errores']) and r['arbol'] is None and r['prestamos'] == {}
        resultados.append(correcto)
        print(f'{nombre}: {"OK" if correcto else "FALLO"}')
        if not correcto:
            print(r['errores'])
    # El símbolo del destino sigue siendo la referencia. El backend debe
    # distinguir p.x de p=... y aplicar el desplazamiento al valor apuntado.
    r = analizar_programa(prefijo+'fn f(p:&mut Punto){p.x=2.0;}')
    destinos = [n for n in r['referencias'] if type(n).__name__ == 'AssignmentContext']
    resultados.append(r['valido'] and len(destinos) == 1 and
        r['simbolos'][r['referencias'][destinos[0]]]['tipo'] == '&mut Punto' and
        r['tipos_expresiones'][destinos[0]] == 'f64')
    print(f'Resultado: {sum(resultados)}/{len(resultados)} pruebas OK')
    if not all(resultados):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
