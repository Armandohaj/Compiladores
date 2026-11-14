"""Ejecuta todas las suites pruebas_*.py con el mismo Python del proyecto.

Uso: python ejecutar_pruebas.py
Cada suite corre en un proceso separado, igual que al lanzarla a mano.
"""
from pathlib import Path
import re
import subprocess
import sys


def ejecutar():
    carpeta = Path(__file__).resolve().parent
    suites = sorted(carpeta.glob("pruebas_*.py"))
    fallos = 0
    correctas = 0
    total = 0
    if not suites:
        print("No se encontraron archivos pruebas_*.py.")
        return 1

    for suite in suites:
        proceso = subprocess.run(
            [sys.executable, str(suite)],
            cwd=carpeta,
            capture_output=True,
            text=True,
        )
        resumen = re.search(r"Resultado:\s*(\d+)/(\d+) pruebas OK", proceso.stdout)
        if resumen:
            correctas += int(resumen.group(1))
            total += int(resumen.group(2))
        if proceso.returncode != 0 or resumen is None:
            fallos += 1
            print(f"{suite.name}: FALLO")
            print(proceso.stdout)
            print(proceso.stderr)
        else:
            print(f"{suite.name}: {resumen.group(0)}")

    print(f"\nTotal: {correctas}/{total} comprobaciones; {len(suites)} suites; {fallos} suites con fallos.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())
