"""Expresiones descartadas: el punto y coma no elimina sus efectos semánticos."""
from main import analizar_programa


def ejecutar_pruebas():
    """Comprueba tipos, consumo de Move, liberación de temporales y saltos."""
    casos = [
        ('Aritmética descartada', 'fn main()->i32{10+20;5}', True),
        ('Booleano descartado', 'fn main(){true;}', True),
        ('Conserva llamadas anteriores', 'fn main(){print(1);}', True),
        ('Arreglo descartado', 'fn main(){[1,2];}', True),
        ('Bloque con valor descartado', 'fn main()->i32{({let x=1;x+2});5}', True),
        ('Match descartado', 'fn main()->i32{match true{true=>1,false=>2};5}', True),
        ('Copy conserva disponibilidad', 'fn main()->i32{let x=1;x;x}', True),
        ('Move se consume al descartar', 'fn main()->String{let x="hola";x;x}', False),
        ('Error de tipos no se oculta', 'fn main(){true+1;}', False),
        ('Nombre no declarado', 'fn main(){desconocida;}', False),
        ('No es retorno implícito', 'fn main()->i32{1;}', False),
        ('Retorno dentro de expresión', 'fn main()->i32{1+{return 2;};}', True),
        ('Préstamo temporal se libera', 'fn main()->i32{let mut x=1;&mut x;x=2;x}', True),
        ('Move dentro de compuesto descartado', 'fn main()->String{let x="hola";[x];x}', False),
        ('Conflicto de préstamos no se oculta', 'fn main(){let mut x=1;let r=&x;&mut x;}', False),
    ]
    resultados = []
    for nombre, codigo, valido in casos:
        r = analizar_programa(codigo)
        correcto = r['valido'] == valido
        if not valido:
            correcto = correcto and bool(r['errores']) and r['arbol'] is None
        resultados.append(correcto)
        print(f'{nombre}: {"OK" if correcto else "FALLO"}')
        if not correcto:
            print(r['errores'])
    r = analizar_programa('fn main()->i32{10+20;5}')
    bloque = r['arbol'].functionDecl(0).block()
    sentencia = bloque.statement(0)
    resultados.append(sentencia.expression() is not None and sentencia.SEMICOLON() is not None and
                      r['tipos_expresiones'][sentencia.expression()] == 'i32' and bloque.expression() is not None)
    r = analizar_programa('fn main(){print(1);}')
    resultados.append(len(r['llamadas_incorporadas']) == 1 and
                      r['arbol'].functionDecl(0).block().statement(0).functionCall() is not None)
    print(f'Resultado: {sum(resultados)}/{len(resultados)} pruebas OK')
    if not all(resultados):
        raise SystemExit(1)


if __name__ == '__main__':
    ejecutar_pruebas()
