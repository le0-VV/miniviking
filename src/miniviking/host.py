from __future__ import annotations

import platform
import subprocess

from .tiers import unified_memory_gib


class HostDetectionError(RuntimeError):
    pass


def detect_unified_memory_gib() -> int:
    if platform.system() != "Darwin":
        raise HostDetectionError("miniviking install is supported on macOS only")

    try:
        output = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HostDetectionError("failed to detect macOS unified memory with sysctl") from exc

    try:
        return unified_memory_gib(int(output))
    except ValueError as exc:
        raise HostDetectionError(f"invalid hw.memsize value: {output!r}") from exc
