"""Pruebas de ramas de if y estados de inicialización.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# Cada prueba contiene:
# nombre, programa y fragmento del error esperado.
# None significa que el programa debe aceptarse.
PRUEBAS = [
    (
        "Retorno en ambas ramas",
        """fn main() -> i32 {
    let edad = 20;
    if edad >= 18 {
        return 1;
    } else {
        return 0;
    }
}""",
        None,
    ),
    (
        "Condición que no es bool",
        """fn main() -> i32 {
    if 10 {
        return 1;
    } else {
        return 0;
    }
}""",
        "La condición del if debe ser bool",
    ),
    (
        "Falta retorno en un camino",
        """fn main() -> i32 {
    let activo = true;
    if activo {
        return 1;
    }
}""",
        "en todos los caminos",
    ),
    (
        "Retorno después del if",
        """fn main() -> i32 {
    let activo = true;
    if activo {
        return 1;
    }
    return 0;
}""",
        None,
    ),
    (
        "Cadena else if",
        """fn main() -> i32 {
    let numero = 10;
    if numero > 0 {
        return 1;
    } else if numero == 0 {
        return 0;
    } else {
        return -1;
    }
}""",
        None,
    ),
    (
        "Inicialización en ambas ramas",
        """fn main() -> i32 {
    let activo = true;
    let resultado: i32;
    if activo {
        resultado = 1;
    } else {
        resultado = 2;
    }
    return resultado;
}""",
        None,
    ),
    (
        "Inicialización en una sola rama",
        """fn main() -> i32 {
    let activo = true;
    let resultado: i32;
    if activo {
        resultado = 1;
    }
    return resultado;
}""",
        "antes de inicializarla",
    ),
    (
        "Variable local del if fuera de ámbito",
        """fn main() -> i32 {
    if true {
        let local = 10;
    }
    return local;
}""",
        "no está declarada",
    ),
    (
        "Tipo de retorno incorrecto en else",
        """fn main() -> i32 {
    if true {
        return 1;
    } else {
        return false;
    }
}""",
        "Retorno incompatible",
    ),
    (
        "Una rama retorna y la otra inicializa",
        """fn main() -> i32 {
    let activo = true;
    let resultado: i32;
    if activo {
        return 1;
    } else {
        resultado = 2;
    }
    return resultado;
}""",
        None,
    ),
    (
        "Posible segunda asignación sin mut",
        """fn main() -> i32 {
    let activo = true;
    let resultado: i32;
    if activo {
        resultado = 1;
    }
    resultado = 2;
    return resultado;
}""",
        "no fue declarada con 'mut'",
    ),
    (
        "Asignación posterior permitida con mut",
        """fn main() -> i32 {
    let activo = true;
    let mut resultado: i32;
    if activo {
        resultado = 1;
    }
    resultado = 2;
    return resultado;
}""",
        None,
    ),
    (
        "Una rama no puede inicializar a la otra",
        """fn main() -> i32 {
    let activo = true;
    let resultado: i32;
    if activo {
        resultado = 1;
    } else {
        return resultado;
    }
    return 0;
}""",
        "antes de inicializarla",
    ),
    (
        "Condicionales anidados",
        """fn main() -> i32 {
    let activo = true;
    let numero = 10;
    if activo {
        if numero > 0 {
            return 1;
        } else {
            return 2;
        }
    } else {
        return 0;
    }
}""",
        None,
    ),
]


def ejecutar_pruebas():
    aprobadas = 0

    for nombre, codigo, error_esperado in PRUEBAS:
        print(f"\n--- {nombre} ---")
        resultado = analizar_programa(codigo)
        errores = resultado["errores"]

        try:
            if error_esperado is None:
                assert resultado["valido"], (
                    f"Se esperaba un programa válido: {errores}"
                )
                assert errores == []
                assert resultado["arbol"] is not None
            else:
                assert not resultado["valido"], (
                    "El programa debía ser rechazado."
                )
                assert resultado["arbol"] is None

                # Exigimos el error semántico esperado.
                # Un error sintáctico no debe hacer pasar la prueba.
                assert any(
                    error["fase"] == "semantico"
                    and error_esperado in error["mensaje"]
                    for error in errores
                ), (
                    f"Falta el error '{error_esperado}'. "
                    f"Errores recibidos: {errores}"
                )

            for error in errores:
                print(
                    f"Error {error['fase']} — "
                    f"Línea {error['linea']}, "
                    f"columna {error['columna']}: "
                    f"{error['mensaje']}"
                )

            print("Prueba OK")
            aprobadas += 1

        except AssertionError as error:
            print(f"Prueba FALLÓ: {error}")

    print(f"\nResultado: {aprobadas}/{len(PRUEBAS)} pruebas OK")

    if aprobadas != len(PRUEBAS):
        raise SystemExit(1)


if __name__ == "__main__":
    ejecutar_pruebas()