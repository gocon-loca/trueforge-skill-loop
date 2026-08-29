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
import shlex
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from orchestrator.research_executor import Digest

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERIFICATION_BLOCK = re.compile(
    r"^##\s+Verification\s*$.*?^```[a-zA-Z]*\s*$(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)
ALLOWED_VERIFIERS = frozenset({"make", "python3", "python", "pytest", "unittest"})
RESERVED_NAMES = frozenset({"_template"})


def validate_trust_state(meta: "SkillMeta") -> None:
    """Reject trust records that contradict themselves.

    A hand-edited meta.yaml is not preventable in a git-backed registry, and this does not
    claim to prevent it. What it does is make an inconsistent record fail closed at read
    time, so the cheap version of forging trust does not survive a load, and the expensive
    version still shows up as a reviewable diff.
    """
    if meta.exercised and not (meta.exercised_at and meta.exercised_by):
        raise InvalidTrustStateError(
            f"skill {meta.name!r} is marked exercised but carries no evidence "
            f"(exercised_at={meta.exercised_at!r}, exercised_by={meta.exercised_by!r}); "
            f"a trust record without evidence is not auditable"
        )
    if not meta.exercised and (meta.exercised_at or meta.exercised_by):
        raise InvalidTrustStateError(
            f"skill {meta.name!r} is not exercised but carries exercise evidence; "
            f"trust was revoked without clearing the record"
        )
    if meta.version < 1:
        raise InvalidTrustStateError(f"skill {meta.name!r} has non-positive version {meta.version}")
    if meta.minted_from not in {"research", "manual"}:
        raise InvalidTrustStateError(
            f"skill {meta.name!r} has unknown minted_from {meta.minted_from!r}"
        )
    if meta.minted_from == "research" and meta.citations < 1:
        raise InvalidTrustStateError(
            f"skill {meta.name!r} claims research provenance but cites nothing"
        )


class RegistryError(Exception):
    """Base for registry faults."""


class UntrustedSkillError(RegistryError):
    """Raised when work is attempted with a skill that has not passed the exercise gate."""


class InvalidTrustStateError(RegistryError):
    """Raised when a meta.yaml trust record contradicts itself."""


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
        meta = SkillMeta.from_mapping(yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {})
        validate_trust_state(meta)
        return meta

    def read_verification_command(self, name: str) -> tuple[str, ...]:
        """The command the skill itself declares as its passing run.

        Read from the first fenced block under `## Verification` in SKILL.md, so each skill
        is verified by its own check rather than by one hardcoded command.

        The body of a minted skill derives from a research digest, which is untrusted input,
        so this is a command-injection surface. It is handled by never using a shell: the
        command is parsed with shlex and the executable must be on ALLOWED_VERIFIERS. A
        skill cannot introduce a new executable by writing one into its own SKILL.md.
        """
        skill_md = self.path_for(name) / "SKILL.md"
        if not skill_md.is_file():
            raise RegistryError(f"skill {name!r} has no SKILL.md")

        match = VERIFICATION_BLOCK.search(skill_md.read_text(encoding="utf-8"))
        if not match:
            raise RegistryError(
                f"skill {name!r} declares no verification command; a skill without a "
                f"checkable verification step cannot be exercised, and so cannot be trusted"
            )

        parts = tuple(shlex.split(match.group("body").strip()))
        if not parts:
            raise RegistryError(f"skill {name!r} declares an empty verification command")
        if parts[0] not in ALLOWED_VERIFIERS:
            raise RegistryError(
                f"skill {name!r} declares verifier {parts[0]!r}, which is not on the "
                f"allowlist {sorted(ALLOWED_VERIFIERS)}"
            )
        return parts

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
