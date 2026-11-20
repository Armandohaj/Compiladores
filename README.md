# RustiQ

RustiQ es un compilador universitario hecho en Python con ANTLR4. Analiza código
RustiQ, genera módulos WebAssembly reales y ofrece un editor web y ejecutores de
escritorio.

## Requisitos

- Python 3.10 o posterior.
- Windows PowerShell para los comandos de esta guía.
- Un navegador moderno con soporte WebAssembly para usar el editor.

## Instalación en Windows

Desde la raíz del repositorio:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-editor-web.txt -r requirements-wasm.txt
```

## Editor web

```powershell
python app.py
```

Abrí `http://127.0.0.1:5000` en el navegador. El editor permite cargar un
archivo, analizarlo, compilarlo, ejecutar el módulo y descargar `programa.wasm`.
Los errores léxicos, sintácticos, semánticos o de generación aparecen con línea
y columna.

La ejecución web admite por ahora `main()` sin parámetros que retorne `i32`.
Los valores para `read()` se indican antes de ejecutar, como enteros `i32`
separados por espacios o comas. Las llamadas a `print()` se muestran antes del
resultado. Cada ejecución tiene un límite de tres segundos.

## Ejecutar código RustiQ desde la terminal

```powershell
python .\ejecutar_escritorio.py .\ejemplo.rustiq
python .\ejecutar_escritorio.py .\ejemplo.rustiq --entrada 15 --entrada 22
```

El comando genera el archivo `.wasm` junto al fuente, ejecuta `main() -> i32`
en un proceso separado y muestra las salidas de `print()` y el resultado final.

## Ejecutar un WASM existente

```powershell
python .\ejecutar_wasm.py .\programa.wasm
python .\ejecutar_wasm.py .\programa.wasm --entrada 15 --entrada 22
```

Este comando lee el binario directamente, sin recompilar el código RustiQ.
También se puede abrir una ventana sencilla con:

```powershell
python .\visor_wasm.py
```

## Pruebas

```powershell
python .\ejecutar_pruebas.py
python -m pytest tests -q
```

Para comprobar que WebAssembly es real, compilá un programa válido desde el
editor, descargá `programa.wasm` y ejecutalo con `ejecutar_wasm.py`. El binario
se valida con Wasmtime y debe mostrar el mismo resultado que el editor.

## Alcance

El frontend reconoce más construcciones que el backend WebAssembly actual.
Las características no generadas devuelven errores controlados; el detalle de
tipos, memoria, arreglos, enums, `match`, ownership y borrowing está en
[`WASM.md`](WASM.md).
