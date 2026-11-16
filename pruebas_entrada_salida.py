"""Valida el contrato del frontend; no ejecuta E/S ni WebAssembly."""
from contextlib import redirect_stdout
from io import StringIO
from main import analizar_programa


def ejecutar_pruebas():
    """Comprueba aceptación, diagnósticos y nodos entregados al backend."""
    validos = [
        'fn main()->i32 { return read(); }',
        'fn main()->i32 { return read()+2; }',
        'fn main() { print(10); }',
        'fn main() { let x=read(); print(x); print(read()); }',
        'fn leer()->i32 { return read(); } fn main() { print(leer()); }',
        'fn main() { if true { print(read()); } else { print(0); } }',
        'fn main() { while false { print(read()); } }',
        'fn main() { loop { print(1); break; } }',
    ]
    invalidos = [
        ('fn main(){ read(1); }', 'espera 0 argumentos'),
        ('fn main(){ print(); }', 'espera 1 argumentos'),
        ('fn main(){ print(1,2); }', 'espera 1 argumentos'),
        ('fn main(){ print(true); }', 'se esperaba i32'),
        ('fn main(){ print(1.0); }', 'se esperaba i32'),
        ('fn main(){ print("hola"); }', 'se esperaba i32'),
        ('fn main(){ let x=print(1); }', 'unit'),
        ('fn main()->i32 { return print(1); }', 'unit'),
        ('fn main(){ print(print(1)); }', 'unit'),
        ('fn main(){ let x=print(1)==print(2); }', 'unit'),
        ('fn main(){ return print(1); }', 'unit'),
        ('const X:i32=read();', 'constante'),
        ('const X:i32=print(1);', 'constante'),
        ('fn read()->i32{return 1;}', 'reservado'),
        ('fn print(x:i32){}', 'reservado'),
        ('fn main(){let read=1;}', 'reservado'),
        ('fn main(){ {let mut print=1;} }', 'reservado'),
        ('fn f(read:i32){}', 'reservado'),
        ('fn f(mut print:i32){}', 'reservado'),
        ('const read:i32=1;', 'reservado'),
        ('const print:i32=1;', 'reservado'),
    ]
    comprobaciones = []
    for codigo in validos:
        salida = StringIO()
        with redirect_stdout(salida):
            resultado = analizar_programa(codigo)
        comprobaciones.append(resultado['valido'] and not salida.getvalue())
    for codigo, mensaje in invalidos:
        resultado = analizar_programa(codigo)
        comprobaciones.append(
            not resultado['valido'] and resultado['llamadas_incorporadas'] == {}
            and any(mensaje in e['mensaje'] for e in resultado['errores'])
        )
    resultado = analizar_programa('fn main(){ print(read()); }')
    llamadas = resultado['llamadas_incorporadas']
    comprobaciones.append(sorted(llamadas.values()) == ['print', 'read'])
    comprobaciones.append(all(n.IDENT().getText() == nombre for n, nombre in llamadas.items()))
    comprobaciones.append(all(resultado['tipos_expresiones'][n] == ('i32' if nombre == 'read' else 'unit') for n, nombre in llamadas.items()))
    comprobaciones.append(set(resultado['funciones']) == {'main'})
    comprobaciones.append(analizar_programa('fn otra(){}')['llamadas_incorporadas'] == {})
    error = analizar_programa('fn main(){\n    print(true);\n}')['errores'][0]
    comprobaciones.append((error['fase'], error['linea'], error['columna']) == ('semantico', 2, 11))
    comprobaciones.append(analizar_programa('fn main(){print(;}')['llamadas_incorporadas'] == {})
    for numero, cumple in enumerate(comprobaciones, 1):
        print(f'Comprobación {numero}: {"OK" if cumple else "FALLO"}')
    correctas = sum(comprobaciones)
    print(f'Resultado: {correctas}/{len(comprobaciones)} pruebas OK')
    if correctas != len(comprobaciones):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
