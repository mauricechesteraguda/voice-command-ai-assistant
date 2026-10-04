"""Minimal injectable administrator CLI; it never sends data unless requested."""

# implementation-10042026-Maurice
from __future__ import annotations
import argparse, json
from typing import Any, Callable
from platform_api.observability import traced

@traced
def main(argv: list[str] | None = None, *, request: Callable[[str, dict[str, Any]], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="control-plane-admin"); parser.add_argument("--config", action="store_true"); args = parser.parse_args(argv)
    if args.config and request is not None: print(json.dumps(request("/v1/config", {}), sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
