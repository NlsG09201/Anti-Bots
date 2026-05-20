"""Weka Python (python-weka-wrapper3) + JVM lifecycle."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_jvm_started = False
_last_error: Optional[str] = None


def weka_python_installed() -> bool:
    try:
        import weka.core.jvm as jvm  # noqa: F401

        return True
    except ImportError:
        return False


def java_available(java_home: str = "") -> bool:
    if java_home:
        return True
    if os.environ.get("JAVA_HOME"):
        return True
    from shutil import which

    return which("java") is not None


def is_jvm_started() -> bool:
    return _jvm_started


def get_last_jvm_error() -> Optional[str]:
    return _last_error


def warm_weka_jvm(
    *,
    java_home: str = "",
    max_heap: str = "512m",
    include_packages: bool = True,
) -> Dict[str, Any]:
    """Start JPype + Weka JVM (blocking — call from thread pool in async apps)."""
    global _jvm_started, _last_error

    if not weka_python_installed():
        _last_error = "python-weka-wrapper3 not installed (pip install python-weka-wrapper3)"
        return {"ok": False, "error": _last_error}

    if not java_available(java_home):
        _last_error = "Java 11+ not found — set JAVA_HOME or install OpenJDK"
        return {"ok": False, "error": _last_error, "java_available": False}

    if _jvm_started:
        return {"ok": True, "jvm_started": True, "already_running": True}

    try:
        import weka.core.jvm as jvm

        if java_home:
            os.environ.setdefault("JAVA_HOME", java_home)

        jvm.start(
            system_cp=True,
            packages=include_packages,
            max_heap_size=max_heap,
        )
        _jvm_started = True
        _last_error = None
        logger.info("weka_jvm_started", max_heap=max_heap, packages=include_packages)
        return {
            "ok": True,
            "jvm_started": True,
            "max_heap": max_heap,
            "packages": include_packages,
        }
    except Exception as exc:
        _last_error = str(exc)
        logger.warning("weka_jvm_start_failed", error=_last_error)
        return {"ok": False, "error": _last_error, "java_available": True}


def weka_runtime_ready(java_home: str = "") -> bool:
    return weka_python_installed() and java_available(java_home) and is_jvm_started()


def runtime_status(java_home: str = "") -> Dict[str, Any]:
    return {
        "weka_python_installed": weka_python_installed(),
        "java_available": java_available(java_home),
        "jvm_started": is_jvm_started(),
        "weka_runtime_ready": weka_runtime_ready(java_home),
        "last_error": get_last_jvm_error(),
        "java_home": os.environ.get("JAVA_HOME") or java_home or None,
    }
