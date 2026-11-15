"""
Pruebas de enumeraciones sin datos.

Este archivo comprueba:
- Declaración y uso de enumeraciones.
- Compatibilidad de tipos.
- Mutabilidad.
- Valores constantes y etiquetas.
- Detección de errores.
- Información entregada al backend.

No ejecuta WebAssembly: verifica el análisis del programa.
"""

from main import analizar_programa


# Declaración que reutilizamos en varias pruebas.
# Evita escribir el mismo enum en cada ejemplo.
ESTADO = """
enum Estado {
    Pendiente,
    Completado
}
"""


# =====================================================
# 1. PROGRAMAS QUE DEBEN SER VÁLIDOS
# =====================================================

# Cada prueba contiene una tupla con:
# 1. Nombre descriptivo.
# 2. Código RustiQ.
# 3. Valores esperados de las constantes globales.
#
# Si el programa no declara constantes, esperamos {}.
VALIDAS = [
    (
        "Variable y retorno de enum",
        ESTADO + """
fn main() -> Estado {
    let estado = Estado::Pendiente;
    return estado;
}
""",
        {},
    ),
    (
        "Variable con tipo explícito",
        ESTADO + """
fn main() -> Estado {
    let estado: Estado = Estado::Completado;
    return estado;
}
""",
        {},
    ),
    (
        "Cambio de variante con mut",
        ESTADO + """
fn main() -> Estado {
    let mut estado = Estado::Pendiente;
    estado = Estado::Completado;
    return estado;
}
""",
        {},
    ),
    (
        "Parámetro y retorno",
        ESTADO + """
fn identidad(estado: Estado) -> Estado {
    return estado;
}

fn main() -> Estado {
    return identidad(Estado::Pendiente);
}
""",
        {},
    ),
    (
        "Enum declarado después de utilizarse",
        """
fn main() -> Estado {
    return Estado::Pendiente;
}
""" + ESTADO,
        {},
    ),
    (
        "Constantes con etiquetas",
        ESTADO + """
const INICIAL: Estado = Estado::Pendiente;
const FINAL: Estado = Estado::Completado;
""",
        {
            "INICIAL": {
                "enumeracion": "Estado",
                "variante": "Pendiente",
                "etiqueta": 0,
            },
            "FINAL": {
                "enumeracion": "Estado",
                "variante": "Completado",
                "etiqueta": 1,
            },
        },
    ),
    (
        "Igualdad de variantes",
        ESTADO + """
const IGUALES: bool =
    Estado::Pendiente == Estado::Pendiente;
""",
        {"IGUALES": True},
    ),
    (
        "Diferencia de variantes",
        ESTADO + """
const DISTINTOS: bool =
    Estado::Pendiente != Estado::Completado;
""",
        {"DISTINTOS": True},
    ),
    (
        "Enum dentro de estructura",
        ESTADO + """
struct Tarea {
    estado: Estado
}

fn main() -> Estado {
    let tarea = Tarea {
        estado: Estado::Pendiente
    };
    return tarea.estado;
}
""",
        {},
    ),
    (
        "Arreglo de enums",
        ESTADO + """
fn main() -> Estado {
    let estados = [
        Estado::Pendiente,
        Estado::Completado
    ];
    return estados[1];
}
""",
        {},
    ),
    (
        "Tupla con enum",
        ESTADO + """
fn main() -> Estado {
    let dato = (10, Estado::Pendiente);
    return dato.1;
}
""",
        {},
    ),
    (
        "Inicialización diferida",
        ESTADO + """
fn main() -> Estado {
    let estado: Estado;
    estado = Estado::Pendiente;
    return estado;
}
""",
        {},
    ),
]


# =====================================================
# 2. PROGRAMAS QUE DEBEN PRODUCIR ERRORES
# =====================================================

# Cada prueba contiene:
# 1. Nombre.
# 2. Código RustiQ.
# 3. Fase que debe detectar el error.
# 4. Fragmento esperado del mensaje.
#
# Si el fragmento es None, basta con encontrar un error
# de la fase indicada.
INVALIDAS = [
    (
        "Enumeración no declarada",
        """
fn main() {
    let estado = Desconocido::Pendiente;
}
""",
        "semantico",
        "no está declarada",
    ),
    (
        "Variante no declarada",
        ESTADO + """
fn main() {
    let estado = Estado::Cancelado;
}
""",
        "semantico",
        "no tiene la variante",
    ),
    (
        "Enumeración duplicada",
        ESTADO + """
enum Estado {
    Otro
}
""",
        "semantico",
        "ya fue declarada",
    ),
    (
        "Variante duplicada",
        """
enum Estado {
    Pendiente,
    Pendiente
}
""",
        "semantico",
        "ya fue declarada",
    ),
    (
        "Tipos nominales diferentes",
        """
enum Primero { A }
enum Segundo { A }

fn main() {
    let valor: Primero = Segundo::A;
}
""",
        "semantico",
        "Tipos incompatibles",
    ),
    (
        "Modificación sin mut",
        ESTADO + """
fn main() {
    let estado = Estado::Pendiente;
    estado = Estado::Completado;
}
""",
        "semantico",
        "No se puede modificar",
    ),
    (
        "Argumento de otro enum",
        """
enum Primero { A }
enum Segundo { A }

fn recibir(valor: Primero) {}

fn main() {
    recibir(Segundo::A);
}
""",
        "semantico",
        "Argumento 1",
    ),
    (
        "Retorno de otro enum",
        """
enum Primero { A }
enum Segundo { A }

fn obtener() -> Primero {
    return Segundo::A;
}
""",
        "semantico",
        "Retorno incompatible",
    ),
    (
        "Suma de variantes",
        ESTADO + """
fn main() {
    let valor = Estado::Pendiente + Estado::Completado;
}
""",
        "semantico",
        "requiere números",
    ),
    (
        "Orden entre variantes",
        ESTADO + """
fn main() -> bool {
    return Estado::Pendiente < Estado::Completado;
}
""",
        "semantico",
        "requiere valores numéricos",
    ),
    (
        "Enum usado como condición",
        ESTADO + """
fn main() {
    if Estado::Pendiente {}
}
""",
        "semantico",
        "debe ser bool",
    ),
    (
        "Enum sin variantes",
        """
enum Estado {}
""",
        "sintactico",
        None,
    ),
]


# =====================================================
# 3. PRESENTACIÓN DE ERRORES
# =====================================================

def mostrar_errores(resultado):
    """
    Muestra los diagnósticos devueltos por analizar_programa.

    Recibe:
        resultado: diccionario con el resultado del análisis.

    No devuelve un valor útil ni modifica el resultado.
    Si no existen errores, no imprime nada.
    """
    for error in resultado["errores"]:
        print(
            f"Error {error['fase']} — "
            f"Línea {error['linea']}, "
            f"columna {error['columna']}: "
            f"{error['mensaje']}"
        )


# =====================================================
# 4. EJECUCIÓN Y COMPROBACIÓN DE LAS PRUEBAS
# =====================================================

def ejecutar_pruebas():
    """
    Ejecuta todos los casos y cuenta cuántos pasan.

    Una prueba válida pasa si el programa se acepta y sus
    constantes tienen los valores esperados.

    Una prueba inválida pasa si se rechaza el programa
    por el error concreto que queríamos detectar.

    También comprueba el registro destinado al backend.

    Si alguna prueba falla, termina con código de salida 1.
    Eso permite que ejecutar_pruebas.py detecte el fallo.
    """
    correctas = 0

    # -------------------------------------------------
    # A. Comprobar programas válidos.
    # -------------------------------------------------

    for nombre, codigo, esperados in VALIDAS:
        print(f"\n--- {nombre} ---")

        # Analizar el ejemplo sin ejecutar el programa RustiQ.
        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

        # Extraer únicamente las constantes globales.
        # Los símbolos de variables locales no tienen que
        # aparecer en esta comparación de valores.
        valores = {
            simbolo["nombre"]: simbolo["valor"]
            for simbolo in resultado["simbolos"].values()
            if simbolo.get("es_constante", False)
        }

        # No basta con aceptar el programa:
        # debe haber un árbol, no debe haber errores
        # y las constantes deben tener el valor correcto.
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
            print("Valores esperados:", esperados)
            print("Valores recibidos:", valores)

    # -------------------------------------------------
    # B. Comprobar programas inválidos.
    # -------------------------------------------------

    for nombre, codigo, fase, fragmento in INVALIDAS:
        print(f"\n--- {nombre} ---")

        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

        # any devuelve True si al menos un diagnóstico
        # pertenece a la fase y contiene el texto esperado.
        #
        # Esto evita aprobar una prueba porque ocurrió
        # un error distinto al que queríamos comprobar.
        cumple = (
            not resultado["valido"]
            and resultado["arbol"] is None
            and any(
                error["fase"] == fase
                and (
                    fragmento is None
                    or fragmento in error["mensaje"]
                )
                for error in resultado["errores"]
            )
            # No entregar registros al backend
            # cuando el programa es inválido.
            and resultado["enumeraciones"] == {}
        )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", fragmento or f"error {fase}")

    # -------------------------------------------------
    # C. Comprobar información para el backend.
    # -------------------------------------------------

    print("\n--- Registro de enumeraciones para el backend ---")

    # Analizar solamente la declaración del enum.
    resultado = analizar_programa(ESTADO)

    # Las etiquetas se asignan según el orden de declaración.
    esperado = {
        "Estado": {
            "variantes": {
                "Pendiente": 0,
                "Completado": 1,
            }
        }
    }

    if resultado["valido"] and resultado["enumeraciones"] == esperado:
        correctas += 1
        print("Prueba OK")
    else:
        print("PRUEBA FALLIDA")
        print(resultado["errores"])

    # -------------------------------------------------
    # D. Mostrar resumen y comunicar fallos.
    # -------------------------------------------------

    # Sumamos uno por la comprobación del backend.
    total = len(VALIDAS) + len(INVALIDAS) + 1

    print(f"\nResultado: {correctas}/{total} pruebas OK")

    if correctas != total:
        raise SystemExit(1)


# Ejecutar las pruebas solo al lanzar este archivo directamente.
# Importarlo desde otro módulo no inicia las pruebas.
if __name__ == "__main__":
    ejecutar_pruebas()