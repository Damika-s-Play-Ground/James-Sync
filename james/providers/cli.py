"""Small CLI used by Hermes/cron workers and smoke tests."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .router import ProviderRouter
from .types import ProviderError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a James reply with Codex and fallback routing")
    parser.add_argument("prompt", nargs="?", help="user prompt; stdin is used when omitted")
    parser.add_argument("--system", default="You are a concise, helpful James assistant.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        print("prompt is empty", file=sys.stderr)
        return 2
    try:
        result = ProviderRouter().generate(system_prompt=args.system, user_prompt=prompt)
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps({
            "text": result.text,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "metadata": result.metadata,
        }, ensure_ascii=False))
    else:
        print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

