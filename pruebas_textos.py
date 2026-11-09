from main import analizar_programa


# Cada caso contiene:
# nombre, código, fase del error y fragmento esperado.
# Si la fase es None, el programa debe ser válido.
PRUEBAS = [
    (
        "Variable y retorno char",
        """
fn main() -> char {
    let letra: char = 'A';
    return letra;
}
""",
        None,
        None,
    ),
    (
        "Variable y retorno String",
        """
fn main() -> String {
    let mensaje: String = "Hola";
    return mensaje;
}
""",
        None,
        None,
    ),
    (
        "Inferencia de char",
        """
fn main() -> char {
    let letra = 'ñ';
    return letra;
}
""",
        None,
        None,
    ),
    (
        "Inferencia de String",
        """
fn main() -> String {
    let mensaje = "Hola";
    return mensaje;
}
""",
        None,
        None,
    ),
    (
        "Cadena vacía",
        """
fn main() -> String {
    return "";
}
""",
        None,
        None,
    ),
    (
        "Carácter Unicode",
        """
fn main() -> char {
    return '中';
}
""",
        None,
        None,
    ),
    (
        "Salto de línea escapado",
        r"""
fn main() -> char {
    return '\n';
}
""",
        None,
        None,
    ),
    (
        "Comilla simple escapada",
        r"""
fn main() -> char {
    return '\'';
}
""",
        None,
        None,
    ),
    (
        "Barra invertida escapada",
        r"""
fn main() -> char {
    return '\\';
}
""",
        None,
        None,
    ),
    (
        "Cadena con escapes",
        r"""
fn main() -> String {
    return "Hola\n\t\"mundo\"\\";
}
""",
        None,
        None,
    ),
    (
        "Asignación compatible de String",
        """
fn main() -> String {
    let mut mensaje = "Hola";
    mensaje = "Adiós";
    return mensaje;
}
""",
        None,
        None,
    ),
    (
        "Inicialización posterior de char",
        """
fn main() -> char {
    let letra: char;
    letra = 'B';
    return letra;
}
""",
        None,
        None,
    ),
    (
        "Parámetro y retorno char",
        """
fn identidad(letra: char) -> char {
    return letra;
}

fn main() -> char {
    return identidad('A');
}
""",
        None,
        None,
    ),
    (
        "Parámetro y retorno String",
        """
fn identidad(texto: String) -> String {
    return texto;
}

fn main() -> String {
    return identidad("Hola");
}
""",
        None,
        None,
    ),
    (
        "Igualdad de caracteres",
        """
fn main() -> bool {
    return 'A' == 'A';
}
""",
        None,
        None,
    ),
    (
        "Diferencia de cadenas",
        """
fn main() -> bool {
    return "Hola" != "Adiós";
}
""",
        None,
        None,
    ),
    (
        "String no es char",
        """
fn main() -> char {
    let letra: char = "A";
    return letra;
}
""",
        "semantico",
        "se esperaba char, pero se recibió String",
    ),
    (
        "char no es String",
        """
fn main() -> String {
    return 'A';
}
""",
        "semantico",
        "se esperaba String, pero se recibió char",
    ),
    (
        "Argumento de texto incompatible",
        """
fn identidad(texto: String) -> String {
    return texto;
}

fn main() -> String {
    return identidad('A');
}
""",
        "semantico",
        "Argumento 1 de 'identidad': se esperaba String",
    ),
    (
        "Asignación de texto incompatible",
        """
fn main() -> String {
    let mut texto = "Hola";
    texto = 'A';
    return texto;
}
""",
        "semantico",
        "se esperaba String, pero se recibió char",
    ),
    (
        "Suma de cadenas no admitida",
        """
fn main() -> String {
    return "Hola" + "mundo";
}
""",
        "semantico",
        "El operador '+' requiere números.",
    ),
    (
        "Signo negativo de un carácter",
        """
fn main() -> char {
    return -'A';
}
""",
        "semantico",
        "El signo negativo requiere un número.",
    ),
    (
        "Comparación entre char y String",
        """
fn main() -> bool {
    return 'A' == "A";
}
""",
        "semantico",
        "Comparación incompatible entre char y String.",
    ),
    (
        "Carácter vacío",
        """
fn main() -> char {
    return '';
}
""",
        "lexico",
        "token recognition error",
    ),
    (
        "Varios caracteres entre comillas simples",
        """
fn main() -> char {
    return 'AB';
}
""",
        "lexico",
        "token recognition error",
    ),
    (
        "Escape no admitido",
        r"""
fn main() -> String {
    return "\q";
}
""",
        "lexico",
        "token recognition error",
    ),
    (
        "Cadena sin cerrar",
        """
fn main() -> String {
    return "Hola;
}
""",
        "lexico",
        "token recognition error",
    ),
]


def ejecutar_pruebas():
    correctas = 0

    for nombre, codigo, fase, fragmento in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)

        for error in resultado["errores"]:
            print(
                f"Error {error['fase']} — "
                f"Línea {error['linea']}, "
                f"columna {error['columna']}: "
                f"{error['mensaje']}"
            )

        if fase is None:
            cumple = (
                resultado["valido"]
                and resultado["arbol"] is not None
                and not resultado["errores"]
            )
        else:
            cumple = (
                not resultado["valido"]
                and resultado["arbol"] is None
                and any(
                    error["fase"] == fase
                    and fragmento in error["mensaje"]
                    for error in resultado["errores"]
                )
            )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", fragmento or "un programa válido")

    # Verificar también los tipos que recibirá el backend.
    print("\n--- Tipos de texto disponibles para el backend ---")

    resultado = analizar_programa("""
fn main() {
    let letra = 'A';
    let texto = "Hola";
}
""")

    tipos = {
        simbolo["nombre"]: simbolo["tipo"]
        for simbolo in resultado["simbolos"].values()
    }

    if resultado["valido"] and tipos == {
        "letra": "char",
        "texto": "String",
    }:
        correctas += 1
        print("Prueba OK")
    else:
        print("PRUEBA FALLIDA")
        print("Tipos recibidos:", tipos)

    total = len(PRUEBAS) + 1
    print(f"\nResultado: {correctas}/{total} pruebas OK")

    if correctas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()