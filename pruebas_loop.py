from main import analizar_programa


# None indica que el programa debe ser válido.
# Un texto indica el error semántico esperado.
PRUEBAS = [
    (
        "Loop con contador mutable y break",
        """
fn main() -> i32 {
    let mut contador = 0;
    loop {
        contador = contador + 1;
        if contador == 5 {
            break;
        }
    }
    return contador;
}
""",
        None,
    ),
    (
        "Continue dentro de loop",
        """
fn main() -> i32 {
    let mut contador = 0;
    loop {
        contador = contador + 1;
        if contador < 3 {
            continue;
        }
        break;
    }
    return contador;
}
""",
        None,
    ),
    (
        "Loops anidados",
        """
fn main() -> i32 {
    loop {
        loop {
            break;
        }
        break;
    }
    return 0;
}
""",
        None,
    ),
    (
        "While dentro de loop",
        """
fn main() -> i32 {
    let mut contador = 0;
    loop {
        while contador < 3 {
            contador = contador + 1;
        }
        break;
    }
    return contador;
}
""",
        None,
    ),
    (
        "Loop dentro de while",
        """
fn main() -> i32 {
    let mut contador = 0;
    while contador < 3 {
        loop {
            contador = contador + 1;
            break;
        }
    }
    return contador;
}
""",
        None,
    ),
    (
        "Variable local del loop",
        """
fn main() -> i32 {
    loop {
        let numero: i32;
        numero = 10;
        if numero == 10 {
            break;
        }
    }
    return 0;
}
""",
        None,
    ),
    (
        "Variable local fuera del loop",
        """
fn main() -> i32 {
    loop {
        let local = 10;
        break;
    }
    return local;
}
""",
        "La variable 'local' no está declarada.",
    ),
    (
        "Modificación de variable externa sin mut",
        """
fn main() -> i32 {
    let numero = 0;
    loop {
        numero = 1;
        break;
    }
    return numero;
}
""",
        "porque no fue declarada con 'mut'",
    ),
    (
        "Inicialización externa sin mut",
        """
fn main() -> i32 {
    let numero: i32;
    loop {
        numero = 10;
        break;
    }
    return 0;
}
""",
        "debe declararse con 'mut' para asignarla dentro de un ciclo",
    ),
    (
        "Inicialización al salir aún conservadora",
        """
fn main() -> i32 {
    let mut numero: i32;
    loop {
        numero = 10;
        break;
    }
    return numero;
}
""",
        "La variable 'numero' se usa antes de inicializarla.",
    ),
    (
        "Break después del loop",
        """
fn main() -> i32 {
    loop {
        break;
    }
    break;
    return 0;
}
""",
        "'break' solo puede usarse dentro de un ciclo.",
    ),
    (
        "Continue después del loop",
        """
fn main() -> i32 {
    loop {
        break;
    }
    continue;
    return 0;
}
""",
        "'continue' solo puede usarse dentro de un ciclo.",
    ),
]


def ejecutar_pruebas():
    correctas = 0

    for nombre, codigo, esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)

        for error in resultado["errores"]:
            print(
                f"Error {error['fase']} — "
                f"Línea {error['linea']}, "
                f"columna {error['columna']}: "
                f"{error['mensaje']}"
            )

        if esperado is None:
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
                    error["fase"] == "semantico"
                    and esperado in error["mensaje"]
                    for error in resultado["errores"]
                )
            )

        if cumple:
            correctas += 1
            print("Prueba OK")
        else:
            print("PRUEBA FALLIDA")
            print("Se esperaba:", esperado or "un programa válido")

    print(f"\nResultado: {correctas}/{len(PRUEBAS)} pruebas OK")

    if correctas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()