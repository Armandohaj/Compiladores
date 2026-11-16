"""Tipos esperados en bloques y match, incluidos arreglos vacíos anidados."""
from main import analizar_programa


def ejecutar_pruebas():
    """Propaga contexto donde corresponde y conserva incompatibilidades reales."""
    casos = [
        ('Let con bloque vacío tipado', 'fn main()->[i32;0]{let x:[i32;0]={[]};x}', None),
        ('Return explícito de bloque', 'fn main()->[i32;0]{return {[]};}', None),
        ('Retorno implícito con paréntesis', 'fn main()->[i32;0]{({[]})}', None),
        ('Let con match', 'fn main()->[i32;0]{let x:[i32;0]=match true{true=>[],false=>[]};x}', None),
        ('Match como retorno implícito', 'fn main()->[i32;0]{match true{true=>[],false=>[]}}', None),
        ('Match con bloques', 'fn main()->[i32;0]{match true{true=>{[]},false=>{[]}}}', None),
        ('Argumento con bloque', 'fn f(x:[i32;0])->i32{1} fn main()->i32{f({[]})}', None),
        ('Argumento con match', 'fn f(x:[i32;0])->i32{1} fn main()->i32{f(match true{true=>[],false=>[]})}', None),
        ('Campo con bloque', 'struct P{x:[i32;0]} fn main()->P{P{x:{[]}}}', None),
        ('Variante con bloque', 'enum E{A([i32;0])} fn main()->E{E::A({[]})}', None),
        ('Tupla con bloque contextual', 'fn main()->([i32;0],bool){({[]},true)}', None),
        ('Arreglo anidado', 'fn main()->[[i32;0];1]{[{[]}]}', None),
        ('Constante con bloque', 'const R:[i32;0]={[]};', None),
        ('Constante con match', 'const R:[i32;0]=match true{true=>{[]},false=>[]};', None),
        ('Tamaño incorrecto sigue inválido', 'fn main()->[i32;1]{({[]})}', 'Retorno implícito incompatible'),
        ('Sin contexto sigue inválido', 'fn main(){let x={[]};}', 'No se puede inferir'),
        ('Bool incompatible sigue inválido', 'fn main()->i32{match true{true=>{false},false=>{true}}}', 'Retorno implícito incompatible'),
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
    # Se comprueba además el valor calculado, no solo la aceptación.
    r = analizar_programa('const R:[i32;0]=match true{true=>{[]},false=>[]};')
    cumple = r['valido'] and any(s.get('valor') == [] for s in r['simbolos'].values() if s['es_constante'])
    correctas += cumple
    print(f'Valor de constante vacía: {"OK" if cumple else "FALLO"}')
    total = len(casos) + 1
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
