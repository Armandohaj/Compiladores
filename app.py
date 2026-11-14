import base64

from flask import Flask, jsonify, render_template, request

from generador_wasm import compilar_programa
from main import analizar_programa


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/analizar")
def analizar():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or not isinstance(datos.get("codigo"), str):
        return jsonify({"error": "Se requiere un campo 'codigo' de texto."}), 400

    resultado = analizar_programa(datos["codigo"])
    return jsonify({
        "valido": resultado["valido"],
        "errores": resultado["errores"],
    })


@app.post("/api/compilar")
def compilar():
    """Compila RustiQ a Wasm y entrega el binario codificado para JSON."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or not isinstance(datos.get("codigo"), str):
        return jsonify({"error": "Se requiere un campo 'codigo' de texto."}), 400

    resultado = compilar_programa(datos["codigo"])
    wasm_base64 = None
    if resultado["valido"]:
        # Base64 permite transportar el binario Wasm sin ejecutar código en Flask.
        wasm_base64 = base64.b64encode(resultado["wasm"]).decode("ascii")

    return jsonify({
        "valido": resultado["valido"],
        "errores": resultado["errores"],
        "wasm_base64": wasm_base64,
    })


if __name__ == "__main__":
    app.run(debug=True)
