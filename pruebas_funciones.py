from main import analizar_programa


# Cada prueba incluye:
# 1. Nombre.
# 2. Código RustiQ.
# 3. Fragmento del error esperado, o None si debe ser válido.
PRUEBAS = [
    (
        "Suma con dos parámetros",
        """
        fn sumar(a: i32, b: i32) -> i32 {
            return a + b;
        }

        fn main() -> i32 {
            return sumar(10, 20);
        }
        """,
        None,
    ),
    (
        "Llamada a función declarada después",
        """
        fn main() -> i32 {
            return obtener();
        }

        fn obtener() -> i32 {
            return 42;
        }
        """,
        None,
    ),
    (
        "Llamadas anidadas",
        """
        fn sumar(a: i32, b: i32) -> i32 {
            return a + b;
        }

        fn main() -> i32 {
            return sumar(sumar(1, 2), 3);
        }
        """,
        None,
    ),
    (
        "Llamada dentro de una operación",
        """
        fn doble(numero: i32) -> i32 {
            return numero * 2;
        }

        fn main() -> i32 {
            return doble(5) + 10;
        }
        """,
        None,
    ),
    (
        "Parámetros f64 y bool",
        """
        fn elegir(valor: f64, activo: bool) -> f64 {
            if activo {
                return valor;
            } else {
                return 0.0;
            }
        }

        fn main() -> f64 {
            return elegir(2.5, true);
        }
        """,
        None,
    ),
    (
        "Parámetro mutable",
        """
        fn incrementar(mut numero: i32) -> i32 {
            numero = numero + 1;
            return numero;
        }

        fn main() -> i32 {
            return incrementar(10);
        }
        """,
        None,
    ),
    (
        "Modificación de parámetro sin mut",
        """
        fn incrementar(numero: i32) -> i32 {
            numero = numero + 1;
            return numero;
        }
        """,
        "porque no fue declarada con 'mut'",
    ),
    (
        "Función sin retorno usada como sentencia",
        """
        fn procesar(numero: i32) {
            let copia = numero;
        }

        fn main() -> i32 {
            procesar(10);
            return 0;
        }
        """,
        None,
    ),
    (
        "Resultado de llamada usado como inicializador",
        """
        fn obtener() -> i32 {
            return 10;
        }

        fn main() -> i32 {
            let resultado = obtener();
            return resultado;
        }
        """,
        None,
    ),
    (
        "Recursión",
        """
        fn factorial(numero: i32) -> i32 {
            if numero <= 1 {
                return 1;
            } else {
                return numero * factorial(numero - 1);
            }
        }

        fn main() -> i32 {
            return factorial(5);
        }
        """,
        None,
    ),
    (
        "Comas finales en parámetros y argumentos",
        """
        fn sumar(a: i32, b: i32,) -> i32 {
            return a + b;
        }

        fn main() -> i32 {
            return sumar(1, 2,);
        }
        """,
        None,
    ),
    (
        "Función no declarada",
        """
        fn main() -> i32 {
            return desconocida(10);
        }
        """,
        "La función 'desconocida' no está declarada.",
    ),
    (
        "Faltan argumentos",
        """
        fn sumar(a: i32, b: i32) -> i32 {
            return a + b;
        }

        fn main() -> i32 {
            return sumar(10);
        }
        """,
        "espera 2 argumentos, pero recibió 1",
    ),
    (
        "Sobran argumentos",
        """
        fn obtener() -> i32 {
            return 10;
        }

        fn main() -> i32 {
            return obtener(1);
        }
        """,
        "espera 0 argumentos, pero recibió 1",
    ),
    (
        "Tipo de argumento incorrecto",
        """
        fn identidad(numero: i32) -> i32 {
            return numero;
        }

        fn main() -> i32 {
            return identidad(true);
        }
        """,
        "Argumento 1 de 'identidad': se esperaba i32",
    ),
    (
        "Segundo argumento incorrecto",
        """
        fn sumar(a: i32, b: i32) -> i32 {
            return a + b;
        }

        fn main() -> i32 {
            return sumar(10, 2.5);
        }
        """,
        "Argumento 2 de 'sumar': se esperaba i32",
    ),
    (
        "Funciones duplicadas",
        """
        fn obtener() -> i32 {
            return 1;
        }

        fn obtener() -> i32 {
            return 2;
        }
        """,
        "La función 'obtener' ya fue declarada.",
    ),
    (
        "Parámetros duplicados",
        """
        fn sumar(numero: i32, numero: i32) -> i32 {
            return numero;
        }
        """,
        "El parámetro 'numero' ya fue declarado.",
    ),
    (
        "Variable local con el mismo nombre del parámetro",
        """
        fn identidad(numero: i32) -> i32 {
            let numero = 20;
            return numero;
        }
        """,
        "La variable 'numero' ya fue declarada en este ámbito.",
    ),
    (
        "Parámetro fuera de su función",
        """
        fn identidad(numero: i32) -> i32 {
            return numero;
        }

        fn main() -> i32 {
            return numero;
        }
        """,
        "La variable 'numero' no está declarada.",
    ),
    (
        "Variable utilizada como función",
        """
        fn obtener() -> i32 {
            return 10;
        }

        fn main() -> i32 {
            let obtener = 5;
            return obtener();
        }
        """,
        "'obtener' es una variable y no puede llamarse como función.",
    ),
    (
        "Inicializador con llamada sin valor",
        """
        fn procesar() {
            return;
        }

        fn main() -> i32 {
            let resultado = procesar();
            return 0;
        }
        """,
        "no devuelve un valor",
    ),
    (
        "Variable no declarada dentro de un argumento",
        """
        fn identidad(numero: i32) -> i32 {
            return numero;
        }

        fn main() -> i32 {
            return identidad(desconocida);
        }
        """,
        "La variable 'desconocida' no está declarada.",
    ),
    (
        "Retorno incompatible con el resultado de una llamada",
        """
        fn obtener() -> bool {
            return true;
        }

        fn main() -> i32 {
            return obtener();
        }
        """,
        "Retorno incompatible: se esperaba i32, pero se recibió bool.",
    ),
]


def ejecutar_pruebas():
    correctas = 0

    for nombre, codigo, error_esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        errores = resultado["errores"]

        # Mostrar los errores ayuda a entender
        # qué detectó el compilador.
        for error in errores:
            print(
                f"Error {error['fase']} — "
                f"Línea {error['linea']}, "
                f"columna {error['columna']}: "
                f"{error['mensaje']}"
            )

        if error_esperado is None:
            # Un programa válido debe tener árbol y ningún error.
            cumple = (
                resultado["valido"]
                and not errores
                and resultado["arbol"] is not None
            )
        else:
            # No basta con que falle: debe detectar
            # el error semántico que queremos comprobar.
            cumple = (
                not resultado["valido"]
                and resultado["arbol"] is None
                and any(
                    error["fase"] == "semantico"
                    and error_esperado in error["mensaje"]
                    for error in errores
                )
            )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print(
                "Se esperaba:",
                error_esperado or "un programa válido",
            )

    print(
        f"\nResultado: {correctas}/{len(PRUEBAS)} pruebas OK"
    )

    # Permite identificar un fallo desde la terminal.
    if correctas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()