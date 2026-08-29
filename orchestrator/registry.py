"""The skill registry, and the single writer of the `exercised` trust flag.

The registry's one job beyond storage is to make this invariant reviewable:

    exercised is true  implies  a passing run happened

That is enforced structurally. `mark_exercised` does not run the check itself; it takes
evidence of a completed run as an argument, so the proof obligation sits at the call site
where the run actually happened. The three trust fields (`exercised`, `exercised_at`,
`exercised_by`) are written in one operation and never separately, because a skill with
`exercised: true` and a null `exercised_by` is unauditable.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from orchestrator.research_executor import Digest

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_NAMES = frozenset({"_template"})


class RegistryError(Exception):
    """Base for registry faults."""


class UntrustedSkillError(RegistryError):
    """Raised when work is attempted with a skill that has not passed the exercise gate."""


class UngroundedSkillError(RegistryError):
    """Raised when minting is attempted from a digest that cites nothing."""


@dataclass(frozen=True)
class ExerciseEvidence:
    """Proof that a run happened, produced by whoever ran it.

    `passed` is the caller's assertion about a run it actually performed. The registry
    refuses to record anything that did not pass, so this type is the only route from a
    completed run to a trusted skill.
    """

    command: str
    passed: bool
    at: datetime

    @staticmethod
    def now(command: str, *, passed: bool) -> "ExerciseEvidence":
        return ExerciseEvidence(command=command, passed=passed, at=datetime.now(timezone.utc))


@dataclass(frozen=True)
class SkillMeta:
    name: str
    version: int
    minted_from: str
    exercised: bool
    exercised_at: str | None
    exercised_by: str | None
    citations: int

    @classmethod
    def from_mapping(cls, data: dict) -> "SkillMeta":
        missing = {"name", "version", "minted_from", "exercised"} - data.keys()
        if missing:
            raise RegistryError(f"meta.yaml missing required fields: {sorted(missing)}")
        return cls(
            name=data["name"],
            version=int(data["version"]),
            minted_from=data["minted_from"],
            exercised=bool(data["exercised"]),
            exercised_at=data.get("exercised_at"),
            exercised_by=data.get("exercised_by"),
            citations=int(data.get("citations", 0)),
        )

    def to_mapping(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "minted_from": self.minted_from,
            "exercised": self.exercised,
            "exercised_at": self.exercised_at,
            "exercised_by": self.exercised_by,
            "citations": self.citations,
        }


class Registry:
    """Git-backed skill packs on disk. TrueForge consumes the same directory as a skill source."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # ---- reading -------------------------------------------------------------

    def list_skills(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name
            for p in self.root.iterdir()
            if p.is_dir() and p.name not in RESERVED_NAMES and (p / "meta.yaml").is_file()
        )

    def path_for(self, name: str) -> Path:
        return self.root / name

    def load_meta(self, name: str) -> SkillMeta:
        meta_path = self.path_for(name) / "meta.yaml"
        if not meta_path.is_file():
            raise RegistryError(f"no skill named {name!r} in {self.root}")
        return SkillMeta.from_mapping(yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {})

    def is_trusted(self, name: str) -> bool:
        return self.load_meta(name).exercised

    def require_trusted(self, name: str) -> SkillMeta:
        """Gate on use. This is what stops a built-never-run skill from performing work."""
        meta = self.load_meta(name)
        if not meta.exercised:
            raise UntrustedSkillError(
                f"skill {name!r} has not passed the exercise gate and must not be used for work; "
                f"run `make exercise` against it first"
            )
        return meta

    # ---- the single writer of the trust fields --------------------------------

    def mark_exercised(self, name: str, evidence: ExerciseEvidence) -> SkillMeta:
        """The ONLY code path that sets `exercised` to true. Nothing else may flip it.

        Takes evidence of a run rather than performing one, so that a caller cannot obtain
        trust without having executed the gate.
        """
        if not evidence.passed:
            raise RegistryError(
                f"refusing to mark {name!r} exercised: evidence reports a failing run"
            )
        meta = self.load_meta(name)
        updated = replace(
            meta,
            exercised=True,
            exercised_at=evidence.at.isoformat().replace("+00:00", "Z"),
            exercised_by=evidence.command,
        )
        self._write_meta(name, updated)
        return updated

    def reset_trust(self, name: str) -> SkillMeta:
        """Re-minting revokes trust. Same single writer, so the three fields cannot drift."""
        meta = self.load_meta(name)
        updated = replace(meta, exercised=False, exercised_at=None, exercised_by=None)
        self._write_meta(name, updated)
        return updated

    # ---- minting --------------------------------------------------------------

    def mint(self, name: str, digest: Digest, skill_body: str) -> SkillMeta:
        """Write a skill pack from a research digest. Always lands untrusted."""
        if not NAME_PATTERN.match(name) or name in RESERVED_NAMES:
            raise RegistryError(f"invalid skill name {name!r}; expected kebab-case")
        if not digest.is_groundable():
            raise UngroundedSkillError(
                f"refusing to mint {name!r} from a digest with no citations; "
                f"a skill whose rules cite nothing is a skill that invented its method"
            )

        skill_dir = self.path_for(name)
        skill_dir.mkdir(parents=True, exist_ok=True)

        previous_version = 0
        if (skill_dir / "meta.yaml").is_file():
            previous_version = self.load_meta(name).version

        (skill_dir / "SKILL.md").write_text(skill_body, encoding="utf-8")
        (skill_dir / "citations.md").write_text(
            "# Citations\n\n"
            "Every method rule this skill encodes traces to a source here.\n\n"
            + "\n".join(c.to_markdown() for c in digest.citations),
            encoding="utf-8",
        )
        meta = SkillMeta(
            name=name,
            version=previous_version + 1,
            minted_from="research",
            exercised=False,
            exercised_at=None,
            exercised_by=None,
            citations=len(digest.citations),
        )
        self._write_meta(name, meta)
        return meta

    # ---- storage --------------------------------------------------------------

    def _write_meta(self, name: str, meta: SkillMeta) -> None:
        """Atomic replace, so an interrupted write cannot leave meta.yaml half-written."""
        target = self.path_for(name) / "meta.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".meta-", suffix=".yaml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(meta.to_mapping(), handle, sort_keys=False)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
