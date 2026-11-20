"""Préstamos de receptores de match: ámbitos e identidades del frontend."""
from main import analizar_programa


def ejecutar_pruebas():
    """Acepta préstamos locales y rechaza referencias que sobreviven al receptor."""
    casos = [
        ('Receptor entero', 'fn main()->i32{match 1{x=>{let r=&x;*r}}}', True),
        ('Receptor bool', 'fn main()->bool{match true{x=>{let r=&x;*r}}}', True),
        ('Receptor String sin mover por lectura', 'fn main()->bool{match "hola"{s=>{let r=&s;*r=="hola"}}}', True),
        ('Receptores de tupla', 'fn main()->i32{match (1,2){(a,b)=>{let r=&a;let s=&b;*r+*s}}}', True),
        ('Receptor de variante', 'enum E{A(i32)} fn main()->i32{match E::A(3){E::A(x)=>{let r=&x;*r}}}', True),
        ('Patrón anidado', 'enum E{A((i32,bool))} fn main()->i32{match E::A((3,true)){E::A((x,b))=>{let r=&x;*r}}}', True),
        ('Nombre sombreado', 'fn main()->i32{let x=9;let y=match 1{x=>{let r=&x;*r}};x+y}', True),
        ('Préstamo exterior termina en cada brazo', 'fn main()->i32{let mut x=1;let y=match true{true=>{let r=&mut x;*r=2;*r},false=>{let r=&mut x;*r=3;*r}};x+y}', True),
        ('Referencia a origen exterior como resultado', 'fn main()->i32{let x=1;let r=match true{true=>&x,false=>&x};*r}', True),
        ('Préstamo directo de receptor escapa', 'fn main()->i32{let r=match 1{x=>&x};*r}', False),
        ('Préstamo de receptor escapa por bloque', 'fn main()->i32{let r=match 1{x=>{&x}};*r}', False),
        ('Receptor es inmutable', 'fn main(){let r=match 1{x=>{let r=&mut x;*r}};}', False),
    ]
    resultados = []
    for nombre, codigo, esperado in casos:
        resultado = analizar_programa(codigo)
        # Para los rechazos también debe preservarse el contrato de error:
        # el backend no recibe préstamos ni un árbol de un programa inválido.
        correcto = resultado['valido'] == esperado
        if not esperado:
            correcto = correcto and resultado['arbol'] is None and resultado['prestamos'] == {}
            mensaje = 'requiere una variable declarada con mut' if nombre == 'Receptor es inmutable' else 'sobrevivir'
            correcto = correcto and any(mensaje in e['mensaje'] for e in resultado['errores'])
        resultados.append(correcto)
        print(f'{nombre}: {"OK" if correcto else "FALLO"}')
        if not correcto:
            print(resultado['errores'])

    # El mapa debe identificar al receptor del patrón, no a la variable exterior
    # que tiene el mismo nombre. Esto permite al backend reservar el origen real.
    resultado = analizar_programa('fn main()->i32{let x=9;match 1{x=>{let r=&x;*r}}}')
    receptores = {i for nodo, i in resultado['declaraciones'].items() if type(nodo).__name__ == 'PatternContext'}
    resultados.append(resultado['valido'] and len(resultado['prestamos']) == 1 and
                      all(p['simbolo_id'] in receptores for p in resultado['prestamos'].values()))
    print(f'Resultado: {sum(resultados)}/{len(resultados)} pruebas OK')
    if not all(resultados):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
