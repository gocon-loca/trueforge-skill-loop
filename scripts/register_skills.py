"""Register this repository's skill registry with a running TrueForge instance.

TrueForge reads skills as git-backed SKILL.md packs. Because this repository is public,
registering it needs no credentials: the manifest carries a public HTTPS URL, a path, and
a ref, and TrueForge fetches the pack itself.

Usage:
    python3 scripts/register_skills.py [--base URL] [--repo URL] [--ref main] [--list]

Note on the base URL. TrueForge binds IPv6 loopback, so http://127.0.0.1:8790 will not
reach it while http://[::1]:8790 will. The default below reflects that; override with
--base if your instance differs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = "http://[::1]:8790"
DEFAULT_REPO = "https://github.com/gocon-loca/trueforge-skill-loop"
REGISTRY = Path(__file__).resolve().parent.parent / "registry"
FRONTMATTER_DESCRIPTION = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def discover_skills() -> list[tuple[str, str]]:
    """Every skill pack in the registry, with the description from its own frontmatter."""
    found = []
    for skill_dir in sorted(p for p in REGISTRY.iterdir() if p.is_dir()):
        if skill_dir.name.startswith("_"):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        parts = skill_md.read_text(encoding="utf-8").split("---")
        match = FRONTMATTER_DESCRIPTION.search(parts[1] if len(parts) > 1 else "")
        if not match:
            print(f"  skipping {skill_dir.name}: no description in frontmatter")
            continue
        found.append((skill_dir.name, match.group(1).strip()))
    return found


def call(url: str, payload: dict | None = None, method: str = "GET") -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except urllib.error.URLError as exc:
        return 0, f"could not reach {url}: {exc.reason}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--list", action="store_true", help="only show what is registered")
    args = parser.parse_args(argv[1:])

    if args.list:
        status, body = call(f"{args.base}/api/v1/skills")
        print(f"HTTP {status}\n{body}")
        return 0 if status == 200 else 1

    skills = discover_skills()
    if not skills:
        print("no skill packs found in registry/", file=sys.stderr)
        return 1

    failures = 0
    for name, description in skills:
        status, body = call(
            f"{args.base}/api/v1/settings/skills",
            {
                "manifest": {
                    "type": "git",
                    "name": name,
                    "url": args.repo,
                    "path": f"registry/{name}",
                    "ref": args.ref,
                    "description": description[:300],
                }
            },
            method="POST",
        )
        if status in (200, 201):
            print(f"  registered {name}")
        elif status == 409 or "exists" in body.lower():
            print(f"  {name} already registered")
        else:
            print(f"  FAILED {name}: HTTP {status} {body[:200]}", file=sys.stderr)
            failures += 1

    status, body = call(f"{args.base}/api/v1/skills")
    print(f"\nTrueForge now reports (HTTP {status}):")
    if status == 200:
        for entry in json.loads(body).get("data", []):
            print(f"  - {entry['name']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
