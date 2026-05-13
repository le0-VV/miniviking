from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import CONFIG_PATH, DEFAULT_HOST, DEFAULT_PORT, ServerConfig, config_from_defaults, load_config, write_config
from .host import HostDetectionError, detect_unified_memory_gib
from .launchd import PLIST_PATH, restart as launchd_restart, start as launchd_start, status as launchd_status, stop as launchd_stop, write_plist
from .openviking import openviking_config_json
from .runtime import DownloadError, MlxRuntime, download_models
from .server import serve
from .smoke import SmokeError, run_smoke
from .tiers import defaults_for_memory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="miniviking")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="write config, download models, and install LaunchAgent")
    install.add_argument("--config", type=Path, default=CONFIG_PATH)
    install.add_argument("--mode", choices=["llm", "embedding", "both"], default="both")
    install.add_argument("--host", default=DEFAULT_HOST)
    install.add_argument("--port", type=int, default=DEFAULT_PORT)
    install.add_argument("--memory-gib", type=int, help="override detected unified memory for custom installs")
    install.add_argument("--skip-launch-agent", action="store_true", help="do not write the macOS LaunchAgent plist")
    install.add_argument("--print-openviking-config", action="store_true", help="print OpenViking config after install")

    uninstall = subparsers.add_parser("uninstall", help="unload LaunchAgent and remove its plist")
    uninstall.add_argument("--plist", type=Path, default=PLIST_PATH)

    serve_parser = subparsers.add_parser("serve", help="serve the OpenAI-compatible API")
    serve_parser.add_argument("--config", type=Path, default=CONFIG_PATH)

    for name in ("start", "stop", "restart", "status"):
        subparsers.add_parser(name)

    config_parser = subparsers.add_parser("config", help="print effective config")
    config_parser.add_argument("--config", type=Path, default=CONFIG_PATH)

    ov_config = subparsers.add_parser("openviking-config", help="print OpenViking config snippet")
    ov_config.add_argument("--config", type=Path, default=CONFIG_PATH)

    smoke = subparsers.add_parser("smoke", help="verify a running miniviking server")
    smoke.add_argument("--config", type=Path, default=CONFIG_PATH)
    smoke.add_argument("--base-url", help="override OpenAI-compatible base URL")
    smoke.add_argument("--timeout", type=float, default=30.0)
    smoke.add_argument("--skip-chat", action="store_true")
    smoke.add_argument("--skip-embeddings", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            _install(args)
        elif args.command == "uninstall":
            _uninstall(args.plist)
        elif args.command == "serve":
            config = load_config(args.config)
            serve(config, MlxRuntime(config))
        elif args.command == "start":
            _print_launchctl(launchd_start())
        elif args.command == "stop":
            _print_launchctl(launchd_stop())
        elif args.command == "restart":
            _print_launchctl(launchd_restart())
        elif args.command == "status":
            _print_launchctl(launchd_status())
        elif args.command == "config":
            config = load_config(args.config)
            print(json.dumps(_config_payload(config), indent=2))
        elif args.command == "openviking-config":
            config = load_config(args.config)
            print(openviking_config_json(config))
        elif args.command == "smoke":
            config = load_config(args.config)
            _smoke(args, config)
    except (DownloadError, HostDetectionError, OSError, RuntimeError, SmokeError, ValueError) as exc:
        print(f"miniviking: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _install(args: argparse.Namespace) -> None:
    memory_gib = args.memory_gib if args.memory_gib else detect_unified_memory_gib()
    defaults = defaults_for_memory(memory_gib)
    config = config_from_defaults(defaults, mode=args.mode, host=args.host, port=args.port)
    download_models(config)
    write_config(config, args.config)
    if not args.skip_launch_agent:
        write_plist(args.config)

    print(f"Detected memory tier: {defaults.name} ({memory_gib} GB)")
    print(f"Wrote config: {args.config}")
    if args.skip_launch_agent:
        print("Skipped LaunchAgent install")
    else:
        print(f"Wrote LaunchAgent: {PLIST_PATH}")
    print(f"OpenAI-compatible base URL: {config.base_url}")
    if args.print_openviking_config:
        print(openviking_config_json(config))
    if defaults.warning:
        print(f"Warning: {defaults.warning}", file=sys.stderr)


def _uninstall(plist_path: Path) -> None:
    launchd_stop()
    if plist_path.exists():
        plist_path.unlink()
        print(f"Removed {plist_path}")


def _print_launchctl(result: object) -> None:
    stdout = getattr(result, "stdout", "")
    stderr = getattr(result, "stderr", "")
    returncode = getattr(result, "returncode", 0)
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    if returncode:
        raise SystemExit(returncode)


def _smoke(args: argparse.Namespace, config: ServerConfig) -> None:
    checks = run_smoke(
        config,
        base_url=args.base_url,
        timeout=args.timeout,
        check_chat=not args.skip_chat,
        check_embeddings=not args.skip_embeddings,
    )
    failed = False
    for check in checks:
        prefix = "ok" if check.ok else "fail"
        print(f"{prefix}: {check.name}: {check.detail}")
        failed = failed or not check.ok
    if failed:
        raise SystemExit(1)


def _config_payload(config: object) -> dict[str, object]:
    from dataclasses import asdict

    return asdict(config)


if __name__ == "__main__":
    main()
