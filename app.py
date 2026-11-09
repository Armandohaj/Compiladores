from flask import Flask, jsonify, render_template, request

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


if __name__ == "__main__":
    app.run(debug=True)
