# RustiQ

RustiQ es un compilador universitario hecho en Python con ANTLR4. Analiza código
RustiQ, genera módulos WebAssembly reales y ofrece un editor web y ejecutores de
escritorio.

## Requisitos

- Python 3.10 o posterior.
- Windows PowerShell para los comandos de esta guía.
- Un navegador moderno con soporte WebAssembly para usar el editor.

## Instalación en Windows

Cloná el repositorio y entrá en su carpeta:

```powershell
git clone https://github.com/Armandohaj/Compiladores.git
Set-Location .\Compiladores
```

Creá y activá el entorno virtual. Si PowerShell bloquea la activación, ejecutá
primero `Set-ExecutionPolicy -Scope Process Bypass` en esa misma ventana.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-editor-web.txt -r requirements-wasm.txt
```

Ese comando instala ANTLR4, Flask y Wasmtime con las versiones usadas por el
proyecto. Todos los comandos siguientes se ejecutan desde esa misma terminal
con el entorno virtual activo.

## Editor web

```powershell
python app.py
```

Abrí `http://127.0.0.1:5000` en el navegador. El editor permite cargar un
archivo, analizarlo, compilarlo, ejecutar el módulo y descargar `programa.wasm`.
Los errores léxicos, sintácticos, semánticos o de generación aparecen con línea
y columna; al seleccionar un error, el editor lo ubica en el código.

La ejecución web admite `main()` sin parámetros con retorno `i32`, `f64`,
`bool`, `char`, `String`, arreglos, tuplas, estructuras, enums o sin retorno.
Los módulos generados por RustiQ incluyen metadatos de retorno para que el
editor muestre textos y valores compuestos sin confundir sus punteros Wasm con
resultados del programa.
Los valores para `read()` se indican antes de ejecutar, como enteros `i32`
separados por espacios o comas. Las llamadas a `print()` se muestran antes del
resultado. Cada ejecución tiene un límite de tres segundos.

## Ejecutar código RustiQ desde la terminal

```powershell
python .\ejecutar_escritorio.py .\ejemplos\01_aritmetica_funciones.rustiq
python .\ejecutar_escritorio.py .\ejemplo.rustiq --entrada 15 --entrada 22
```

El comando genera el archivo `.wasm` junto al fuente y ejecuta `main()` sin
parámetros en un proceso separado. Muestra las salidas de `print()` y decodifica
el resultado según los metadatos incluidos por RustiQ.

## Ejecutar un WASM existente

El primer comando anterior deja el binario junto al fuente. Podés ejecutar
exactamente ese mismo archivo sin recompilar RustiQ:

```powershell
python .\ejecutar_wasm.py .\ejemplos\01_aritmetica_funciones.wasm
python .\ejecutar_wasm.py .\programa.wasm --entrada 15 --entrada 22
```

Este comando lee el binario directamente, sin recompilar el código RustiQ.
También se puede abrir una ventana sencilla con:

```powershell
python .\visor_wasm.py
```

En la ventana, elegí **Abrir archivo**, seleccioná un `.wasm` generado y pulsá
**Ejecutar**. El visor ejecuta directamente el binario seleccionado; no vuelve
a compilar el archivo RustiQ.

## Ejemplos

Los archivos en `ejemplos\` no requieren entradas y tienen `main() -> i32`, por
lo que se pueden ejecutar en el editor, la terminal y el visor después de
compilarlos:

- `01_aritmetica_funciones.rustiq`: variables, aritmética y funciones. Resultado: `25`.
- `02_ciclo_while.rustiq`: variables mutables y ciclo `while`. Resultado: `10`.
- `03_struct_enum_match.rustiq`: estructura, enum y `match`. Resultado: `7`.

Para probar cualquiera desde la terminal:

```powershell
python .\ejecutar_escritorio.py .\ejemplos\02_ciclo_while.rustiq
python .\ejecutar_wasm.py .\ejemplos\02_ciclo_while.wasm
```

En el editor web, iniciá `python app.py`, abrí `http://127.0.0.1:5000`, usá
**Cargar archivo** para elegir un ejemplo y después pulsá **Compilar** o
**Ejecutar**. La descarga guarda el mismo WASM que produjo la compilación.

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
