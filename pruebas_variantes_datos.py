# Suite del frontend: cantidad y tipos de datos asociados a variantes de enum. Se analiza
# código y se comprueban diagnósticos o mapas; la ejecución WASM corresponde a las pruebas
# de integración.
"""
Pruebas de enumeraciones con datos asociados.

Verifican:
- Cantidad y tipos de argumentos.
- Variantes con datos y sin datos.
- Valores constantes y etiquetas.
- Combinaciones con arreglos, tuplas y estructuras.
- Información que recibe el backend.

Estas pruebas validan el frontend, no la ejecución WebAssembly.
"""

from main import analizar_programa


# Declaración reutilizable en los ejemplos.
RESULTADO = """
enum Resultado {
    Correcto(i32),
    Error(String),
    Vacio
}
"""


# =====================================================
# 1. CASOS VÁLIDOS
# =====================================================

# Cada prueba contiene:
# nombre, código RustiQ y valores constantes esperados.
VALIDAS = [
    (
        "Variante con entero",
        RESULTADO + """
fn main() -> Resultado {
    return Resultado::Correcto(10);
}
""",
        {},
    ),
    (
        "Variante con cadena",
        RESULTADO + """
fn main() -> Resultado {
    return Resultado::Error("Falló");
}
""",
        {},
    ),
    (
        "Variante sin datos",
        RESULTADO + """
fn main() -> Resultado {
    return Resultado::Vacio;
}
""",
        {},
    ),
    (
        "Expresión como argumento",
        RESULTADO + """
fn main() -> Resultado {
    return Resultado::Correcto(5 + 5);
}
""",
        {},
    ),
    (
        "Varios datos asociados",
        """
enum Punto {
    Coordenada(i32, i32),
    Desconocido
}

fn main() -> Punto {
    return Punto::Coordenada(10, 20);
}
""",
        {},
    ),
    (
        "Cambio de variante con mut",
        RESULTADO + """
fn main() -> Resultado {
    let mut valor = Resultado::Correcto(10);
    valor = Resultado::Error("Falló");
    return valor;
}
""",
        {},
    ),
    (
        "Parámetro y retorno de enum",
        RESULTADO + """
fn identidad(valor: Resultado) -> Resultado {
    return valor;
}

fn main() -> Resultado {
    return identidad(Resultado::Correcto(10));
}
""",
        {},
    ),
    (
        "Constante con datos",
        RESULTADO + """
const VALOR: Resultado = Resultado::Correcto(5 + 5);
""",
        {
            "VALOR": {
                "enumeracion": "Resultado",
                "variante": "Correcto",
                "etiqueta": 0,
                "datos": [10],
            }
        },
    ),
    (
        "Constante sin datos conserva su formato",
        RESULTADO + """
const VALOR: Resultado = Resultado::Vacio;
""",
        {
            "VALOR": {
                "enumeracion": "Resultado",
                "variante": "Vacio",
                "etiqueta": 2,
            }
        },
    ),
    (
        "Referencia adelantada en los datos",
        RESULTADO + """
const VALOR: Resultado = Resultado::Correcto(NUMERO);
const NUMERO: i32 = 10;
""",
        {
            "VALOR": {
                "enumeracion": "Resultado",
                "variante": "Correcto",
                "etiqueta": 0,
                "datos": [10],
            },
            "NUMERO": 10,
        },
    ),
    (
        "Arreglo vacío con contexto",
        """
enum Datos {
    Numeros([i32; 0]),
    Vacio
}

const VALOR: Datos = Datos::Numeros([]);
""",
        {
            "VALOR": {
                "enumeracion": "Datos",
                "variante": "Numeros",
                "etiqueta": 0,
                "datos": [[]],
            }
        },
    ),
    (
        "Tupla como dato asociado",
        """
enum Datos {
    Par((i32, bool))
}

const VALOR: Datos = Datos::Par((10, true));
""",
        {
            "VALOR": {
                "enumeracion": "Datos",
                "variante": "Par",
                "etiqueta": 0,
                "datos": [(10, True)],
            }
        },
    ),
    (
        "Estructura como dato asociado",
        """
struct Persona {
    edad: i32
}

enum Datos {
    Usuario(Persona)
}

const VALOR: Datos = Datos::Usuario(Persona { edad: 20 });
""",
        {
            "VALOR": {
                "enumeracion": "Datos",
                "variante": "Usuario",
                "etiqueta": 0,
                "datos": [
                    {
                        "estructura": "Persona",
                        "campos": {"edad": 20},
                    }
                ],
            }
        },
    ),
    (
        "Enumeraciones anidadas",
        """
enum Interior {
    Numero(i32)
}

enum Exterior {
    Contenido(Interior)
}

const VALOR: Exterior =
    Exterior::Contenido(Interior::Numero(10));
""",
        {
            "VALOR": {
                "enumeracion": "Exterior",
                "variante": "Contenido",
                "etiqueta": 0,
                "datos": [
                    {
                        "enumeracion": "Interior",
                        "variante": "Numero",
                        "etiqueta": 0,
                        "datos": [10],
                    }
                ],
            }
        },
    ),
]


# =====================================================
# 2. CASOS INVÁLIDOS
# =====================================================

# Cada prueba contiene:
# nombre, código y fragmento del error semántico esperado.
INVALIDAS = [
    (
        "Faltan paréntesis y datos",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto;
}
""",
        "requiere argumentos",
    ),
    (
        "Falta un argumento",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto();
}
""",
        "espera 1 argumentos, pero recibió 0",
    ),
    (
        "Sobran argumentos",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto(10, 20);
}
""",
        "espera 1 argumentos, pero recibió 2",
    ),
    (
        "Tipo de argumento incorrecto",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto(true);
}
""",
        "se esperaba i32, pero se recibió bool",
    ),
    (
        "Segundo argumento incorrecto",
        """
enum Punto {
    Coordenada(i32, i32)
}

fn main() {
    let punto = Punto::Coordenada(10, true);
}
""",
        "Argumento 2",
    ),
    (
        "Paréntesis en variante sin datos",
        RESULTADO + """
fn main() {
    let valor = Resultado::Vacio();
}
""",
        "no recibe argumentos ni utiliza paréntesis",
    ),
    (
        "Argumento en variante sin datos",
        RESULTADO + """
fn main() {
    let valor = Resultado::Vacio(10);
}
""",
        "no recibe argumentos",
    ),
    (
        "Variable no declarada dentro de argumento",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto(desconocida);
}
""",
        "no está declarada",
    ),
    (
        "Tipo de dato asociado desconocido",
        """
enum Datos {
    Valor(Desconocido)
}
""",
        "no está declarado",
    ),
    (
        "Recursión directa por valor",
        """
enum Nodo {
    Vacio,
    Siguiente(Nodo)
}
""",
        "recursiva por valor",
    ),
    (
        "Recursión entre estructura y enum",
        """
struct Caja {
    contenido: Datos
}

enum Datos {
    Valor(Caja)
}
""",
        "recursiva por valor",
    ),
    (
        "Arreglo asociado con tamaño incorrecto",
        """
enum Datos {
    Numeros([i32; 2])
}

fn main() {
    let valor = Datos::Numeros([10]);
}
""",
        "Argumento 1",
    ),
    (
        "Llamada dentro de constante",
        RESULTADO + """
fn obtener() -> i32 {
    return 10;
}

const VALOR: Resultado =
    Resultado::Correcto(obtener());
""",
        "no puede inicializarse con una llamada",
    ),
    (
        "Cambio de variante sin mut",
        RESULTADO + """
fn main() {
    let valor = Resultado::Correcto(10);
    valor = Resultado::Vacio;
}
""",
        "No se puede modificar",
    ),
]


# =====================================================
# 3. FUNCIONES AUXILIARES
# =====================================================

def mostrar_errores(resultado):
    """Imprime los diagnósticos para entender qué detectó el compilador."""
    for error in resultado["errores"]:
        print(
            f"Error {error['fase']} — "
            f"Línea {error['linea']}, "
            f"columna {error['columna']}: "
            f"{error['mensaje']}"
        )


def comprobar_registro_backend():
    """
    Verifica el contrato de datos para Anthony.

    Las etiquetas identifican variantes.
    datos_variantes indica qué tipos transporta cada una.
    """
    resultado = analizar_programa(RESULTADO)

    esperado = {
        "Resultado": {
            "variantes": {
                "Correcto": 0,
                "Error": 1,
                "Vacio": 2,
            },
            "datos_variantes": {
                "Correcto": ["i32"],
                "Error": ["String"],
                "Vacio": [],
            },
        }
    }

    return (
        resultado["valido"]
        and resultado["enumeraciones"] == esperado
    )


# =====================================================
# 4. EJECUCIÓN DE LAS PRUEBAS
# =====================================================

def ejecutar_pruebas():
    """
    Ejecuta los casos y cuenta los resultados correctos.

    Un programa inválido cuenta como prueba correcta cuando
    produce el diagnóstico que esperábamos.

    Si alguna prueba falla, termina con código de salida 1.
    """
    # Reúne los casos de esta suite y comprueba las expectativas. El total de aprobadas
    # incluye programas inválidos rechazados correctamente; no significa que todos los
    # programas hayan compilado.
    correctas = 0

    for nombre, codigo, esperados in VALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

        # Extraer valores de constantes, excluyendo variables locales.
        valores = {
            simbolo["nombre"]: simbolo["valor"]
            for simbolo in resultado["simbolos"].values()
            if simbolo.get("es_constante", False)
        }

        cumple = (
            resultado["valido"]
            and resultado["arbol"] is not None
            and not resultado["errores"]
            and valores == esperados
        )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Esperado:", esperados)
            print("Recibido:", valores)

    for nombre, codigo, mensaje in INVALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

        cumple = (
            not resultado["valido"]
            and resultado["arbol"] is None
            and any(
                error["fase"] == "semantico"
                and mensaje in error["mensaje"]
                for error in resultado["errores"]
            )
            and resultado["enumeraciones"] == {}
        )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", mensaje)

    print("\n--- Registro de variantes para el backend ---")

    if comprobar_registro_backend():
        correctas += 1
        print("Prueba OK")
    else:
        print("PRUEBA FALLIDA")

    total = len(VALIDAS) + len(INVALIDAS) + 1
    print(f"\nResultado: {correctas}/{total} pruebas OK")

    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()