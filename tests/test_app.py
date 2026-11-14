import base64

import wasmtime

from app import app


def test_editor_y_analizar_conservan_su_comportamiento():
    cliente = app.test_client()
    inicio = cliente.get("/")
    analisis = cliente.post(
        "/api/analizar",
        json={"codigo": "fn main() -> i32 { return 1; }"},
    )

    assert inicio.status_code == 200
    assert "RustiQ" in inicio.get_data(as_text=True)
    assert analisis.status_code == 200
    assert analisis.get_json() == {"valido": True, "errores": []}


def test_compilar_devuelve_wasm_base64_valido():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() -> i32 { return 10 + 20; }"},
    )

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["valido"]
    assert datos["errores"] == []
    wasm = base64.b64decode(datos["wasm_base64"], validate=True)
    assert wasm.startswith(b"\x00asm")
    wasmtime.Module(wasmtime.Engine(), wasm)


def test_compilar_informa_programa_invalido_sin_wasm():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() -> i32 { return @; }"},
    )

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert not datos["valido"]
    assert datos["wasm_base64"] is None
    assert any(error["fase"] == "lexico" for error in datos["errores"])


def test_compilar_rechaza_funcionalidad_wasm_no_implementada():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={
            "codigo": """fn main() -> i32 {
    let mut valores = [1];
    valores[0] = 2;
    return valores[0];
}"""
        },
    )

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert not datos["valido"]
    assert datos["wasm_base64"] is None
    assert datos["errores"][0]["fase"] == "generacion"


def test_compilar_requiere_codigo_de_texto():
    cliente = app.test_client()
    respuesta = cliente.post("/api/compilar", json={})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": "Se requiere un campo 'codigo' de texto."}
