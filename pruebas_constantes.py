"""Pruebas de valores calculados, dependencias y errores constantes.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# Cada prueba válida incluye el código y los valores
# que deben recibir los símbolos del backend.
VALIDAS = [
    (
        "Constante entera utilizada en una función",
        """
const LIMITE: i32 = 10;

fn main() -> i32 {
    return LIMITE;
}
""",
        {"LIMITE": 10},
    ),
    (
        "Prioridad de operaciones",
        """
const RESULTADO: i32 = 2 + 3 * 4;
""",
        {"RESULTADO": 14},
    ),
    (
        "Paréntesis",
        """
const RESULTADO: i32 = (2 + 3) * 4;
""",
        {"RESULTADO": 20},
    ),
    (
        "Referencia a otra constante",
        """
const BASE: i32 = 10;
const LIMITE: i32 = BASE * 2;
""",
        {"BASE": 10, "LIMITE": 20},
    ),
    (
        "Referencia adelantada",
        """
const LIMITE: i32 = BASE * 2;
const BASE: i32 = 10;
""",
        {"LIMITE": 20, "BASE": 10},
    ),
    (
        "Constante decimal",
        """
const VALOR: f64 = 1.5 + 2.5;
""",
        {"VALOR": 4.0},
    ),
    (
        "Comparaciones y lógica",
        """
const ACTIVO: bool = 10 > 2 && !false;
""",
        {"ACTIVO": True},
    ),
    (
        "Constante char",
        """
const LETRA: char = 'ñ';
""",
        {"LETRA": "ñ"},
    ),
    (
        "String con escapes",
        r"""
const MENSAJE: String = "Hola\nmundo";
""",
        {"MENSAJE": "Hola\nmundo"},
    ),
    (
        "División entera negativa trunca hacia cero",
        """
const RESULTADO: i32 = -7 / 2;
""",
        {"RESULTADO": -3},
    ),
    (
        "Residuo negativo",
        """
const RESULTADO: i32 = -7 % 2;
""",
        {"RESULTADO": -1},
    ),
    (
        "Valor mínimo de i32",
        """
const MINIMO: i32 = -2147483648;
""",
        {"MINIMO": -2147483648},
    ),
    (
        "Cortocircuito de AND",
        """
const ACTIVO: bool = false && (1 / 0 == 0);
""",
        {"ACTIVO": False},
    ),
    (
        "Cortocircuito de OR",
        """
const ACTIVO: bool = true || (1 / 0 == 0);
""",
        {"ACTIVO": True},
    ),
    (
        "Variable local con nombre de constante",
        """
const NUMERO: i32 = 10;

fn main() -> i32 {
    let NUMERO = 20;
    return NUMERO;
}
""",
        {"NUMERO": 10},
    ),
]


# Cada prueba inválida indica la fase y parte del mensaje
# que esperamos encontrar.
INVALIDAS = [
    (
        "Tipo incompatible",
        """
const LIMITE: i32 = true;
""",
        "semantico",
        "se esperaba i32, pero se recibió bool",
    ),
    (
        "Constante duplicada",
        """
const LIMITE: i32 = 10;
const LIMITE: i32 = 20;
""",
        "semantico",
        "La constante 'LIMITE' ya fue declarada.",
    ),
    (
        "Nombre compartido con función",
        """
const obtener: i32 = 10;

fn obtener() -> i32 {
    return 1;
}
""",
        "semantico",
        "ya pertenece a una función",
    ),
    (
        "Referencia no declarada",
        """
const LIMITE: i32 = DESCONOCIDA;
""",
        "semantico",
        "no está declarada",
    ),
    (
        "Dependencia circular directa",
        """
const NUMERO: i32 = NUMERO;
""",
        "semantico",
        "Dependencia circular",
    ),
    (
        "Dependencia circular entre constantes",
        """
const PRIMERA: i32 = SEGUNDA;
const SEGUNDA: i32 = PRIMERA;
""",
        "semantico",
        "Dependencia circular",
    ),
    (
        "Llamada a función en una constante",
        """
const NUMERO: i32 = obtener();

fn obtener() -> i32 {
    return 10;
}
""",
        "semantico",
        "no puede inicializarse con una llamada a función",
    ),
    (
        "Asignación a una constante",
        """
const LIMITE: i32 = 10;

fn main() -> i32 {
    LIMITE = 20;
    return LIMITE;
}
""",
        "semantico",
        "No se puede modificar 'LIMITE'",
    ),
    (
        "Asignación compuesta a una constante",
        """
const LIMITE: i32 = 10;

fn main() -> i32 {
    LIMITE += 1;
    return LIMITE;
}
""",
        "semantico",
        "No se puede modificar 'LIMITE'",
    ),
    (
        "División entera entre cero",
        """
const NUMERO: i32 = 10 / 0;
""",
        "semantico",
        "entre cero",
    ),
    (
        "Desbordamiento de i32",
        """
const NUMERO: i32 = 2147483647 + 1;
""",
        "semantico",
        "fuera del rango de i32",
    ),
    (
        "Constante sin tipo",
        """
const NUMERO = 10;
""",
        "sintactico",
        None,
    ),
    (
        "Constante sin inicializador",
        """
const NUMERO: i32;
""",
        "sintactico",
        None,
    ),
]


def mostrar_errores(resultado):
    for error in resultado["errores"]:
        print(
            f"Error {error['fase']} — "
            f"Línea {error['linea']}, "
            f"columna {error['columna']}: "
            f"{error['mensaje']}"
        )


def ejecutar_pruebas():
    correctas = 0

    for nombre, codigo, esperados in VALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

        # Extraer únicamente los símbolos de constantes.
        constantes = {
            simbolo["nombre"]: simbolo
            for simbolo in resultado["simbolos"].values()
            if simbolo.get("es_constante", False)
        }

        valores = {
            nombre: simbolo["valor"]
            for nombre, simbolo in constantes.items()
        }

        cumple = (
            resultado["valido"]
            and resultado["arbol"] is not None
            and not resultado["errores"]
            and valores == esperados
            and all(
                not simbolo["mutable"]
                and simbolo["funcion"] is None
                for simbolo in constantes.values()
            )
        )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Valores esperados:", esperados)
            print("Valores recibidos:", valores)

    for nombre, codigo, fase, fragmento in INVALIDAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        mostrar_errores(resultado)

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
            # Un programa inválido no entrega símbolos al backend.
            and resultado["simbolos"] == {}
        )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", fragmento or f"error {fase}")

    total = len(VALIDAS) + len(INVALIDAS)
    print(f"\nResultado: {correctas}/{total} pruebas OK")

    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()