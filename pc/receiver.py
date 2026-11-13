#!/usr/bin/env python3
"""
Jádro přijímače: přijímá UDP pakety z telefonu a převádí je na virtuální Xbox 360 ovladač
(vJoy). Hra ho vidí jako běžný joystick.

Protokol (UDP, port z config.json, výchozí 47800):
  telefon -> PC  JSON jednou za ~20 ms:
      {"pitch": -1..1, "roll": -1..1, "yaw": -1..1, "collective": -1..1, "buttons": <bitmask>}
  telefon -> broadcast  b"HELI_DISCOVER"
  PC -> telefon  JSON {"heli": 1, "name": "<jméno PC>", "port": <port>}   (odpověď na objevení)

Spuštění z příkazové řádky (bez okna):
  python receiver.py                # reálný virtuální joystick (Windows + vJoy)
  python receiver.py --dry-run      # jen vypisuje hodnoty, bez ovladače
Okno s ikonou v liště: tray_app.py
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
DISCOVER_MSG = b"HELI_DISCOVER"


# ---------------------------------------------------------------------------
# Čisté funkce pro mapování (bez závislostí, dají se testovat na libovolném OS)
# ---------------------------------------------------------------------------

def clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def apply_deadzone(v: float, dz: float) -> float:
    """Malé výchylky na nulu, zbytek přepočítá na plný rozsah -1..1."""
    if abs(v) <= dz:
        return 0.0
    sign = 1.0 if v > 0 else -1.0
    return sign * (abs(v) - dz) / (1.0 - dz)


@dataclass
class Axes:
    lx: float = 0.0          # levá páka X (roll)
    ly: float = 0.0          # levá páka Y (pitch)
    rx: float = 0.0          # pravá páka X (yaw)
    lt: float = 0.0          # levý spoušť 0..1
    rt: float = 0.0          # pravý spoušť 0..1
    buttons: list[int] = field(default_factory=list)  # indexy stisknutých tlačítek


class Mapper:
    """Převádí telefonní data na osy gamepadu podle config.json."""

    def __init__(self, cfg: dict):
        self.dz = float(cfg.get("deadzone", 0.05))
        self.inv = cfg.get("invert", {})
        self.sens = cfg.get("sensitivity", {})
        # index bitu telefonu -> číslo tlačítka vJoy (1..32)
        self.button_map = {int(k): int(v) for k, v in cfg.get("buttons", {}).items()}

    def _axis(self, name: str, raw: float) -> float:
        v = clamp(raw)
        if self.inv.get(name, False):
            v = -v
        v = v * float(self.sens.get(name, 1.0))
        return clamp(apply_deadzone(clamp(v), self.dz))

    def map(self, pkt: dict) -> Axes:
        pitch = self._axis("pitch", pkt.get("pitch", 0.0))
        roll = self._axis("roll", pkt.get("roll", 0.0))
        yaw = self._axis("yaw", pkt.get("yaw", 0.0))
        coll = self._axis("collective", pkt.get("collective", 0.0))

        # Náklon dopředu = páka dopředu (záporné Y). Lze převrátit v config.json.
        axes = Axes(
            lx=roll,
            ly=-pitch,
            rx=yaw,
            lt=max(0.0, -coll),
            rt=max(0.0, coll),
        )
        mask = int(pkt.get("buttons", 0))
        axes.buttons = [i for i in range(32) if mask & (1 << i) and i in self.button_map]
        return axes

    def button_numbers(self, axes: Axes) -> list[int]:
        return [self.button_map[i] for i in axes.buttons]


def parse_packet(data: bytes) -> dict | None:
    try:
        pkt = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return pkt if isinstance(pkt, dict) else None


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def local_ip() -> str:
    """Zjistí IP adresu PC v lokální síti (bez odeslání čehokoli)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Výstupní zařízení
# ---------------------------------------------------------------------------

def to_vjoy_axis(v: float) -> int:
    """-1..1 -> 0..32767 (střed 16384), jak očekává vJoy."""
    v = clamp(v)
    return max(0, min(VJOY_AXIS_MAX, round((v + 1.0) / 2.0 * VJOY_AXIS_MAX)))


VJOY_AXIS_MAX = 32767
VJOY_DEVICE = 1
VJOY_DLL_DEFAULT = Path(r"C:\Program Files\vJoy\x64\vJoyInterface.dll")
# HID kódy os (usage) podle vJoy SDK
HID_X, HID_Y, HID_Z, HID_RZ = 0x30, 0x31, 0x32, 0x35


class DryRunPad:
    """Náhrada za vJoy pro testování bez Windows/vJoy."""

    def __init__(self, log: Callable[[str], None] = print):
        self.log = log
        self.last = 0.0

    def apply(self, axes: Axes, numbers: list[int]):
        now = time.monotonic()
        if now - self.last < 0.2:
            return
        self.last = now
        self.log(f"X={axes.lx:+.2f} Y={axes.ly:+.2f} Z={axes.rt - axes.lt:+.2f} "
                 f"RZ={axes.rx:+.2f} btn={numbers}")

    def reset(self):
        pass

    def close(self):
        pass


class VJoyPad:
    """Virtuální joystick přes vJoyInterface.dll (vyžaduje nainstalovaný vJoy na Windows)."""

    def __init__(self, dll_path: Path = VJOY_DLL_DEFAULT):
        import ctypes

        if not dll_path.exists():
            raise RuntimeError("Není nainstalovaný vJoy (chybí vJoyInterface.dll).")
        self.dll = ctypes.WinDLL(str(dll_path))
        d = self.dll
        d.vJoyEnabled.restype = ctypes.c_int
        d.AcquireVJD.argtypes = [ctypes.c_uint]
        d.AcquireVJD.restype = ctypes.c_int
        d.RelinquishVJD.argtypes = [ctypes.c_uint]
        d.RelinquishVJD.restype = ctypes.c_int
        d.ResetVJD.argtypes = [ctypes.c_uint]
        d.ResetVJD.restype = ctypes.c_int
        d.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]
        d.SetAxis.restype = ctypes.c_int
        d.SetBtn.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_ubyte]
        d.SetBtn.restype = ctypes.c_int

        if not d.vJoyEnabled():
            raise RuntimeError("vJoy je nainstalovaný, ale není aktivní. Zkus přeinstalovat vJoy.")
        if not d.AcquireVJD(VJOY_DEVICE):
            raise RuntimeError(f"Virtuální joystick {VJOY_DEVICE} je obsazený nebo neexistuje (zkontroluj vJoy Config).")
        d.ResetVJD(VJOY_DEVICE)
        self._pressed: set[int] = set()

    def apply(self, axes: Axes, numbers: list[int]):
        d = self.dll
        d.SetAxis(to_vjoy_axis(axes.lx), VJOY_DEVICE, HID_X)
        d.SetAxis(to_vjoy_axis(axes.ly), VJOY_DEVICE, HID_Y)
        d.SetAxis(to_vjoy_axis(axes.rt - axes.lt), VJOY_DEVICE, HID_Z)
        d.SetAxis(to_vjoy_axis(axes.rx), VJOY_DEVICE, HID_RZ)

        wanted = set(numbers)
        for n in wanted - self._pressed:
            d.SetBtn(1, VJOY_DEVICE, n)
        for n in self._pressed - wanted:
            d.SetBtn(0, VJOY_DEVICE, n)
        self._pressed = wanted

    def reset(self):
        """Bezpečnost: při ztrátě spojení vše vrátit do středu."""
        self.dll.ResetVJD(VJOY_DEVICE)
        self._pressed = set()

    def close(self):
        self.reset()
        self.dll.RelinquishVJD(VJOY_DEVICE)


def create_pad(dry_run: bool, log: Callable[[str], None] = print):
    """Vytvoří výstup. Při chybě (chybí vJoy apod.) vyhodí RuntimeError s lidským textem."""
    if dry_run:
        return DryRunPad(log)
    try:
        return VJoyPad()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Virtuální joystick nelze vytvořit ({e}). Je nainstalovaný vJoy?") from e


def vjoy_selftest(log: Callable[[str], None]) -> bool:
    """
    Diagnostika vJoy: ověří DLL, získá zařízení 1 a 5 s pohybuje osou X.
    Výsledky hlásí přes log(). Vrací True, pokud volání prošla.
    """
    import ctypes
    import math

    log("Diagnostika vJoy: začínám.")
    if not VJOY_DLL_DEFAULT.exists():
        log("✖ Nenalezen vJoyInterface.dll. Je nainstalovaný vJoy?")
        return False
    try:
        pad = VJoyPad()
    except RuntimeError as e:
        log(f"✖ {e}")
        return False

    try:
        d = pad.dll
        d.GetVJDStatus.argtypes = [ctypes.c_uint]
        d.GetVJDStatus.restype = ctypes.c_int
        status = {0: "vlastním", 1: "volné", 2: "obsazené", 3: "chybí", 4: "neznámé"}
        code = d.GetVJDStatus(VJOY_DEVICE)
        log(f"Stav zařízení {VJOY_DEVICE}: {status.get(code, code)}")
        log("✔ Zařízení vJoy 1 získáno.")

        failures = 0
        for i in range(100):  # ~5 s
            v = int(16384 + 16000 * math.sin(i / 10))
            ok = d.SetAxis(v, VJOY_DEVICE, HID_X)
            if not ok:
                failures += 1
            time.sleep(0.05)
        if failures == 0:
            log("✔ Osa X přijímala hodnoty (5 s). Pokud se v joy.cpl nehýbe, je vJoy špatně nakonfigurovaný (osy X, Y, Z, Rz v vJoy Configure).")
            return True
        log(f"✖ SetAxis selhalo {failures}×. Zapni osy X, Y, Z, Rz ve vJoy Configure a zkus to znovu.")
        return False
    finally:
        pad.close()
        log("Diagnostika vJoy: hotovo.")


# ---------------------------------------------------------------------------
# Bridge: přenos telefon -> ovladač, běží ve vlastním vlákně
# ---------------------------------------------------------------------------

class Bridge:
    """
    Stavy hlášené přes on_status(stav, text):
      "stopped"   - nezapnuto
      "waiting"   - naslouchá, telefon zatím nepřipojen
      "connected" - přijímá data z telefonu (text = IP telefonu)
      "error"     - chyba (text = popis)
    """

    def __init__(
        self,
        cfg: dict,
        *,
        dry_run: bool = False,
        port: int | None = None,
        on_status: Callable[[str, str], None] = lambda s, t: None,
        log: Callable[[str], None] = print,
    ):
        self.cfg = cfg
        self.dry_run = dry_run
        self.port = port or int(cfg.get("port", 47800))
        self.timeout = float(cfg.get("timeout_s", 0.5))
        self.mapper = Mapper(cfg)
        self.on_status = on_status
        self.log = log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._pad = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        # Výstup i port zkontrolujeme dřív, než něco přepneme do stavu "běží".
        self._pad = create_pad(self.dry_run, self.log)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", self.port))
        except OSError as e:
            self._pad.close()
            raise RuntimeError(f"Port {self.port} je obsazený (jiný program?): {e}") from e
        sock.settimeout(0.1)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="heli-bridge", daemon=True)
        self._thread.start()
        self.on_status("waiting", f"Čekám na telefon (port {self.port})")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._pad:
            self._pad.close()
            self._pad = None
        self.on_status("stopped", "Zastaveno")

    def _loop(self):
        assert self._sock and self._pad
        connected_ip: str | None = None
        last_packet = 0.0
        name = socket.gethostname()

        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(2048)
            except socket.timeout:
                if connected_ip and time.monotonic() - last_packet > self.timeout:
                    self._pad.reset()
                    connected_ip = None
                    self.on_status("waiting", "Spojení vypršelo, čekám na telefon")
                continue
            except OSError:
                break

            # Objevení telefonu: odpovíme, aby se telefon mohl připojit bez zadání IP.
            if data == DISCOVER_MSG:
                reply = json.dumps({"heli": 1, "name": name, "port": self.port}).encode("utf-8")
                self._sock.sendto(reply, addr)
                continue

            pkt = parse_packet(data)
            if pkt is None:
                continue

            if connected_ip != addr[0]:
                connected_ip = addr[0]
                self.on_status("connected", connected_ip)
            last_packet = time.monotonic()

            axes = self.mapper.map(pkt)
            self._pad.apply(axes, self.mapper.button_numbers(axes))

        self._pad.reset()


# ---------------------------------------------------------------------------
# Příkazová řádka (bez okna)
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Telefon -> virtuální Xbox ovladač")
    ap.add_argument("--dry-run", action="store_true", help="jen vypisuj hodnoty, bez ovladače")
    ap.add_argument("--port", type=int, help="přepíše port z config.json")
    args = ap.parse_args()

    cfg = load_config()
    bridge = Bridge(
        cfg,
        dry_run=args.dry_run,
        port=args.port,
        on_status=lambda s, t: print(f"[{s}] {t}"),
    )
    try:
        bridge.start()
        print(f"Adresa PC: {local_ip()}  Ukonči Ctrl+C.")
        while True:
            time.sleep(1)
    except RuntimeError as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        print("\nUkončeno.")
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()
