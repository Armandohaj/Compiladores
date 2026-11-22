"""Interfaz de escritorio para ejecutar módulos WebAssembly ya compilados."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from ejecutar_wasm import (
    cargar_modulo,
    entradas_desde_texto,
    ejecutar_main_con_entradas,
    verificar_firma_main,
    verificar_importaciones,
)


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
    compatible, mensaje = verificar_importaciones(modulo)
    if not compatible:
        raise ValueError(mensaje)
    return wasm


class VisorWasm:
    """Ventana mínima que conserva en memoria el módulo seleccionado."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.wasm = None
        self.ruta = tk.StringVar(value="No se ha seleccionado un archivo .wasm")
        self.entradas = tk.StringVar()

        ventana.title("RustiQ - Ejecutor de escritorio")
        ventana.minsize(640, 440)
        ventana.configure(background="#f4f6f8")

        estilo = ttk.Style(ventana)
        estilo.theme_use("clam")
        estilo.configure(
            "Archivo.TButton",
            background="#e8eef5",
            foreground="#1f2937",
            borderwidth=0,
            padding=(14, 9),
            font=("Segoe UI", 10, "bold"),
        )
        estilo.map("Archivo.TButton", background=[("active", "#d9e4f0")])
        estilo.configure(
            "Ejecutar.TButton",
            background="#2563eb",
            foreground="white",
            borderwidth=0,
            padding=(18, 9),
            font=("Segoe UI", 10, "bold"),
        )
        estilo.map(
            "Ejecutar.TButton",
            background=[("active", "#1d4ed8"), ("disabled", "#a8b8d8")],
            foreground=[("disabled", "#eef3ff")],
        )

        marco = tk.Frame(ventana, background="#f4f6f8", padx=28, pady=24)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(1, weight=1)

        encabezado = tk.Frame(marco, background="#f4f6f8")
        encabezado.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        tk.Label(
            encabezado,
            text="RustiQ",
            background="#f4f6f8",
            foreground="#172033",
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            encabezado,
            text="Ejecutor de WebAssembly",
            background="#f4f6f8",
            foreground="#64748b",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 0))

        contenido = tk.Frame(marco, background="white", padx=24, pady=22, highlightthickness=1,
                             highlightbackground="#e2e8f0")
        contenido.grid(row=1, column=0, sticky="nsew")
        contenido.columnconfigure(0, weight=1)
        contenido.rowconfigure(8, weight=1)

        tk.Label(
            contenido,
            text="Archivo WebAssembly",
            background="white",
            foreground="#334155",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.boton_abrir = ttk.Button(
            contenido,
            text="Seleccionar archivo .wasm",
            command=self.abrir_archivo,
            style="Archivo.TButton",
        )
        self.boton_abrir.grid(row=1, column=0, sticky="w", pady=(8, 10))
        tk.Label(
            contenido,
            textvariable=self.ruta,
            anchor="w",
            justify="left",
            wraplength=560,
            background="#f8fafc",
            foreground="#475569",
            font=("Segoe UI", 9),
            padx=12,
            pady=10,
            relief="solid",
            borderwidth=1,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 18))

        tk.Label(
            contenido,
            text="Entradas i32",
            background="white",
            foreground="#334155",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=3, column=0, sticky="w")
        tk.Label(
            contenido,
            text="Separá los valores con espacios o comas.",
            background="white",
            foreground="#64748b",
            font=("Segoe UI", 9),
        ).grid(row=4, column=0, sticky="w", pady=(2, 6))
        self.campo_entradas = ttk.Entry(contenido, textvariable=self.entradas, font=("Segoe UI", 10))
        self.campo_entradas.grid(row=5, column=0, sticky="ew", pady=(0, 14), ipady=5)
        self.boton_ejecutar = ttk.Button(
            contenido,
            text="Ejecutar",
            command=self.ejecutar,
            state="disabled",
            style="Ejecutar.TButton",
        )
        self.boton_ejecutar.grid(row=6, column=0, sticky="w", pady=(0, 18))

        tk.Label(
            contenido,
            text="Resultados",
            background="white",
            foreground="#334155",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=7, column=0, sticky="w", pady=(0, 7))
        self.resultados = ScrolledText(
            contenido,
            height=9,
            state="disabled",
            wrap="word",
            background="#f8fafc",
            foreground="#1e293b",
            borderwidth=1,
            relief="solid",
            font=("Consolas", 10),
            padx=10,
            pady=9,
        )
        self.resultados.grid(row=8, column=0, sticky="nsew")

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
        try:
            entradas = entradas_desde_texto(self.entradas.get())
        except ValueError as error:
            self.mostrar_mensaje(str(error))
            return
        wasm = self.wasm
        self.boton_abrir.configure(state="disabled")
        self.boton_ejecutar.configure(state="disabled")
        self.campo_entradas.configure(state="disabled")
        self.mostrar_mensaje("Ejecutando main()…")
        threading.Thread(
            target=self._ejecutar_en_segundo_plano,
            args=(wasm, entradas),
            daemon=True,
        ).start()

    def _ejecutar_en_segundo_plano(self, wasm, entradas):
        try:
            valor, salidas, resultado = ejecutar_main_con_entradas(wasm, entradas, detalles=True)
            lineas = [
                *(f"Salida: {salida}" for salida in salidas),
            ]
            lineas.append(resultado)
            mensaje = "\n".join(lineas)
        except (RuntimeError, TimeoutError) as error:
            mensaje = f"Error de ejecución: {error}"
        # Tkinter solo se actualiza desde su hilo principal.
        self.ventana.after(0, self._terminar_ejecucion, mensaje)

    def _terminar_ejecucion(self, mensaje):
        self.mostrar_mensaje(mensaje)
        self.boton_abrir.configure(state="normal")
        self.campo_entradas.configure(state="normal")
        if self.wasm is not None:
            self.boton_ejecutar.configure(state="normal")


def main():
    ventana = tk.Tk()
    VisorWasm(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
