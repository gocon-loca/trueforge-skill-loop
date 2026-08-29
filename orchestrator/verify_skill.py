"""Run one skill's own verification.

Finding 5. The gate previously conferred trust from `make fixture`, which runs the
pipeline. A pass said the pipeline worked; it said nothing about the skill. Trust earned
from an unrelated run is not trust.

A skill is now verified by a `verify.py` in its own directory, invoked through the single
allowlisted entry point `make verify-skill SKILL=<name>`. A skill without one cannot be
exercised, and so cannot become trusted.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "registry"


def registry_root() -> Path:
    """The gate names the registry it is exercising, so verification cannot drift onto
    a different copy of the skill than the one whose trust is at stake."""
    return Path(os.environ.get("SKILL_REGISTRY") or DEFAULT_REGISTRY)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 -m orchestrator.verify_skill <skill-name>", file=sys.stderr)
        return 2

    name = argv[1]
    registry = registry_root()
    env_name = os.environ.get("SKILL_NAME")
    if env_name and env_name != name:
        print(
            f"refusing to verify {name!r}: the gate is exercising {env_name!r}",
            file=sys.stderr,
        )
        return 2

    skill_dir = registry / name
    if not skill_dir.is_dir() or skill_dir.resolve().parent != registry.resolve():
        print(f"no skill directory for {name!r}", file=sys.stderr)
        return 2

    check = skill_dir / "verify.py"
    if not check.is_file():
        print(
            f"skill {name!r} has no verify.py, so there is nothing that exercises its "
            f"method; it cannot become trusted",
            file=sys.stderr,
        )
        return 2

    print(f"verifying {name} via {check}")
    runpy.run_path(str(check), run_name="__main__")
    print(f"{name}: verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
