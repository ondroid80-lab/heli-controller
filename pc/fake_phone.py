#!/usr/bin/env python3
"""
Simulátor telefonu: posílá na přijímač testovací pakety (sinusovky + tlačítka).
Použij pro ověření přenosu bez telefonu, např.:
  python receiver.py --dry-run      (v jednom okně)
  python fake_phone.py --host 127.0.0.1   (v druhém okně)
"""
import argparse
import json
import math
import socket
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=47800)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--rate", type=float, default=50.0, help="paketů za sekundu")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dt = 1.0 / args.rate
    t0 = time.monotonic()
    n = 0
    while time.monotonic() - t0 < args.seconds:
        t = time.monotonic() - t0
        pkt = {
            "pitch": 0.6 * math.sin(t * 2),
            "roll": 0.6 * math.cos(t * 1.3),
            "yaw": 0.5 * math.sin(t * 0.7),
            "collective": 0.8 * math.sin(t * 0.5),
            "buttons": 1 if int(t) % 2 == 0 else 0,  # tlačítko 0 (A) bliká
            "center": False,
        }
        sock.sendto(json.dumps(pkt).encode("utf-8"), (args.host, args.port))
        n += 1
        time.sleep(dt)
    print(f"Odesláno {n} paketů.")


if __name__ == "__main__":
    main()
