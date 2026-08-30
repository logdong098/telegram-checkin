from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .config import ConfigError, load_app_config, load_runtime_config
from .runtime import exit_code, login, run_daemon, run_once
from .web import AuthorizationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="telegram-checkin")
    parser.add_argument(
        "command",
        choices=("login", "once", "daemon", "validate"),
        help="authorize 820010.xyz and Telegram, run now, run the scheduler, or validate configuration",
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("CONFIG_PATH", "config.yaml"),
        help="YAML configuration path (default: CONFIG_PATH or config.yaml)",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args()

    try:
        if args.command == "login":
            asyncio.run(login(load_runtime_config()))
            return

        app = load_app_config(args.config)
        if args.command == "validate":
            print(f"Configuration valid: {len(app.bots)} bot(s)")
            return

        runtime = load_runtime_config()
        if args.command == "once":
            results = asyncio.run(run_once(app, runtime))
            for result in results:
                print(f"{result.target}: {result.status.value} - {result.detail}")
            raise SystemExit(exit_code(results))
        else:
            asyncio.run(run_daemon(app, runtime))
    except (ConfigError, AuthorizationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        raise SystemExit(130) from None
