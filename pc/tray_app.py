#!/usr/bin/env python3
"""
Heli Controller – okno a ikona v liště (Windows).

Uživatel: spustí aplikaci, zkontroluje se, že je vše připravené, a stiskne Start.
Vše ostatní (firewall, ViGEmBus, spuštění s Windows) jde nastavit tlačítky v okně.
"""

from __future__ import annotations

import ctypes
import logging
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import receiver
from receiver import Bridge, local_ip

APP_NAME = "HeliController"
FIREWALL_RULE = "HeliController UDP"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOG_DIR = Path.home() / "AppData" / "Local" / APP_NAME
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "log.txt",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("heli")

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW – neotvírat černé okno konzole


def run_hidden(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, creationflags=NO_WINDOW)


# ---------------------------------------------------------------------------
# Kontroly systému
# ---------------------------------------------------------------------------

def vigem_installed() -> bool:
    """ViGEmBus je služba; `sc query` vrátí 0, pokud existuje."""
    return run_hidden(["sc", "query", "ViGEmBus"]).returncode == 0


def firewall_rule_exists() -> bool:
    return run_hidden(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE}"]
    ).returncode == 0


def fix_firewall_elevated(port: int) -> bool:
    """Přidá pravidlo do firewallu. Windows zobrazí UAC dialog (uživatel musí potvrdit)."""
    params = (
        f'advfirewall firewall add rule name="{FIREWALL_RULE}" dir=in action=allow '
        f"protocol=UDP localport={port} profile=private"
    )
    # 1 = SW_SHOWNORMAL; "runas" vyžádá zvýšená práva přes UAC
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", params, None, 0)
    return rc > 32


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool):
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{__file__}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Ikona v liště
# ---------------------------------------------------------------------------

def make_tray_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(30, 110, 200, 255))
    d.text((20, 16), "H", fill=(255, 255, 255, 255))
    return img


# ---------------------------------------------------------------------------
# Hlavní okno
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.cfg = receiver.load_config()
        self.port = int(self.cfg.get("port", 47800))
        self.ui_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Heli Controller")
        self.root.geometry("460x420")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.bridge = Bridge(
            self.cfg,
            on_status=lambda s, t: self.ui_queue.put((s, t)),
            log=log.info,
        )
        self.tray = None
        self._build_ui()
        self._refresh_checks()
        self.root.after(100, self._poll)

    # ----- UI -----

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        self.status_var = tk.StringVar(value="Zastaveno")
        self.status_lbl = ttk.Label(frm, textvariable=self.status_var, font=("Segoe UI", 14, "bold"))
        self.status_lbl.pack(**pad, anchor="w")

        self.ip_var = tk.StringVar(value=f"Adresa PC: {local_ip()}  (port {self.port})")
        ttk.Label(frm, textvariable=self.ip_var).pack(padx=14, anchor="w")

        self.toggle_btn = ttk.Button(frm, text="Spustit", command=self.toggle)
        self.toggle_btn.pack(**pad, fill="x")

        checks = ttk.LabelFrame(frm, text="Připravenost")
        checks.pack(fill="x", padx=14, pady=8)

        self.vigem_var = tk.StringVar()
        self.fw_var = tk.StringVar()
        ttk.Label(checks, textvariable=self.vigem_var).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Button(checks, text="Nainstalovat ovladač", command=self.open_vigem).grid(row=0, column=1, padx=8)
        ttk.Label(checks, textvariable=self.fw_var).grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Button(checks, text="Opravit firewall", command=self.fix_firewall).grid(row=1, column=1, padx=8)

        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(
            frm, text="Spouštět po zapnutí Windows (na pozadí)",
            variable=self.autostart_var, command=self.toggle_autostart,
        ).pack(padx=14, anchor="w", pady=4)

        ttk.Button(frm, text="Otestovat ovladač (Windows)", command=self.open_joy_cpl).pack(**pad, fill="x")

        self.log_text = tk.Text(frm, height=6, font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(4, 8))

    def _refresh_checks(self):
        self.vigem_var.set("✔ ViGEmBus je nainstalovaný" if vigem_installed()
                           else "✖ Chybí ovladač ViGEmBus")
        self.fw_var.set("✔ Firewall je nastavený" if firewall_rule_exists()
                        else "✖ Firewall blokuje telefon")

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ----- akce -----

    def toggle(self):
        if self.bridge.running:
            self.bridge.stop()
            return
        try:
            self.bridge.start()
        except RuntimeError as e:
            log.error("Start selhal: %s", e)
            messagebox.showerror("Heli Controller", str(e))
            self._refresh_checks()

    def fix_firewall(self):
        if fix_firewall_elevated(self.port):
            self._append_log("Firewall: potvrď prosím dialog Windows (UAC).")
            self.root.after(4000, self._refresh_checks)
        else:
            messagebox.showwarning("Heli Controller", "Firewall se nepodařilo nastavit.")

    def open_vigem(self):
        import webbrowser
        webbrowser.open("https://github.com/nefarius/ViGEmBus/releases")

    def open_joy_cpl(self):
        subprocess.Popen(["control", "joy.cpl"], creationflags=NO_WINDOW)

    def toggle_autostart(self):
        try:
            set_autostart(self.autostart_var.get())
        except OSError as e:
            log.error("Autostart: %s", e)
            messagebox.showerror("Heli Controller", f"Nepodařilo se nastavit spouštění: {e}")
            self.autostart_var.set(autostart_enabled())

    def hide_to_tray(self):
        self.root.withdraw()

    def show_window(self, *_):
        self.root.after(0, self._show)

    def _show(self):
        self.root.deiconify()
        self.root.lift()

    def quit_app(self, *_):
        self.ui_queue.put(("quit", ""))

    # ----- smyčka -----

    def _poll(self):
        try:
            while True:
                state, text = self.ui_queue.get_nowait()
                if state == "quit":
                    self._shutdown()
                    return
                if state == "toggle":
                    self.toggle()
                    continue
                self._apply_status(state, text)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _apply_status(self, state: str, text: str):
        labels = {
            "stopped": ("Zastaveno", "gray"),
            "waiting": ("Čekám na telefon", "orange"),
            "connected": ("Telefon připojen", "green"),
            "error": ("Chyba", "red"),
        }
        label, color = labels.get(state, (state, "black"))
        self.status_var.set(label)
        self.status_lbl.configure(foreground=color)
        self.toggle_btn.configure(text="Zastavit" if state in ("waiting", "connected") else "Spustit")
        self._append_log(f"{label}: {text}" if text else label)
        if self.tray:
            self.tray.title = f"Heli Controller – {label}"

    def _shutdown(self):
        self.bridge.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def start_tray(self):
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("Otevřít", self.show_window, default=True),
            pystray.MenuItem("Spustit / Zastavit", lambda *_: self.ui_queue.put(("toggle", ""))),
            pystray.MenuItem("Konec", self.quit_app),
        )
        self.tray = pystray.Icon(APP_NAME, make_tray_image(), "Heli Controller", menu)
        # Na Windows běží ikona v pozadí; položky menu jdou přes frontu do hlavního vlákna.
        if hasattr(self.tray, "run_detached"):
            self.tray.run_detached()
        else:
            threading.Thread(target=self.tray.run, daemon=True).start()

    def run(self):
        self.start_tray()
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        sys.exit("Okno je určené pro Windows. Na testy použij receiver.py --dry-run.")
    app = App()
    app.run()


if __name__ == "__main__":
    main()
