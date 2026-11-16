"""Interfaz de escritorio para ejecutar módulos WebAssembly ya compilados."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText

from ejecutar_wasm import cargar_modulo, ejecutar_main_con_limite, verificar_firma_main


def cargar_archivo_wasm(ruta_archivo):
    """Lee y valida un .wasm sin modificarlo ni depender del compilador RustiQ."""
    ruta = Path(ruta_archivo)
    try:
        wasm = ruta.read_bytes()
    except OSError as error:
        raise ValueError(f"No se pudo leer '{ruta}': {error}") from error

    try:
        modulo = cargar_modulo(wasm)
    except Exception as error:
        raise ValueError(f"El archivo no es un módulo WebAssembly válido: {error}") from error

    ejecutable, mensaje = verificar_firma_main(modulo)
    if not ejecutable:
        raise ValueError(mensaje)
    return wasm


class VisorWasm:
    """Ventana mínima que conserva en memoria el módulo seleccionado."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.wasm = None
        self.ruta = tk.StringVar(value="No se ha seleccionado un archivo .wasm")

        ventana.title("RustiQ - Ejecutor de escritorio")
        ventana.minsize(560, 300)

        marco = tk.Frame(ventana, padx=16, pady=16)
        marco.pack(fill="both", expand=True)

        self.boton_abrir = tk.Button(marco, text="Abrir archivo", command=self.abrir_archivo)
        self.boton_abrir.pack(anchor="w")
        tk.Label(marco, textvariable=self.ruta, anchor="w", justify="left", wraplength=520).pack(
            fill="x", pady=(8, 12)
        )
        self.boton_ejecutar = tk.Button(
            marco,
            text="Ejecutar",
            command=self.ejecutar,
            state="disabled",
        )
        self.boton_ejecutar.pack(anchor="w")

        tk.Label(marco, text="Resultados").pack(anchor="w", pady=(14, 4))
        self.resultados = ScrolledText(marco, height=10, state="disabled", wrap="word")
        self.resultados.pack(fill="both", expand=True)

    def mostrar_mensaje(self, mensaje):
        """Actualiza el área de salida de forma legible para la demostración."""
        self.resultados.configure(state="normal")
        self.resultados.delete("1.0", tk.END)
        self.resultados.insert(tk.END, mensaje)
        self.resultados.configure(state="disabled")

    def abrir_archivo(self):
        """Selecciona y valida el archivo antes de permitir su ejecución."""
        ruta = filedialog.askopenfilename(
            title="Abrir módulo WebAssembly",
            filetypes=[("WebAssembly", "*.wasm"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return
        try:
            self.wasm = cargar_archivo_wasm(ruta)
        except ValueError as error:
            self.wasm = None
            self.ruta.set("Archivo no válido")
            self.boton_ejecutar.configure(state="disabled")
            self.mostrar_mensaje(str(error))
            return

        self.ruta.set(str(Path(ruta)))
        self.boton_ejecutar.configure(state="normal")
        self.mostrar_mensaje("Archivo listo para ejecutar.")

    def ejecutar(self):
        """Usa un hilo para que la espera del proceso Wasm no bloquee la ventana."""
        if self.wasm is None:
            return
        wasm = self.wasm
        self.boton_abrir.configure(state="disabled")
        self.boton_ejecutar.configure(state="disabled")
        self.mostrar_mensaje("Ejecutando main()…")
        threading.Thread(
            target=self._ejecutar_en_segundo_plano,
            args=(wasm,),
            daemon=True,
        ).start()

    def _ejecutar_en_segundo_plano(self, wasm):
        try:
            valor = ejecutar_main_con_limite(wasm)
            mensaje = f"Resultado de main(): {valor}"
        except (RuntimeError, TimeoutError) as error:
            mensaje = f"Error de ejecución: {error}"
        # Tkinter solo se actualiza desde su hilo principal.
        self.ventana.after(0, self._terminar_ejecucion, mensaje)

    def _terminar_ejecucion(self, mensaje):
        self.mostrar_mensaje(mensaje)
        self.boton_abrir.configure(state="normal")
        if self.wasm is not None:
            self.boton_ejecutar.configure(state="normal")


def main():
    ventana = tk.Tk()
    VisorWasm(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
