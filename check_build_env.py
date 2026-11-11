#!/usr/bin/env python3
# PDFDesk — Guido Cauli <guido.cauli@gmail.com> — controllo dell'ambiente di compilazione
# Verifica che Python (versione maggiore.minore) e tutti i moduli indicati in requirements.lock siano ESATTAMENTE quelli di
# riferimento, così Windows, Linux e macOS si compilano con lo stesso Python e le stesse librerie.
# Uso: python check_build_env.py [--quiet]      Esce con codice 1 se qualcosa differisce.
import importlib.metadata as md
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def norm(n: str) -> str:
    return re.sub(r"[-_.]+", "-", n).lower()


def read_lock():
    py, pins = None, {}
    for raw in open(os.path.join(ROOT, "requirements.lock"), encoding="utf-8"):
        line = raw.strip()
        m = re.match(r"#\s*python_requires:\s*(\d+\.\d+)", line)
        if m:
            py = m.group(1)
        if not line or line.startswith("#"):
            continue
        spec, _, marker = line.partition(";")
        mk = marker.strip()
        if mk and (("win32" in mk and sys.platform != "win32") or ("darwin" in mk and sys.platform != "darwin")):
            continue                                   # pacchetti solo Windows (pefile…) o solo macOS (macholib)
        name, _, ver = spec.strip().partition("==")
        pins[norm(name)] = ver.strip()
    return py, pins


def main() -> int:
    quiet = "--quiet" in sys.argv
    py, pins = read_lock()
    bad = []
    here = f"{sys.version_info.major}.{sys.version_info.minor}"
    if py and here != py:
        bad.append(f"Python {here} (richiesto {py}.x)")
    for name, want in sorted(pins.items()):
        try:
            got = md.version(name)
        except md.PackageNotFoundError:
            bad.append(f"{name}: non installato (richiesto {want})")
            continue
        if got != want:
            bad.append(f"{name}: {got} (richiesto {want})")
    if bad:
        print("PDFDesk — Guido Cauli <guido.cauli@gmail.com> — AMBIENTE DI COMPILAZIONE NON CONFORME", file=sys.stderr)
        for b in bad:
            print("  - " + b, file=sys.stderr)
        print("Installa le versioni di riferimento:  python -m pip install -r requirements.lock  (con Python " + (py or "3.11") + ")", file=sys.stderr)
        return 1
    if not quiet:
        print(f"Ambiente di compilazione conforme: Python {sys.version.split()[0]}, {len(pins)} moduli alle versioni di riferimento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
