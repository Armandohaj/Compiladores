import base64
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest
import wasmtime

from app import app
from ejecutar_wasm import ejecutar_archivo_wasm, ejecutar_main_con_entradas
from generador_wasm import compilar_programa
from visor_wasm import cargar_archivo_wasm


def test_editor_y_analizar_conservan_su_comportamiento():
    cliente = app.test_client()
    inicio = cliente.get("/")
    analisis = cliente.post(
        "/api/analizar",
        json={"codigo": "fn main() -> i32 { return 1; }"},
    )

    assert inicio.status_code == 200
    assert "RustiQ" in inicio.get_data(as_text=True)
    assert 'id="compilar"' in inicio.get_data(as_text=True)
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


def test_compilar_admite_main_unit():
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() { print(10); }"},
    )

    datos = respuesta.get_json()
    wasm = base64.b64decode(datos["wasm_base64"], validate=True)

    assert respuesta.status_code == 200
    assert datos["valido"]
    assert datos["main"] == {"parametros": [], "retorno": "unit"}
    wasmtime.Module(wasmtime.Engine(), wasm)


def test_main_unit_del_editor_se_ejecuta_en_terminal_y_visor(tmp_path, capsys):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/api/compilar",
        json={"codigo": "fn main() { let valor = read(); print(valor); }"},
    )
    datos = respuesta.get_json()
    wasm = base64.b64decode(datos["wasm_base64"], validate=True)
    archivo = tmp_path / "editor-unit.wasm"
    archivo.write_bytes(wasm)
    antes = hashlib.sha256(wasm).hexdigest()

    codigo_salida = ejecutar_archivo_wasm(archivo, entradas=[40])
    salida = capsys.readouterr().out
    wasm_visor = cargar_archivo_wasm(archivo)

    assert datos["valido"]
    assert codigo_salida == 0
    assert "Salida: 40" in salida
    assert "main() finalizó correctamente." in salida
    assert ejecutar_main_con_entradas(wasm_visor, [40]) == (None, [40])
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_descarta_analisis_obsoletos_e_invalida_al_cambiar_o_cargar():
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
for (const id of ["codigo", "lineas", "analizar", "compilar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_compila_sin_ejecutar_y_descarta_respuestas_obsoletas():
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
for (const id of ["codigo", "lineas", "analizar", "compilar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
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
  setImmediate,
  FileReader: class {},
  atob(valor) { return valor === "nuevo" ? "\x02" : "\x01"; },
  Blob: class {}, URL: {}, Worker: class { constructor() { throw new Error("No debe ejecutar."); } }, console,
};
vm.createContext(contexto);
const fuente = fs.readFileSync("static/js/editor.js", "utf8");
vm.runInContext(`${fuente}\nglobalThis.probar = { compilar, wasm: () => wasmCompilado };`, contexto);
const respuesta = (wasm, retorno = "bool") => ({
  ok: true,
  json: async () => ({ valido: true, errores: [], wasm_base64: wasm, main: { parametros: [], retorno } }),
});
const error = () => ({
  ok: true,
  json: async () => ({ valido: false, errores: [{ fase: "generacion", linea: 1, columna: 1, mensaje: "error" }], wasm_base64: null }),
});

(async () => {
  const antigua = contexto.probar.compilar();
  elementos.codigo.value = "nuevo";
  elementos.codigo.listeners.input();
  resolutores.shift()(respuesta("viejo"));
  await antigua;
  if (!elementos["descargar-wasm"].disabled || contexto.probar.wasm() !== null) {
    throw new Error("Conservó una compilación antigua.");
  }

  const reciente = contexto.probar.compilar();
  resolutores.shift()(respuesta("nuevo"));
  await reciente;
  if (elementos["descargar-wasm"].disabled || elementos.estado.className !== "correcto"
      || contexto.probar.wasm()[0] !== 2) {
    throw new Error("No conservó el WASM compilado.");
  }

  const anterior = contexto.probar.compilar();
  const posterior = contexto.probar.compilar();
  const resolverAnterior = resolutores.shift();
  const resolverPosterior = resolutores.shift();
  resolverPosterior(respuesta("nuevo"));
  await posterior;
  resolverAnterior(respuesta("viejo"));
  await anterior;
  if (contexto.probar.wasm()[0] !== 2) {
    throw new Error("Una compilación fuera de orden reemplazó la reciente.");
  }

  elementos.codigo.value = "invalido";
  elementos.codigo.listeners.input();
  const invalida = contexto.probar.compilar();
  resolutores.shift()(error());
  await invalida;
  if (!elementos["descargar-wasm"].disabled || elementos.estado.className !== "error") {
    throw new Error("Presentó una compilación inválida como correcta.");
  }
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_descarta_compilacion_y_ejecucion_solapadas():
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
for (const id of ["codigo", "lineas", "analizar", "compilar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
  elementos[id] = crearElemento(id === "codigo" ? "codigo" : "");
}
const resolutores = [];
const workers = [];
class WorkerFalso {
  constructor() { workers.push(this); }
  postMessage() {}
  terminate() {}
}
const contexto = {
  document: {
    querySelector(selector) { return elementos[selector.slice(1)]; },
    createElement() { return crearElemento(); },
  },
  fetch() { return new Promise((resolver) => resolutores.push(resolver)); },
  window: { setTimeout() { return 0; }, clearTimeout() {} },
  FileReader: class {},
  atob(valor) { return valor === "ejecutar" ? "\x02" : "\x03"; },
  Blob: class {}, URL: {}, Worker: WorkerFalso, console,
};
vm.createContext(contexto);
const fuente = fs.readFileSync("static/js/editor.js", "utf8");
vm.runInContext(`${fuente}\nglobalThis.probar = { compilar, ejecutar, wasm: () => wasmCompilado };`, contexto);
const respuesta = (wasm, retorno = "i32") => ({
  ok: true,
  json: async () => ({ valido: true, errores: [], wasm_base64: wasm, main: { parametros: [], retorno } }),
});
const invalida = () => ({
  ok: true,
  json: async () => ({ valido: false, errores: [{ fase: "generacion", linea: 1, columna: 1, mensaje: "antiguo" }], wasm_base64: null }),
});

(async () => {
  const compilacion = contexto.probar.compilar();
  const ejecucion = contexto.probar.ejecutar();
  const resolverCompilacion = resolutores.shift();
  const resolverEjecucion = resolutores.shift();
  resolverEjecucion(respuesta("ejecutar"));
  await new Promise((resolver) => setImmediate(resolver));
  resolverCompilacion(invalida());
  await compilacion;
  workers[0].onmessage({ data: { valor: 7, salidas: [] } });
  await ejecucion;
  if (elementos.estado.textContent !== "Resultado de main(): 7" || contexto.probar.wasm()[0] !== 2
      || elementos.compilar.disabled || elementos.ejecutar.disabled) {
    throw new Error("La compilación antigua reemplazó la ejecución reciente.");
  }

  const ejecucionAntigua = contexto.probar.ejecutar();
  const resolverEjecucionAntigua = resolutores.shift();
  resolverEjecucionAntigua(respuesta("ejecutar"));
  await new Promise((resolver) => setImmediate(resolver));
  const compilacionReciente = contexto.probar.compilar();
  const resolverCompilacionReciente = resolutores.shift();
  resolverCompilacionReciente(respuesta("compilar", "bool"));
  await compilacionReciente;
  workers[1].onmessage({ data: { valor: 9, salidas: [] } });
  await ejecucionAntigua;
  if (elementos.estado.textContent !== "La compilación fue correcta." || elementos.estado.className !== "correcto"
      || contexto.probar.wasm()[0] !== 3 || elementos.compilar.disabled || elementos.ejecutar.disabled) {
    throw new Error("La ejecución antigua reemplazó la compilación reciente.");
  }
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_ejecuta_main_unit_sin_mostrar_valor_inexistente():
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
for (const id of ["codigo", "lineas", "analizar", "compilar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
  elementos[id] = crearElemento(id === "codigo" ? "fn main() {}" : "");
}
const workers = [];
class WorkerFalso {
  constructor() { workers.push(this); }
  postMessage() { this.onmessage({ data: { salidas: [37], resultado: "main() finalizó correctamente." } }); }
  terminate() {}
}
const contexto = {
  document: {
    querySelector(selector) { return elementos[selector.slice(1)]; },
    createElement() { return crearElemento(); },
  },
  fetch: async () => ({
    ok: true,
    json: async () => ({
      valido: true, errores: [], wasm_base64: "x",
      main: { parametros: [], retorno: "unit" },
    }),
  }),
  window: { setTimeout() { return 0; }, clearTimeout() {} },
  FileReader: class {}, atob() { return "\x01"; }, Blob: class {}, URL: {}, Worker: WorkerFalso, console,
};
vm.createContext(contexto);
const fuente = fs.readFileSync("static/js/editor.js", "utf8");
vm.runInContext(`${fuente}\nglobalThis.probar = { ejecutar };`, contexto);
(async () => {
  await contexto.probar.ejecutar();
  if (elementos.estado.textContent !== "Salida: 37\nmain() finalizó correctamente."
      || elementos.estado.textContent.includes("undefined") || workers.length !== 1) {
    throw new Error("No informó correctamente la ejecución unit.");
  }
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("fn main() -> f64 { 1.5 }", "Resultado de main(): 1.5"),
        ("fn main() -> bool { true }", "Resultado de main(): true"),
        ("fn main() -> char { 'ñ' }", "Resultado de main(): 'ñ'"),
        (r"fn main() -> char { '\n' }", r"Resultado de main(): '\n'"),
        (r"fn main() -> char { '\t' }", r"Resultado de main(): '\t'"),
        (r"fn main() -> char { '\r' }", r"Resultado de main(): '\r'"),
        (r'''fn main() -> char { '\'' }''', r"Resultado de main(): '\''"),
        (r"fn main() -> char { '\\' }", r"Resultado de main(): '\\'"),
        ('fn main() -> String { "hola" }', 'Resultado de main(): "hola"'),
        ("fn main() -> (i32, bool) { (7, true) }", "Resultado de main(): [7,true]"),
        (
            "struct Punto { x: i32 } fn main() -> Punto { Punto { x: 7 } }",
            'Resultado de main(): {"x":7}',
        ),
        (
            "enum Estado { Valor(i32), Vacio } fn main() -> Estado { Estado::Valor(7) }",
            'Resultado de main(): {"enum":"Estado","variante":"Valor","datos":[7]}',
        ),
        (
            "fn main() -> [[i32; 2]; 2] { [[1, 2], [3, 4]] }",
            "Resultado de main(): [[1,2],[3,4]]",
        ),
    ],
)
def test_worker_web_decodifica_retornos_rustiq(codigo, esperado):
    resultado_compilacion = compilar_programa(codigo)
    wasm_base64 = base64.b64encode(resultado_compilacion["wasm"]).decode("ascii")
    script = f'''
const fs = require("fs");
const vm = require("vm");
let salida = null;
const contexto = {{
  self: {{ postMessage(datos) {{ salida = datos; }} }},
  WebAssembly, Uint8Array, DataView, TextDecoder, JSON, Error, Number, Array, Object, String,
}};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync("static/js/ejecutor-wasm.js", "utf8"), contexto);
(async () => {{
  const bytes = Uint8Array.from(Buffer.from("{wasm_base64}", "base64"));
  await contexto.self.onmessage({{ data: {{ wasm: bytes.buffer, entradas: [] }} }});
  if (!salida || salida.error || salida.resultado !== {esperado!r}) {{
    throw new Error(JSON.stringify(salida));
  }}
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
'''

    resultado = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado_compilacion["valido"]
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_worker_web_distingue_metadatos_ausentes_de_metadatos_invalidos():
    sin_metadatos = base64.b64encode(wasmtime.wat2wasm(
        '(module (func (export "main") (result i32) i32.const 30))'
    )).decode("ascii")
    sin_memoria = base64.b64encode(wasmtime.wat2wasm(
        '(module (global (export "__rustiq-main-metadata") i32 (i32.const 0)) '
        '(func (export "main") (result i32) i32.const 1))'
    )).decode("ascii")
    metadatos_invalidos = base64.b64encode(wasmtime.wat2wasm(
        '(module (memory (export "memory") 1) '
        '(global (export "__rustiq-main-metadata") i32 (i32.const 0)) '
        '(data (i32.const 0) "\\08\\00\\00\\00\\01\\00\\00\\00x") '
        '(func (export "main") (result i32) i32.const 1))'
    )).decode("ascii")
    script = f'''
const fs = require("fs");
const vm = require("vm");
let salida = null;
const contexto = {{
  self: {{ postMessage(datos) {{ salida = datos; }} }},
  WebAssembly, Uint8Array, DataView, TextDecoder, JSON, Error, Number, Array, Object, String,
}};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync("static/js/ejecutor-wasm.js", "utf8"), contexto);
(async () => {{
  await contexto.self.onmessage({{ data: {{ wasm: Uint8Array.from(Buffer.from("{sin_metadatos}", "base64")).buffer, entradas: [] }} }});
  if (!salida || salida.error || salida.resultado !== "Resultado de main(): 30") throw new Error(JSON.stringify(salida));
  await contexto.self.onmessage({{ data: {{ wasm: Uint8Array.from(Buffer.from("{sin_memoria}", "base64")).buffer, entradas: [] }} }});
  if (!salida || !salida.error || !salida.error.includes("declara metadatos RustiQ pero no expone la memoria requerida")) {{
    throw new Error(JSON.stringify(salida));
  }}
  await contexto.self.onmessage({{ data: {{ wasm: Uint8Array.from(Buffer.from("{metadatos_invalidos}", "base64")).buffer, entradas: [] }} }});
  if (!salida || !salida.error || !salida.error.includes("metadatos de retorno del módulo no son compatibles")) {{
    throw new Error(JSON.stringify(salida));
  }}
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
'''

    resultado = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está disponible.")
def test_editor_localiza_errores_e_invalida_posiciones_antiguas():
    script = r'''
const fs = require("fs");
const vm = require("vm");
const elementos = {};
function crearElemento(valor = "") {
  return {
    value: valor, textContent: "", className: "", hidden: false, disabled: false,
    children: [], listeners: {}, files: [], scrollTop: 0, inicio: null, fin: null, enfocado: false,
    addEventListener(nombre, funcion) { this.listeners[nombre] = funcion; },
    replaceChildren() { this.children = []; },
    append(item) { this.children.push(item); },
    focus() { this.enfocado = true; },
    setSelectionRange(inicio, fin) { this.inicio = inicio; this.fin = fin; },
  };
}
for (const id of ["codigo", "lineas", "analizar", "compilar", "ejecutar", "descargar-wasm", "entradas", "archivo", "estado", "errores"]) {
  elementos[id] = crearElemento(id === "codigo" ? "uno\ndos\ntres" : "");
}
const contexto = {
  document: {
    querySelector(selector) { return elementos[selector.slice(1)]; },
    createElement() { return crearElemento(); },
  },
  window: { setTimeout() { return 0; }, clearTimeout() {} },
  FileReader: class {}, atob() {}, Blob: class {}, URL: {}, Worker: class {}, console,
};
vm.createContext(contexto);
const fuente = fs.readFileSync("static/js/editor.js", "utf8");
vm.runInContext(`${fuente}\nglobalThis.probar = { mostrarResultado };`, contexto);
const resultado = { valido: false, errores: [
  { fase: "lexico", linea: 2, columna: 2, mensaje: "error" },
  { fase: "sintactico", linea: 99, columna: 99, mensaje: "final" },
] };
contexto.probar.mostrarResultado(resultado);
elementos.errores.children[0].listeners.click();
if (!elementos.codigo.enfocado || elementos.codigo.inicio !== 5 || elementos.codigo.fin !== 6) {
  throw new Error("No localizó la línea y columna del error.");
}
elementos.errores.children[1].listeners.click();
if (elementos.codigo.inicio !== 12 || elementos.codigo.fin !== 12) {
  throw new Error("No limitó la posición al final del archivo.");
}
const errorAntiguo = elementos.errores.children[0];
elementos.codigo.value = "nuevo";
elementos.codigo.listeners.input();
errorAntiguo.listeners.click();
if (elementos.codigo.inicio !== 12 || elementos.codigo.fin !== 12 || !elementos.errores.hidden) {
  throw new Error("Una ubicación antigua siguió activa después de modificar el código.");
}
'''

    resultado = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
