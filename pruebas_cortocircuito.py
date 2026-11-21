"""Verifica inicialización conservadora al omitir operandos lógicos."""
from main import analizar_programa


def ejecutar_pruebas():
    """No ejecuta RustiQ; comprueba aceptación y diagnósticos del frontend."""
    casos = [
        ('AND puede omitir asignación', 'fn main()->i32{let x:i32;let b=false && {x=10;true};return x;}', 'antes de inicializarla'),
        ('OR puede omitir asignación', 'fn main()->i32{let x:i32;let b=true || {x=10;false};return x;}', 'antes de inicializarla'),
        ('Primer operando sí inicializa', 'fn main()->i32{let x:i32;let b={x=10;true} && false;return x;}', None),
        ('Variable previamente inicializada', 'fn main()->i32{let mut x=1;let b=false && {x=10;true};return x;}', None),
        ('Posible segunda asignación sin mut', 'fn main()->i32{let x:i32;let b=false && {x=10;true};x=2;return x;}', 'no fue declarada con'),
        ('Asignación posterior con mut', 'fn main()->i32{let mut x:i32;let b=false && {x=10;true};x=2;return x;}', None),
        ('Operando omitido también se valida', 'fn main()->bool{false && desconocida}', 'no está declarada'),
        ('Se conserva declaración del resultado', 'fn main()->bool{let b=true || false;b}', None),
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
