import base64
import hashlib

import wasmtime

from app import app
from ejecutar_wasm import ejecutar_archivo_wasm


def test_editor_y_analizar_conservan_su_comportamiento():
    cliente = app.test_client()
    inicio = cliente.get("/")
    analisis = cliente.post(
        "/api/analizar",
        json={"codigo": "fn main() -> i32 { return 1; }"},
    )

    assert inicio.status_code == 200
    assert "RustiQ" in inicio.get_data(as_text=True)
    assert 'id="descargar-wasm"' in inicio.get_data(as_text=True)
    assert 'id="entradas"' in inicio.get_data(as_text=True)
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
    assert datos["main"] == {"parametros": [], "retorno": "i32"}
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
    assert datos["main"] is None
    assert any(error["fase"] == "lexico" for error in datos["errores"])


def test_compilar_admite_asignacion_a_elemento_de_arreglo():
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
    assert datos["valido"]
    assert datos["errores"] == []
    assert datos["wasm_base64"] is not None
    assert datos["main"] == {"parametros": [], "retorno": "i32"}


def test_compilar_admite_constantes_globales():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={
            "codigo": """const LIMITE: i32 = 10;
const DOBLE: i32 = LIMITE * 2;
fn main() -> i32 { return DOBLE + 5; }"""
        },
    )

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["valido"]
    assert datos["errores"] == []
    assert datos["wasm_base64"] is not None


def test_compilar_read_y_print_entrega_importaciones_wasm(tmp_path, capsys):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() -> i32 { let x = read(); print(x); return x; }"},
    )

    datos = respuesta.get_json()
    wasm = base64.b64decode(datos["wasm_base64"])
    modulo = wasmtime.Module(wasmtime.Engine(), wasm)
    importaciones = {(item.module, item.name) for item in modulo.imports}
    archivo = tmp_path / "programa.wasm"
    archivo.write_bytes(wasm)
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()

    assert respuesta.status_code == 200
    assert datos["valido"]
    assert importaciones == {("env", "read_i32"), ("env", "print_i32")}
    assert ejecutar_archivo_wasm(archivo, entradas=[37]) == 0
    assert "Salida: 37" in capsys.readouterr().out
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


def test_compilar_informa_firma_main_no_ejecutable_en_el_editor():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() -> bool { return true; }"},
    )

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["valido"]
    assert datos["main"] == {"parametros": [], "retorno": "bool"}


def test_compilar_requiere_codigo_de_texto():
    cliente = app.test_client()
    respuesta = cliente.post("/api/compilar", json={})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": "Se requiere un campo 'codigo' de texto."}
