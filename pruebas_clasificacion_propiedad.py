"""Pruebas de clasificación: todavía no comprueban movimientos de variables."""
from clasificacion_propiedad import clasificar_tipo
from main import analizar_programa


def ejecutar_pruebas():
    """Verifica tipos básicos, composición y registros reales del analizador."""
    estructuras = {
        'Punto': {'x':'i32', 'y':'f64'},
        'Persona': {'nombre':'String', 'edad':'i32'},
        'Grupo': {'personas':'[Persona;2]'},
        'Caja': {'punto':'Punto', 'activo':'bool'},
        'Recursivo': {'otro':'Recursivo'},
    }
    enums = {
        'Estado': {'variantes':{'A':0,'B':1}},
        'Numero': {'variantes':{'A':0,'B':1}, 'datos_variantes':{'A':['i32'],'B':[]}},
        'Texto': {'variantes':{'Vacio':0,'ConTexto':1}, 'datos_variantes':{'Vacio':[],'ConTexto':['String']}},
        'Mixto': {'variantes':{'A':0}, 'datos_variantes':{'A':['(Punto,Persona)']}},
    }
    casos = [
        ('i32','Copy'), ('f64','Copy'), ('bool','Copy'), ('char','Copy'),
        ('String','Move'), ('[i32;3]','Copy'), ('[String;2]','Move'),
        ('[[i32;2];3]','Copy'), ('[[String;2];3]','Move'),
        ('[String;0]','Move'), ('[i32;0]','Copy'),
        ('(i32,bool)','Copy'), ('(String,bool)','Move'),
        ('(i32,(bool,char))','Copy'), ('(i32,(String,char))','Move'),
        ('([i32;2],bool)','Copy'), ('([String;2],bool)','Move'),
        ('Punto','Copy'), ('Persona','Move'), ('Grupo','Move'), ('Caja','Copy'),
        ('Estado','Copy'), ('Numero','Copy'), ('Texto','Move'), ('Mixto','Move'),
        ('Desconocido',None), ('unit',None), (None,None), ('Recursivo',None),
        ('[i32;mal]',None),
    ]
    correctas = 0
    for tipo, esperado in casos:
        recibido = clasificar_tipo(tipo, estructuras, enums)
        cumple = recibido == esperado
        print(f'{tipo}: {recibido} - {"OK" if cumple else "FALLO"}')
        correctas += cumple

    # Usar los formatos reales del frontend, sin agregar campos a su contrato.
    r = analizar_programa('''
struct P { x: i32 }
enum E { Vacio, Dato(String) }
fn main() -> i32 { 0 }
''')
    cumple = r['valido'] and (
        clasificar_tipo('P', r['estructuras'], r['enumeraciones']) == 'Copy'
        and clasificar_tipo('E', r['estructuras'], r['enumeraciones']) == 'Move'
    )
    correctas += cumple
    print(f'Registros reales del frontend: {"OK" if cumple else "FALLO"}')
    total = len(casos) + 1
    print(f'Resultado: {correctas}/{total} pruebas OK')
    if correctas != total:
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
