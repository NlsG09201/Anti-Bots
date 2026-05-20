#!/usr/bin/env python3
"""Comprueba Java + python-weka-wrapper3 y arranca la JVM (smoke test local)."""

from __future__ import annotations

import sys


def main() -> int:
    from app.ml.weka_j48.runtime import runtime_status, warm_weka_jvm

    print("=== Weka Python check ===")
    st = runtime_status()
    for k, v in st.items():
        print(f"  {k}: {v}")

    if not st["weka_python_installed"]:
        print("\nInstala: pip install python-weka-wrapper3")
        return 1
    if not st["java_available"]:
        print("\nInstala Java 17+ y define JAVA_HOME")
        return 1

    print("\nArrancando JVM…")
    res = warm_weka_jvm()
    print(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
