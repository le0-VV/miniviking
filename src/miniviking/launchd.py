from __future__ import annotations

import os
import subprocess
from html import escape
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH
from .processes import server_program_arguments

LABEL = "ai.openviking.miniviking"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"
UTF8_ENVIRONMENT = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "LANG": "en_US.UTF-8",
    "LC_CTYPE": "en_US.UTF-8",
}


def launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def program_arguments(config_path: Path = CONFIG_PATH) -> list[str]:
    return server_program_arguments(config_path)


def plist_payload(config_path: Path = CONFIG_PATH) -> dict[str, object]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": program_arguments(config_path),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "miniviking.log"),
        "StandardErrorPath": str(LOG_DIR / "miniviking.err.log"),
        "WorkingDirectory": str(config_path.parent),
        "EnvironmentVariables": {"MINIVIKING_CONFIG": str(config_path), **UTF8_ENVIRONMENT},
    }


def write_plist(config_path: Path = CONFIG_PATH, plist_path: Path = PLIST_PATH) -> None:
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_xml(plist_payload(config_path)), encoding="utf-8")


def plist_xml(payload: dict[str, object]) -> str:
    body = "\n".join(_plist_key_value(key, value, 1) for key, value in payload.items())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        f"{body}\n"
        "</dict>\n"
        "</plist>\n"
    )


def _plist_key_value(key: str, value: object, indent: int) -> str:
    pad = "  " * indent
    return f"{pad}<key>{escape(key)}</key>\n{_plist_value(value, indent)}"


def _plist_value(value: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, bool):
        return f"{pad}<{str(value).lower()}/>"
    if isinstance(value, str):
        return f"{pad}<string>{escape(value)}</string>"
    if isinstance(value, list):
        items = "\n".join(_plist_value(item, indent + 1) for item in value)
        return f"{pad}<array>\n{items}\n{pad}</array>"
    if isinstance(value, dict):
        items = "\n".join(_plist_key_value(str(key), item, indent + 1) for key, item in value.items())
        return f"{pad}<dict>\n{items}\n{pad}</dict>"
    if isinstance(value, int):
        return f"{pad}<integer>{value}</integer>"
    raise TypeError(f"unsupported plist value: {value!r}")


def run_launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], text=True, capture_output=True, check=False)


def start(plist_path: Path = PLIST_PATH) -> subprocess.CompletedProcess[str]:
    return run_launchctl("bootstrap", launchd_domain(), str(plist_path))


def stop() -> subprocess.CompletedProcess[str]:
    return run_launchctl("bootout", launchd_domain(), LABEL)


def restart(plist_path: Path = PLIST_PATH) -> subprocess.CompletedProcess[str]:
    stop()
    return start(plist_path)


def status() -> subprocess.CompletedProcess[str]:
    return run_launchctl("print", f"{launchd_domain()}/{LABEL}")
