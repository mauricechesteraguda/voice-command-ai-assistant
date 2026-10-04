#!/usr/bin/env python3
"""Offline deterministic checks for manifests and repository hygiene."""
# implementation-10042026-Maurice
import json, pathlib, re, sys, uuid

session = f"native-{uuid.uuid4()}"
def log(event, detail=""):
    print(json.dumps({"session": session, "event": event, "detail": detail}, sort_keys=True))

def main() -> int:
    log("startup", "native validators")
    root = pathlib.Path(__file__).parents[2]
    bad = []
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.parts and ".trailmap" not in path.parts:
            text = path.read_text(errors="ignore")
            if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}", text):
                bad.append(str(path))
            if path.suffix in {".yaml", ".yml"} and "permissions:" in text and "contents: read" not in text and ".github" in path.parts:
                bad.append(f"broad workflow permissions: {path}")
    if bad:
        log("error", "; ".join(bad)); return 1
    log("result", "offline checks passed"); return 0

if __name__ == "__main__":
    raise SystemExit(main())
