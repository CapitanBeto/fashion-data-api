"""
GUI mínima de escritorio (Tkinter, sin dependencias gráficas externas) para
pegar una lista tipo:

    ayllenoliver — Fashion influencer Chile (ranking Modash/Heepsy)
    stodakwrld — Handle visto en TikTok para marca Stodak (CL) ...

extraer solo el username (lo que va antes del "—") y enviarlo como un único
request múltiple a POST /instagram/profiles de la API.

Requisitos:
    pip install requests
"""

import json
import os
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000/instagram/profiles")


def extract_username(line: str) -> str | None:
    """De una línea 'username — descripción...' devuelve solo 'username'."""
    line = line.strip()
    if not line:
        return None

    # Formato esperado: separador em-dash "—"
    if "—" in line:
        username = line.split("—", 1)[0].strip()
    else:
        # fallback: si no hay "—", toma la primera palabra de la línea
        parts = line.split()
        username = parts[0] if parts else ""

    username = username.strip().lstrip("@")
    return username or None


def extract_usernames(text: str) -> list[str]:
    usernames = []
    for raw_line in text.splitlines():
        username = extract_username(raw_line)
        if username and username not in usernames:
            usernames.append(username)
    return usernames


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Enviar perfiles a la API")
        self.geometry("640x560")
        self.minsize(480, 400)

        tk.Label(
            self,
            text="Pega la lista (una entrada por línea, formato 'username — descripción'):",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 4))

        self.input_box = scrolledtext.ScrolledText(self, height=16, wrap="word")
        self.input_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        controls = tk.Frame(self)
        controls.pack(fill="x", padx=10, pady=(0, 6))

        tk.Label(controls, text="API URL:").pack(side="left")
        self.api_url_var = tk.StringVar(value=API_URL)
        tk.Entry(controls, textvariable=self.api_url_var, width=40).pack(
            side="left", padx=(4, 12), fill="x", expand=True
        )

        self.approved_var = tk.BooleanVar(value=True)
        tk.Checkbutton(controls, text="approved", variable=self.approved_var).pack(side="left")

        self.submit_btn = tk.Button(self, text="Enviar", command=self.on_submit)
        self.submit_btn.pack(pady=(0, 10))

        tk.Label(self, text="Resultado:", anchor="w").pack(fill="x", padx=10)
        self.output_box = scrolledtext.ScrolledText(self, height=10, wrap="word", state="disabled")
        self.output_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _set_output(self, text: str) -> None:
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.insert("1.0", text)
        self.output_box.configure(state="disabled")

    def on_submit(self):
        raw_text = self.input_box.get("1.0", "end")
        usernames = extract_usernames(raw_text)

        if not usernames:
            messagebox.showwarning("Sin usernames", "No se encontró ningún username en el texto pegado.")
            return

        self._set_output(
            "Usernames detectados (" + str(len(usernames)) + "):\n"
            + "\n".join(usernames)
            + "\n\nEnviando..."
        )
        self.submit_btn.configure(state="disabled")

        threading.Thread(
            target=self._send_request,
            args=(usernames, self.api_url_var.get().strip(), self.approved_var.get()),
            daemon=True,
        ).start()

    def _send_request(self, usernames: list[str], api_url: str, approved: bool):
        payload = {"usernames": usernames, "approved": approved}
        try:
            response = requests.post(api_url, json=payload, timeout=600)
            body = response.text
            try:
                body = json.dumps(response.json(), ensure_ascii=False, indent=2)
            except ValueError:
                pass

            result_text = (
                f"Usernames enviados ({len(usernames)}):\n"
                + "\n".join(usernames)
                + f"\n\nStatus: {response.status_code}\nRespuesta:\n{body}"
            )
        except requests.RequestException as exc:
            result_text = (
                f"Usernames que se intentaron enviar ({len(usernames)}):\n"
                + "\n".join(usernames)
                + f"\n\nError al conectar con la API:\n{exc}"
            )

        self.after(0, self._finish_request, result_text)

    def _finish_request(self, result_text: str):
        self._set_output(result_text)
        self.submit_btn.configure(state="normal")


if __name__ == "__main__":
    App().mainloop()
