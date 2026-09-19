"""Non-invasive provider/runtime health checks.

The check never calls a model and never prints credential values. It is safe to
run from an EC2 health probe or a dashboard endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _codex_checks() -> list[Check]:
    binary = os.getenv("CODEX_BIN", "codex")
    found = shutil.which(binary)
    checks = [Check("codex_binary", bool(found), found or f"{binary!r} not found")]
    home = Path(os.getenv("CODEX_HOME", "~/.codex")).expanduser()
    auth = home / "auth.json"
    checks.append(
        Check(
            "codex_auth_state",
            auth.is_file() or bool(os.getenv("CODEX_ACCESS_TOKEN")),
            "auth.json present" if auth.is_file() else (
                "CODEX_ACCESS_TOKEN present" if os.getenv("CODEX_ACCESS_TOKEN") else "missing auth.json/access token"
            ),
        )
    )
    return checks


def _openrouter_checks() -> list[Check]:
    enabled = os.getenv("JAMES_LLM_FALLBACK_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return [Check("openrouter_fallback", True, "disabled by configuration", required=False)]
    key_present = bool(os.getenv("OPENROUTER_API_KEY"))
    model_present = bool(os.getenv("OPENROUTER_MODEL"))
    return [
        Check("openrouter_api_key", key_present, "configured" if key_present else "missing OPENROUTER_API_KEY"),
        Check("openrouter_model", model_present, "configured" if model_present else "missing OPENROUTER_MODEL"),
    ]


def run_checks() -> dict[str, object]:
    checks = _codex_checks() + _openrouter_checks()
    required_failures = [check.name for check in checks if check.required and not check.ok]
    return {
        "ok": not required_failures,
        "required_failures": required_failures,
        "checks": [asdict(check) for check in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check James model provider configuration")
    parser.add_argument("--strict", action="store_true", help="return non-zero if any required check fails")
    args = parser.parse_args(argv)
    report = run_checks()
    print(json.dumps(report, indent=2))
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

