"""Primera versión de borrowing léxico: no ejecuta memoria ni WebAssembly."""
from main import analizar_programa
from generated.RustiQParser import RustiQParser as P
from clasificacion_propiedad import clasificar_tipo


def ejecutar_pruebas():
    """Comprueba préstamos, desreferenciación, vidas útiles y contrato de nodos."""
    validos = [
        ('Préstamo compartido', 'fn main()->i32{let x=1;let r=&x;*r}'),
        ('Dos préstamos compartidos', 'fn main()->i32{let x=1;let r=&x;let s=&x;*r+*s}'),
        ('Compartido permite leer Copy original', 'fn main()->i32{let x=1;let r=&x;x+*r}'),
        ('Anotación &i32', 'fn main()->i32{let x=1;let r:&i32=&x;*r}'),
        ('Escritura exclusiva', 'fn main()->i32{let mut x=1;{let r=&mut x;*r=2;}x}'),
        ('Asignación compuesta por referencia', 'fn main()->i32{let mut x=1;{let r=&mut x;*r+=2;}x}'),
        ('Binding de referencia no exige mut', 'fn main()->i32{let mut x=1;let r=&mut x;*r=2;*r}'),
        ('Libera préstamo al salir del bloque', 'fn main()->i32{let mut x=1;{let r=&x;print(*r);}x=2;x}'),
        ('Préstamos exclusivos en bloques sucesivos', 'fn main()->i32{let mut x=1;{let r=&mut x;*r=2;}{let r=&mut x;*r=3;}x}'),
        ('Copia de referencia compartida', 'fn main()->i32{let x=1;let r=&x;let s=r;*r+*s}'),
        ('Transferencia de referencia exclusiva', 'fn main()->i32{let mut x=1;let r=&mut x;let s=r;*s=2;*s}'),
        ('Parámetro compartido', 'fn leer(r:&i32)->i32{*r} fn main()->i32{let x=1;leer(&x)}'),
        ('Parámetro exclusivo', 'fn inc(r:&mut i32){*r+=1;} fn main()->i32{let mut x=1;inc(&mut x);x}'),
        ('Dos parámetros compartidos del mismo origen', 'fn suma(a:&i32,b:&i32)->i32{*a+*b} fn main()->i32{let x=1;suma(&x,&x)}'),
        ('Parámetros exclusivos de orígenes diferentes', 'fn f(a:&mut i32,b:&mut i32){*a=2;*b=3;} fn main()->i32{let mut x=1;let mut y=1;f(&mut x,&mut y);x+y}'),
        ('Temporal exclusivo termina con llamada', 'fn f(r:&mut i32){} fn main()->i32{let mut x=1;f(&mut x);f(&mut x);x}'),
        ('Préstamo de String no mueve propietario', 'fn main()->bool{let s="hola";let r=&s;*r=="hola"}'),
        ('Mover String después de liberar préstamo', 'fn main()->String{let s="hola";{let r=&s;let b=*r=="hola";}s}'),
        ('Préstamo de arreglo completo', 'fn main()->i32{let a=[1,2];let r=&a;(*r)[0]}'),
        ('Préstamo de estructura completa', 'struct P{x:i32} fn main()->i32{let p=P{x:1};let r=&p;(*r).x}'),
        ('Préstamo de tupla completa', 'fn main()->i32{let p=(1,true);let r=&p;(*r).0}'),
        ('Referencia producida por bloque con origen exterior', 'fn main()->i32{let x=1;let r={&x};*r}'),
        ('Préstamos locales en if', 'fn main()->i32{let mut x=1;if true{let r=&mut x;*r=2;}else{let r=&mut x;*r=3;}x}'),
        ('Préstamos locales en while', 'fn main()->i32{let mut x=0;while x<2{let r=&mut x;*r+=1;}x}'),
        ('Tipos f64', 'fn main()->f64{let x=1.5;let r=&x;*r}'),
        ('Tipos bool', 'fn main()->bool{let x=true;let r=&x;!*r}'),
        ('Tipos char', "fn main()->char{let x='a';let r=&x;*r}"),
    ]
    invalidos = [
        ('Mut requiere origen mutable', 'fn main(){let x=1;let r=&mut x;}', 'requiere una variable declarada con mut'),
        ('Exclusivos simultáneos', 'fn main(){let mut x=1;let r=&mut x;let s=&mut x;}', 'incompatible con los préstamos activos'),
        ('Compartido y luego exclusivo', 'fn main(){let mut x=1;let r=&x;let s=&mut x;}', 'incompatible con los préstamos activos'),
        ('Exclusivo y luego compartido', 'fn main(){let mut x=1;let r=&mut x;let s=&x;}', 'incompatible con los préstamos activos'),
        ('Modificar propietario compartido', 'fn main(){let mut x=1;let r=&x;x=2;}', 'modificar un valor mientras tiene préstamos activos'),
        ('Modificar propietario exclusivo', 'fn main(){let mut x=1;let r=&mut x;x=2;}', 'modificar un valor mientras tiene préstamos activos'),
        ('Leer propietario exclusivo', 'fn main()->i32{let mut x=1;let r=&mut x;x}', 'acceder directamente'),
        ('Mover propietario compartido', 'fn main()->String{let x="hola";let r=&x;x}', 'mover'),
        ('Mover propietario exclusivo', 'fn main()->String{let mut x="hola";let r=&mut x;x}', 'acceder directamente'),
        ('Escribir por compartida', 'fn main(){let x=1;let r=&x;*r=2;}', 'referencia inmutable'),
        ('Leer referencia exclusiva movida', 'fn main()->i32{let mut x=1;let r=&mut x;let s=r;*r}', 'después de mover'),
        ('Mover valor a través de referencia', 'fn main()->String{let x="hola";let r=&x;*r}', 'mover un valor a través de una referencia'),
        ('Origen movido no se puede prestar', 'fn main(){let x="hola";let y=x;let r=&x;}', 'después de mover'),
        ('Origen no inicializado', 'fn main(){let x:i32;let r=&x;}', 'antes de inicializarla'),
        ('Referencia escapa del bloque del origen', 'fn main()->i32{let r={let x=1;&x};*r}', 'sobrevivir'),
        ('Retorno de referencia local', 'fn f()->&i32{let x=1;&x}', 'no admite devolver referencias'),
        ('Retorno de referencia parámetro limitado', 'fn f(r:&i32)->&i32{r}', 'no admite devolver referencias'),
        ('Dos argumentos exclusivos mismo origen', 'fn f(a:&mut i32,b:&mut i32){} fn main(){let mut x=1;f(&mut x,&mut x);}', 'incompatible con los préstamos activos'),
        ('Argumentos compartido y exclusivo mismo origen', 'fn f(a:&i32,b:&mut i32){} fn main(){let mut x=1;f(&x,&mut x);}', 'incompatible con los préstamos activos'),
        ('Préstamo a temporal', 'fn main(){let r=&(1+2);}', 'variable completa'),
        ('Préstamo a campo', 'struct P{x:i32} fn main(){let p=P{x:1};let r=&p.x;}', 'variable completa'),
        ('Préstamo a elemento', 'fn main(){let a=[1];let r=&a[0];}', 'variable completa'),
        ('Referencia anidada', 'fn main(){let x=1;let r=&x;let s=&r;}', 'referencias anidadas'),
        ('Referencia dentro de arreglo', 'fn main(){let x=1;let a=[&x];}', 'referencias dentro de arreglos'),
        ('Referencia dentro de tupla', 'fn main(){let x=1;let a=(&x,true);}', 'referencias dentro de arreglos'),
        ('Referencia en campo de estructura', 'struct P{x:&i32}', 'referencias almacenadas'),
        ('Referencia en constante', 'const X:i32={let x=1;let r=&x;*r};', 'constantes globales'),
        ('Reasignar referencia limitado', 'fn main(){let x=1;let y=2;let mut r=&x;r=&y;}', 'reasignar variables de referencia'),
        ('Patrones de referencia limitados', 'fn main()->i32{let x=1;let r=&x;match r{s=>*s}}', 'no admite patrones sobre referencias'),
        ('Desreferenciar entero', 'fn main()->i32{let x=1;*x}', 'requiere un tipo de referencia'),
        ('Tipo incorrecto al escribir', 'fn main(){let mut x=1;let r=&mut x;*r=true;}', 'Asignación desreferenciada incompatible'),
    ]
    resultados = []
    for nombre, codigo in validos:
        r = analizar_programa(codigo)
        cumple = r['valido']
        resultados.append(cumple)
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(r['errores'])
    for nombre, codigo, mensaje in invalidos:
        r = analizar_programa(codigo)
        cumple = not r['valido'] and any(mensaje.lower() in e['mensaje'].lower() for e in r['errores'])
        resultados.append(cumple)
        print(f'{nombre}: {"OK" if cumple else "FALLO"}')
        if not cumple:
            print(r['errores'])
    r = analizar_programa('fn main()->i32{let mut x=1;let r:&mut i32=&mut x;*r=2;*r}')
    mapa = r['prestamos']
    resultados.append(r['valido'] and len(mapa)==1 and all(isinstance(n,P.BorrowExprContext) for n in mapa))
    resultados.append(all(set(v)=={'simbolo_id','tipo','mutable'} and v['tipo']=='i32' and v['mutable'] is True for v in mapa.values()))
    resultados.append(all(r['simbolos'][v['simbolo_id']]['nombre']=='x' for v in mapa.values()))
    resultados.append(any(t=='&mut i32' for t in r['tipos_expresiones'].values()))
    destinos = [n for n in r['referencias'] if isinstance(n,P.DereferenceTargetContext)]
    resultados.append(len(destinos)==1 and r['simbolos'][r['referencias'][destinos[0]]]['nombre']=='r')
    resultados.append(clasificar_tipo('&i32',{}, {})=='Copy' and clasificar_tipo('&mut i32',{}, {})=='Move')
    for codigo in ['fn main(){let x=1;let r=&mut x;}', 'fn main(){let mut x=1;let r=&mut x;let s=&mut x;}', 'fn main(){let x=;}']:
        invalido = analizar_programa(codigo)
        resultados.append(not invalido['valido'] and invalido['prestamos']=={} and invalido['arbol'] is None)
    r = analizar_programa('fn main(){\n let mut x=1;\n let a=&mut x;\n let b=&x;\n}')
    resultados.append(any(e['linea']==4 and e['columna']==8 and e['fase']=='semantico' for e in r['errores']))
    correctas = sum(resultados)
    print(f'Resultado: {correctas}/{len(resultados)} pruebas OK')
    if correctas != len(resultados):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
