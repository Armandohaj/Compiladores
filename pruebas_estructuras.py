"""Verifica estructuras nominales, constructores, campos y datos del backend.

Ejecutar: python pruebas_estructuras.py
No ejecuta WebAssembly ni comprueba reglas de ownership aún pendientes.
"""
from main import analizar_programa
from generated.RustiQParser import RustiQParser


P = "struct Persona { edad: i32, activo: bool } "
VALIDAS = [
    ("Declaración y lectura", P + "fn main() -> i32 { let p=Persona{edad:20,activo:true}; return p.edad; }", {}),
    ("Tipo explícito", P + "fn main() { let p:Persona=Persona{edad:20,activo:true}; }", {}),
    ("Orden de campos diferente", P + "fn main() { let p=Persona{activo:true,edad:20}; }", {}),
    ("Comas finales", "struct P { x:i32, y:bool, } fn main() { let p=P{x:1,y:true,}; }", {}),
    ("Estructura vacía", "struct V {} fn main() { let v=V{}; }", {}),
    ("Tipo declarado después de usarse", "fn f(p:Persona)->i32 { return p.edad; } " + P, {}),
    ("Parámetro y retorno", P + "fn f(p:Persona)->Persona { return p; } fn main()->i32 { return f(Persona{edad:1,activo:true}).edad; }", {}),
    ("Asignación a campo", P + "fn main() { let mut p=Persona{edad:20,activo:true}; p.edad=21; }", {}),
    ("Campo booleano", P + "fn main() { let mut p=Persona{edad:20,activo:true}; p.activo=false; }", {}),
    ("Parámetro mutable", P + "fn f(mut p:Persona)->i32 { p.edad+=1; return p.edad; }", {}),
    ("Asignación completa", P + "fn main() { let mut p=Persona{edad:20,activo:true}; p=Persona{edad:21,activo:false}; }", {}),
    ("Inicialización diferida", P + "fn main() { let p:Persona; p=Persona{edad:1,activo:true}; }", {}),
    ("Campo como condición", P + "fn main()->i32 { let p=Persona{edad:1,activo:true}; if p.activo { return p.edad; } else { return 0; } }", {}),
    ("Constructor en condición con acceso", P + "fn main() { if Persona{edad:1,activo:true}.activo {} }", {}),
    ("Campo en ciclo", P + "fn main() { let mut p=Persona{edad:0,activo:true}; while p.edad<2 { p.edad+=1; } }", {}),
    ("Campos char y String", "struct Texto { letra:char, texto:String } fn main()->char { let t=Texto{letra:'ñ',texto:\"Hola\"}; return t.letra; }", {}),
    ("Campo decimal", "struct Medida { valor:f64 } fn main() { let mut m=Medida{valor:1.5}; m.valor/=2.0; }", {}),
    ("Campo arreglo vacío contextual", "struct V { datos:[i32;0] } fn main() { let v=V{datos:[]}; }", {}),
    ("Campo tupla con arreglo vacío", "struct V { dato:([i32;0],bool) } fn main() { let v=V{dato:([],true)}; }", {}),
    ("Accesos mezclados", "struct V { datos:[(i32,bool);1] } fn main() { let mut v=V{datos:[(1,true)]}; v.datos[0].0+=2; }", {}),
    ("Estructuras anidadas", P + "struct Grupo { persona:Persona } fn main()->i32 { let g=Grupo{persona:Persona{edad:20,activo:true}}; return g.persona.edad; }", {}),
    ("Escritura anidada", P + "struct Grupo { persona:Persona } fn main() { let mut g=Grupo{persona:Persona{edad:20,activo:true}}; g.persona.edad=21; }", {}),
    ("Arreglo de estructuras", P + "fn main()->i32 { let a=[Persona{edad:20,activo:true}]; return a[0].edad; }", {}),
    ("Tupla de estructuras", P + "fn main()->i32 { let t=(Persona{edad:20,activo:true},false); return t.0.edad; }", {}),
    ("Constante estructura", P + "const P:Persona=Persona{edad:20,activo:true};", {"P":{"estructura":"Persona","campos":{"edad":20,"activo":True}}}),
    ("Campo de constante", P + "const P:Persona=Persona{edad:20,activo:true}; const N:i32=P.edad;", {"P":{"estructura":"Persona","campos":{"edad":20,"activo":True}},"N":20}),
    ("Constante vacía", "struct V {} const X:V=V{};", {"X":{"estructura":"V","campos":{}}}),
    ("Arreglo constante de estructuras", "struct V { x:i32 } const A:[V;1]=[V{x:10}]; const N:i32=A[0].x;", {"A":[{"estructura":"V","campos":{"x":10}}],"N":10}),
    ("Referencia adelantada en constructor", "struct V { x:i32 } const P:V=V{x:N}; const N:i32=10;", {"P":{"estructura":"V","campos":{"x":10}},"N":10}),
    ("Arreglo vacío constante en campo", "struct V { a:[i32;0] } const X:V=V{a:[]};", {"X":{"estructura":"V","campos":{"a":[]}}}),
    ("Llaves de if con identificador", "fn main() { let b=true; if b {} }", {}),
    ("If seguido de bloque", "fn main() { let b=true; if b {} {} }", {}),
    ("While con identificador", "fn main() { let b=false; while b {} }", {}),
]
for operador in ("+=","-=","*=","/="):
    VALIDAS.append((f"Compuesta {operador}", P+f"fn main() {{ let mut p=Persona{{edad:20,activo:true}}; p.edad {operador} 2; }}",{}))

INVALIDAS = [
    ("Estructura duplicada", "struct V {} struct V {}", "ya fue declarada"),
    ("Campo duplicado", "struct V { x:i32,x:bool }", "ya fue declarado"),
    ("Nombre coincide con función", "struct V {} fn V() {}", "ya pertenece"),
    ("Nombre coincide con constante", "struct V {} const V:i32=1;", "ya pertenece"),
    ("Tipo de campo desconocido", "struct V { x:Desconocido }", "no está declarado"),
    ("Tipo local desconocido", "fn main() { let x:Desconocido; }", "no está declarado"),
    ("Tipo de parámetro desconocido", "fn f(x:Desconocido) {}", "no está declarado"),
    ("Tipo de retorno desconocido", "fn f()->Desconocido { return 1; }", "no está declarado"),
    ("Recursión directa por valor", "struct V { x:V }", "recursiva por valor"),
    ("Recursión indirecta por valor", "struct A { b:B } struct B { a:A }", "recursiva por valor"),
    ("Recursión a través de compuesto", "struct V { x:[(i32,V);1] }", "recursiva por valor"),
    ("Constructor desconocido", "fn main() { let p=Desconocido{}; }", "no está declarada"),
    ("Falta campo", P + "fn main() { let p=Persona{edad:20}; }", "Falta el campo"),
    ("Campo extra", P + "fn main() { let p=Persona{edad:20,activo:true,otro:1}; }", "no tiene el campo"),
    ("Campo repetido en constructor", P + "fn main() { let p=Persona{edad:20,activo:true,edad:21}; }", "está repetido"),
    ("Tipo de campo incompatible", P + "fn main() { let p=Persona{edad:true,activo:true}; }", "Tipo incompatible"),
    ("Lectura de campo inexistente", P + "fn main() { let p=Persona{edad:20,activo:true}; let x=p.otro; }", "no tiene el campo"),
    ("Campo en escalar", "fn main() { let x=1; let y=x.edad; }", "No se puede acceder"),
    ("Campo en tupla", "fn main() { let x=(1,true); let y=x.edad; }", "No se puede acceder"),
    ("Campo posicional en estructura", P + "fn main() { let p=Persona{edad:1,activo:true}; let x=p.0; }", "No se puede acceder"),
    ("Índice en estructura", P + "fn main() { let p=Persona{edad:1,activo:true}; let x=p[0]; }", "No se puede indexar"),
    ("Uso antes de inicializar", P + "fn main() { let p:Persona; let x=p.edad; }", "antes de inicializarla"),
    ("Escritura sin mut", P + "fn main() { let p=Persona{edad:1,activo:true}; p.edad=2; }", "No se puede modificar"),
    ("Compuesta sin mut", P + "fn main() { let p=Persona{edad:1,activo:true}; p.edad+=2; }", "No se puede modificar"),
    ("Escritura de constante", P + "const X:Persona=Persona{edad:1,activo:true}; fn main() { X.edad=2; }", "No se puede modificar"),
    ("Escritura sin inicializar", P + "fn main() { let mut p:Persona; p.edad=2; }", "antes de inicializarla"),
    ("Tipo incompatible al escribir", P + "fn main() { let mut p=Persona{edad:1,activo:true}; p.edad=false; }", "Tipos incompatibles"),
    ("Campo destino desconocido", P + "fn main() { let mut p=Persona{edad:1,activo:true}; p.otro=2; }", "no tiene el campo"),
    ("Tipos nominales distintos", "struct A { x:i32 } struct B { x:i32 } fn main() { let a:A=B{x:1}; }", "Tipos incompatibles"),
    ("Argumento nominal incorrecto", "struct A {} struct B {} fn f(a:A) {} fn main() { f(B{}); }", "Argumento 1"),
    ("Retorno nominal incorrecto", "struct A {} struct B {} fn f()->A { return B{}; }", "Retorno incompatible"),
    ("Llamada en constante", "struct V { x:i32 } const X:V=V{x:f()}; fn f()->i32 { return 1; }", "no puede inicializarse con una llamada"),
    ("Dependencia circular en constante", "struct V { x:i32 } const X:V=V{x:N}; const N:i32=X.x;", "Dependencia circular"),
    ("Compuesta sobre bool", P+"fn main() { let mut p=Persona{edad:1,activo:true}; p.activo+=false; }", "requiere números"),
    ("Compuesta sobre estructura", P+"fn main() { let mut p=Persona{edad:1,activo:true}; p+=Persona{edad:2,activo:false}; }", "requiere números"),
]


def recorrer(nodo):
    yield nodo
    for hijo in nodo.getChildren():
        if hasattr(hijo,"getChildren"):
            yield from recorrer(hijo)


def comprobar_backend():
    r=analizar_programa(P+"fn main() { let mut p=Persona{edad:1,activo:true}; let n=2; p.edad+=n; }")
    assert r["valido"],r["errores"]
    assert r["estructuras"]=={"Persona":{"edad":"i32","activo":"bool"}}
    asignacion=next(n for n in recorrer(r["arbol"]) if isinstance(n,RustiQParser.AssignmentContext))
    assert r["simbolos"][r["referencias"][asignacion]]["tipo"]=="Persona"
    assert r["tipos_expresiones"][asignacion]=="i32"
    assert r["tipos_expresiones"][asignacion.fieldAccess(0)]=="i32"
    lecturas=[n for n in recorrer(asignacion) if isinstance(n,RustiQParser.PrimaryContext) and n.IDENT()]
    assert [r["simbolos"][r["referencias"][n]]["nombre"] for n in lecturas]==["n"]


def ejecutar_pruebas():
    correctas=0
    for nombre,codigo,esperados in VALIDAS:
        r=analizar_programa(codigo)
        valores={s["nombre"]:s["valor"] for s in r["simbolos"].values() if s["es_constante"]}
        cumple=r["valido"] and r["arbol"] is not None and not r["errores"] and valores==esperados
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple: correctas+=1
        else: print(r["errores"],valores)
    for nombre,codigo,mensaje in INVALIDAS:
        r=analizar_programa(codigo)
        cumple=(not r["valido"] and r["arbol"] is None and any(e["fase"]=="semantico" and mensaje in e["mensaje"] for e in r["errores"])
            and all(r[c]=={} for c in ("simbolos","referencias","declaraciones","tipos_expresiones","funciones","estructuras")))
        print(f"{nombre}: {'OK' if cumple else 'FALLO'}")
        if cumple: correctas+=1
        else: print(r["errores"])
    comprobar_backend();correctas+=1
    print("Tipos nominales y referencias para backend: OK")
    total=len(VALIDAS)+len(INVALIDAS)+1
    print(f"\nResultado: {correctas}/{total} pruebas OK")
    if correctas!=total: raise SystemExit(1)


if __name__=="__main__":
    ejecutar_pruebas()
