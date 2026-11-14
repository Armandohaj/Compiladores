"""Pruebas de while, break, continue y ámbitos de ciclos.

Cada caso compara aceptación o diagnóstico esperado. Los casos inválidos
son éxitos de la prueba cuando se detecta el error correcto. Estas pruebas
no ejecutan el programa RustiQ ni reemplazan las pruebas del backend Wasm.
"""
from main import analizar_programa


# None significa que el programa debe aceptarse.
# Un texto indica parte del error semántico esperado.
PRUEBAS = [
    (
        "While con contador mutable",
        """fn main() -> i32 {
    let mut contador = 0;
    while contador < 3 {
        contador = contador + 1;
    }
    return contador;
}""",
        None,
    ),
    (
        "Condición del while no booleana",
        """fn main() -> i32 {
    while 10 {
        break;
    }
    return 0;
}""",
        "La condición del while debe ser bool",
    ),
    (
        "Break dentro de un ciclo",
        """fn main() -> i32 {
    while true {
        break;
    }
    return 0;
}""",
        None,
    ),
    (
        "Continue dentro de un ciclo",
        """fn main() -> i32 {
    let mut contador = 0;
    while contador < 3 {
        contador = contador + 1;
        continue;
    }
    return contador;
}""",
        None,
    ),
    (
        "Break fuera de un ciclo",
        """fn main() -> i32 {
    break;
    return 0;
}""",
        "'break' solo puede usarse dentro de un ciclo",
    ),
    (
        "Continue fuera de un ciclo",
        """fn main() -> i32 {
    continue;
    return 0;
}""",
        "'continue' solo puede usarse dentro de un ciclo",
    ),
    (
        "Inicialización únicamente dentro del while",
        """fn main() -> i32 {
    let mut resultado: i32;
    while false {
        resultado = 10;
    }
    return resultado;
}""",
        "antes de inicializarla",
    ),
    (
        "Variable local del ciclo fuera de ámbito",
        """fn main() -> i32 {
    while false {
        let local = 10;
    }
    return local;
}""",
        "no está declarada",
    ),
    (
        "Modificación sin mut",
        """fn main() -> i32 {
    let contador = 0;
    while contador < 3 {
        contador = contador + 1;
    }
    return contador;
}""",
        "no fue declarada con 'mut'",
    ),
    (
        "Inicialización de variable externa sin mut",
        """fn main() -> i32 {
    let resultado: i32;
    while false {
        resultado = 10;
    }
    return 0;
}""",
        "debe declararse con 'mut'",
    ),
    (
        "Variable local inicializada en cada iteración",
        """fn main() -> i32 {
    let mut contador = 0;
    while contador < 3 {
        let local: i32;
        local = contador;
        contador = contador + 1;
    }
    return contador;
}""",
        None,
    ),
    (
        "Retorno únicamente dentro del while",
        """fn main() -> i32 {
    while false {
        return 1;
    }
}""",
        "en todos los caminos",
    ),
    (
        "Ciclos anidados",
        """fn main() -> i32 {
    let mut contador = 0;
    while contador < 3 {
        while true {
            break;
        }
        contador = contador + 1;
        continue;
    }
    return contador;
}""",
        None,
    ),
    (
        "Break después de terminar el ciclo",
        """fn main() -> i32 {
    while false {
        break;
    }
    break;
    return 0;
}""",
        "'break' solo puede usarse dentro de un ciclo",
    ),
    (
        "Break dentro de un if dentro del ciclo",
        """fn main() -> i32 {
    let mut contador = 0;
    while contador < 10 {
        if contador == 3 {
            break;
        }
        contador = contador + 1;
    }
    return contador;
}""",
        None,
    ),
    (
        "Inicialización posterior al ciclo",
        """fn main() -> i32 {
    let mut resultado: i32;
    while false {
        resultado = 10;
    }
    resultado = 20;
    return resultado;
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

                # No basta con que exista cualquier error:
                # debe aparecer el error semántico esperado.
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