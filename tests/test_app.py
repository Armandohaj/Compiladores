# Suite de integración: API del editor y transporte de binarios. Los casos usan archivos o
# instancias de prueba para aislar resultados.
import base64
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest
import wasmtime

from app import app
from ejecutar_wasm import ejecutar_archivo_wasm


def test_editor_y_analizar_conservan_su_comportamiento():
    # Objetivo: editor y analizar conservan su comportamiento. Usa el cliente de pruebas
    # HTTP; no equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar devuelve wasm base64 valido. Usa el cliente de pruebas HTTP; no
    # equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar informa programa invalido sin wasm. Usa el cliente de pruebas HTTP;
    # no equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar admite asignacion a elemento de arreglo. Usa el cliente de pruebas
    # HTTP; no equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar admite constantes globales. Usa el cliente de pruebas HTTP; no
    # equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar read y print entrega importaciones wasm. Comprueba resultados o
    # errores de ejecución mediante las funciones o procesos invocados en esta prueba.
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
    # Objetivo: compilar informa firma main no ejecutable en el editor. Usa el cliente de
    # pruebas HTTP; no equivale a una demostración manual en un navegador.
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
    # Objetivo: compilar requiere codigo de texto. Usa el cliente de pruebas HTTP; no
    # equivale a una demostración manual en un navegador.
    cliente = app.test_client()
    respuesta = cliente.post("/api/compilar", json={})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": "Se requiere un campo 'codigo' de texto."}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_descarta_analisis_obsoletos_e_invalida_al_cambiar_o_cargar():
    # Objetivo: editor descarta analisis obsoletos e invalida al cambiar o cargar. Lanza el
    # comando como proceso externo y comprueba su respuesta; necesita las herramientas de su
    # plataforma.
    script = r'''
const fs = require("fs");
const vm = require("vm");
const elementos = {};
function crearElemento(valor = "") {
  return {
    value: valor, textContent: "", className: "", hidden: false, disabled: false,
    children: [], listeners: {}, files: [], scrollTop: 0,
    addEventListener(nombre, funcion) { this.listeners[nombre] = funcion; },
    replaceChildren() { this.children = []; },
    append(item) { this.children.push(item); },
  };
}
for (const id of ["codigo", "lineas", "analizar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
  elementos[id] = crearElemento(id === "codigo" ? "viejo" : "");
}
const resolutores = [];
const contexto = {
  document: {
    querySelector(selector) { return elementos[selector.slice(1)]; },
    createElement() { return crearElemento(); },
  },
  fetch() { return new Promise((resolver) => resolutores.push(resolver)); },
  window: { setTimeout() { return 0; }, clearTimeout() {} },
  FileReader: class {
    readAsText() { this.result = "cargado"; this.onload(); }
  },
  atob() {}, Blob: class {}, URL: {}, Worker: class {}, console,
};
vm.createContext(contexto);
const fuente = fs.readFileSync("static/js/editor.js", "utf8");
vm.runInContext(`${fuente}\nglobalThis.probar = { analizar };`, contexto);
const respuesta = (valido) => ({ ok: true, json: async () => ({ valido, errores: [] }) });

(async () => {
  const primera = contexto.probar.analizar();
  elementos.codigo.value = "nuevo";
  elementos.codigo.listeners.input();
  resolutores.shift()(respuesta(true));
  await primera;
  if (elementos.estado.className === "correcto") throw new Error("Mostró un análisis antiguo.");

  elementos.estado.className = "correcto";
  elementos.archivo.files = [{}];
  elementos.archivo.listeners.change();
  if (elementos.estado.className === "correcto" || elementos.codigo.value !== "cargado") {
    throw new Error("La carga no invalidó el resultado anterior.");
  }

  elementos.codigo.value = "uno";
  elementos.codigo.listeners.input();
  const antigua = contexto.probar.analizar();
  elementos.codigo.value = "dos";
  elementos.codigo.listeners.input();
  const reciente = contexto.probar.analizar();
  const resolverAntiguo = resolutores.shift();
  const resolverReciente = resolutores.shift();
  resolverReciente(respuesta(true));
  await reciente;
  resolverAntiguo(respuesta(false));
  await antigua;
  if (elementos.estado.className !== "correcto") throw new Error("Una respuesta fuera de orden reemplazó la reciente.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
'''

    resultado = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
