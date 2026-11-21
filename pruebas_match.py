"""Pruebas del frontend para match; no ejecutan WebAssembly."""
from main import analizar_programa


def ejecutar_pruebas():
    """Incluye cobertura de datos anidados, ámbitos y contrato de símbolos."""
    casos = [
        ('literal', 'fn main()->i32{return match 2 {0=>10,_=>20};}', True),
        ('bool completo', 'fn main()->i32{return match true {true=>1,false=>2};}', True),
        ('bool incompleto', 'fn main()->i32{return match true {true=>1};}', False),
        ('receptor', 'fn main()->i32{return match 2 {x=>x+1};}', True),
        ('sombreado', 'fn main()->i32{let x=2;let y=match 3{x=>x};return x+y;}', True),
        ('fuera de ámbito', 'fn main()->i32{let y=match 3{x=>x};return x;}', False),
        ('tipos de brazos', 'fn main()->i32{return match 2{0=>true,_=>2};}', False),
        ('tipo de patrón', 'fn main()->i32{return match 2{true=>1,_=>2};}', False),
        ('sin comodín entero', 'fn main()->i32{return match 2{0=>1,1=>2};}', False),
        ('negativo', 'fn main()->i32{return match -1{-1=>1,_=>0};}', True),
        ('rango i32', 'fn main()->i32{return match 1{2147483648=>1,_=>0};}', False),
        ('tupla', 'fn main()->i32{return match (1,true){(x,_)=>x};}', True),
        ('tupla incorrecta', 'fn main()->i32{return match (1,true){(x,y,z)=>1};}', False),
        ('tupla restrictiva', 'fn main()->i32{return match (1,true){(0,_)=>1};}', False),
        ('tupla bool cubierta', 'fn main()->i32{return match (true,false){(true,_)=>1,(false,_)=>0};}', True),
        ('nombre repetido', 'fn main()->i32{return match (1,2){(x,x)=>x};}', False),
        ('read protegido', 'fn main()->i32{return match 1{read=>read};}', False),
        ('print protegido', 'fn main()->i32{return match 1{print=>print};}', False),
        ('Match constante válido', 'const X:i32=match 1{_=>2};', True),
        ('match anidado', 'fn main()->i32{return match true{true=>match 1{x=>x},false=>0};}', True),
        ('retorno incompatible', 'fn main()->bool{return match 1{_=>2};}', False),
        ('entrada salida', 'fn main(){print(match read(){0=>1,x=>x});}', True),
        ('falta flecha', 'fn main()->i32{return match 1{_ 2};}', False),
    ]
    enum = 'enum E {A, B(bool), C(i32)} '
    casos += [
        ('enum completo', enum+'fn main()->i32{return match E::A{E::A=>0,E::B(x)=>1,E::C(y)=>y};}', True),
        ('enum incompleto', enum+'fn main()->i32{return match E::A{E::A=>0};}', False),
        ('dato restrictivo', enum+'fn main()->i32{return match E::A{E::A=>0,E::B(true)=>1,E::C(_)=>2};}', False),
        ('dato bool cubierto', enum+'fn main()->i32{return match E::A{E::A=>0,E::B(true)=>1,E::B(false)=>2,E::C(_)=>3};}', True),
        ('falta dato', enum+'fn main()->i32{return match E::A{E::B=>1,_=>0};}', False),
        ('variante desconocida', enum+'fn main()->i32{return match E::A{E::Z=>1,_=>0};}', False),
        ('dato incompatible', enum+'fn main()->i32{return match E::A{E::B(2)=>1,_=>0};}', False),
        ('unit con paréntesis', enum+'fn main()->i32{return match E::A{E::A(x)=>1,_=>0};}', False),
    ]
    correctas = 0
    for nombre, codigo, esperado in casos:
        resultado = analizar_programa(codigo)
        cumple = resultado['valido'] == esperado
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(resultado['errores'])
        correctas += cumple
    # Un receptor debe quedar vinculado a su lectura, con el tipo calculado.
    r = analizar_programa('fn main()->i32{return match 10{x=>x};}')
    receptores = [n for n in r['declaraciones'] if type(n).__name__ == 'PatternContext']
    cumple = (len(receptores) == 1 and r['tipos_expresiones'][receptores[0]] == 'i32'
              and r['declaraciones'][receptores[0]] in r['referencias'].values())
    correctas += cumple
    total = len(casos)+1
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
