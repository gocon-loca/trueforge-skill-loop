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

import hashlib
import json
import os
import re
import secrets
import shlex
import tempfile
import threading
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
# Finding 1. The previous allowlist named python3 and pytest, which is not a constraint:
# `python3 -c "<anything>"` is arbitrary code execution, so an allowlist naming an
# interpreter offers assurance it cannot deliver.
#
# A skill may invoke `make` only, with bare target names and VAR=VALUE assignments.
# Targets live in this repository's reviewed Makefile, so what a minted skill can cause
# to run is fixed by review rather than by whatever its own body says.
ALLOWED_VERIFIERS = frozenset({"make"})
MAKE_ARG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(=[A-Za-z0-9._/-]*)?$")
RESERVED_NAMES = frozenset({"_template"})


def _strict_bool(value: object, *, field: str) -> bool:
    """Finding 8. `bool("false")` is True, so a quoted false in meta.yaml read as trusted.

    Only a real YAML boolean is accepted. A string is rejected rather than coerced, because
    guessing at the intent of `exercised: "false"` is how a skill becomes trusted by typo.
    """
    if isinstance(value, bool):
        return value
    raise InvalidTrustStateError(
        f"{field} must be a YAML boolean, got {type(value).__name__} {value!r}; "
        f"quote-wrapped booleans are rejected rather than coerced"
    )


def validate_trust_state(meta: "SkillMeta") -> None:
    """Reject trust records that contradict themselves.

    A hand-edited meta.yaml is not preventable in a git-backed registry, and this does not
    claim to prevent it. What it does is make an inconsistent record fail closed at read
    time, so the cheap version of forging trust does not survive a load, and the expensive
    version still shows up as a reviewable diff.
    """
    if meta.exercised and not (meta.exercised_at and meta.exercised_by and meta.exercised_hash):
        raise InvalidTrustStateError(
            f"skill {meta.name!r} is marked exercised but carries no evidence "
            f"(exercised_at={meta.exercised_at!r}, exercised_by={meta.exercised_by!r}, "
        f"exercised_hash={meta.exercised_hash!r}); "
            f"a trust record without evidence is not auditable"
        )
    if not meta.exercised and (meta.exercised_at or meta.exercised_by or meta.exercised_hash):
        raise InvalidTrustStateError(
            f"skill {meta.name!r} is not exercised but carries exercise evidence; "
            f"trust was revoked without clearing the record"
        )
    if meta.version < 1:
        raise InvalidTrustStateError(f"skill {meta.name!r} has non-positive version {meta.version}")
    if meta.minted_from not in {"research", "manual", "incident"}:
        raise InvalidTrustStateError(
            f"skill {meta.name!r} has unknown minted_from {meta.minted_from!r}"
        )
    for entry in meta.amendments:
        fields = dict(entry)
        missing = {"gap_question", "retrieval_source", "date"} - fields.keys()
        if missing:
            raise InvalidTrustStateError(
                f"skill {meta.name!r} has an amendment record missing {sorted(missing)}; "
                f"an amendment that does not say what prompted it records nothing"
            )

    if meta.minted_from in {"research", "incident"} and meta.citations < 1:
        raise InvalidTrustStateError(
            f"skill {meta.name!r} claims {meta.minted_from} provenance but cites nothing"
        )


class RegistryError(Exception):
    """Base for registry faults."""


class VersionAmbiguityError(RegistryError):
    """Raised when a version would stop identifying exactly one body of content."""


class UntrustedSkillError(RegistryError):
    """Raised when work is attempted with a skill that has not passed the exercise gate."""


class InvalidTrustStateError(RegistryError):
    """Raised when a meta.yaml trust record contradicts itself."""


class UngroundedSkillError(RegistryError):
    """Raised when minting is attempted from a digest that cites nothing."""


@dataclass(frozen=True)
class ExerciseTicket:
    """A registry-issued claim on one exercise run, bound to the skill state it saw.

    Findings 1 and 4. Evidence used to be a caller-constructed `passed=True` boolean, which
    the review correctly called forgeable: the tests themselves obtained trust without
    running the gate. A ticket must now be issued by the registry before a run, carries the
    version and content hash observed at issue time, and is consumed on use.

    What this does and does not achieve, stated plainly. It closes the accidental path, so
    no caller marks a skill trusted without first asking for a ticket and reporting a real
    exit status, and it binds a run to the exact skill content that was on disk when the run
    started, so a concurrent re-mint invalidates the ticket rather than inheriting its trust.
    It is not unforgeable. Any in-process caller can request a ticket and report rc=0
    without running anything. In-process code is trusted here; the durable defence is that
    `exercised_by` records what ran and every trust change is a reviewable diff.
    """

    skill: str
    version: int
    content_hash: str
    nonce: str
    issued_at: datetime


@dataclass(frozen=True)
class SkillMeta:
    name: str
    version: int
    minted_from: str
    exercised: bool
    exercised_at: str | None
    exercised_by: str | None
    exercised_hash: str | None
    citations: int
    # Procedure step 1b: an amend must carry forward the provenance of the research that
    # prompted it. Without this, folding a live-minted skill into an existing one erases the
    # evidence that live retrieval happened at all, and the only surviving record is a commit
    # message. It lives in meta.yaml because that is where a consumer looks.
    amendments: tuple = ()

    @classmethod
    def from_mapping(cls, data: dict) -> "SkillMeta":
        missing = {"name", "version", "minted_from", "exercised"} - data.keys()
        if missing:
            raise RegistryError(f"meta.yaml missing required fields: {sorted(missing)}")
        return cls(
            name=data["name"],
            version=int(data["version"]),
            minted_from=data["minted_from"],
            exercised=_strict_bool(data["exercised"], field="exercised"),
            exercised_at=data.get("exercised_at"),
            exercised_by=data.get("exercised_by"),
            exercised_hash=data.get("exercised_hash"),
            amendments=tuple(
                tuple(sorted(a.items())) for a in (data.get("amendments") or [])
            ),
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
            "exercised_hash": self.exercised_hash,
            "citations": self.citations,
            "amendments": [dict(a) for a in self.amendments],
        }


LEDGER_NAME = "version-ledger.jsonl"


def check_version_injectivity(entries: list[dict]) -> None:
    """`version` must identify exactly one content, and one content exactly one version.

    Both directions, because both are ambiguous in the same way. Two contents sharing a
    version means a record naming that version cannot say which content it meant. Two
    versions sharing a content means two records naming different versions point at
    identical bytes, and nothing downstream can tell whether the difference was meaningful.

    This exists as a check rather than as a rule because the rule was written down twice,
    argued to a sharper form, agreed explicitly, and then recurred three times in four hours
    while two reviewers were watching for it. A rule that survives that is a missing check.
    """
    by_version: dict[tuple[str, int], set[str]] = {}
    by_hash: dict[tuple[str, str], set[int]] = {}
    for e in entries:
        by_version.setdefault((e["name"], e["version"]), set()).add(e["content_hash"])
        by_hash.setdefault((e["name"], e["content_hash"]), set()).add(e["version"])

    for (name, version), hashes in sorted(by_version.items()):
        if len(hashes) > 1:
            raise VersionAmbiguityError(
                f"skill {name!r} version {version} names {len(hashes)} different contents "
                f"({sorted(h[:12] for h in hashes)}); a version must identify one content"
            )
    for (name, content_hash), versions in sorted(by_hash.items()):
        if len(versions) > 1:
            raise VersionAmbiguityError(
                f"skill {name!r} content {content_hash[:12]} carries versions "
                f"{sorted(versions)}; identical content must not carry two versions, or a "
                f"record naming one of them says nothing the other does not"
            )


class Registry:
    """Git-backed skill packs on disk. TrueForge consumes the same directory as a skill source."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        # Finding 7. One nonce per skill meant a second begin_exercise silently
        # invalidated the first gate's pass. Tickets coexist; each is consumed once.
        self._outstanding: dict[str, set[str]] = {}
        self._lock = threading.RLock()

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
        """Resolve a skill directory, refusing any name that escapes the registry root.

        Finding 5. Only `mint` validated the name, so every read path accepted traversal.
        Validation belongs here because this is the single place a name becomes a path.
        """
        if not NAME_PATTERN.match(name) or name in RESERVED_NAMES:
            raise RegistryError(f"invalid skill name {name!r}; expected kebab-case")
        candidate = (self.root / name).resolve()
        if candidate.parent != self.root.resolve():
            raise RegistryError(f"skill name {name!r} escapes the registry root")
        return candidate

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
                f"skill {name!r} declares verifier {parts[0]!r}; only "
                f"{sorted(ALLOWED_VERIFIERS)} may be invoked, because an allowlist naming "
                f"an interpreter does not constrain what runs"
            )
        for arg in parts[1:]:
            if not MAKE_ARG.match(arg):
                raise RegistryError(
                    f"skill {name!r} declares make argument {arg!r}; only bare target "
                    f"names and VAR=VALUE assignments are permitted"
                )
        return parts

    def is_trusted(self, name: str) -> bool:
        return self.load_meta(name).exercised

    def require_trusted(self, name: str) -> SkillMeta:
        """Gate on use. This is what stops a built-never-run skill from performing work."""
        meta = self.load_meta(name)
        if not meta.exercised:
            raise UntrustedSkillError(
                f"skill {name!r} has not passed the exercise gate and must not be used "
                f"for work; run `make exercise` against it first"
            )
        current = self.content_hash(name)
        if current != meta.exercised_hash:
            # The trust flag says a run passed, but not for these files. Recording only
            # that something passed, without recording what, let an edit keep the flag.
            raise UntrustedSkillError(
                f"skill {name!r} is marked exercised, but its files have changed since "
                f"that run; the trusted content is not what would execute. Re-exercise it"
            )
        return meta

    # ---- the single writer of the trust fields --------------------------------

    def content_hash(self, name: str) -> str:
        """Hash of everything the gate relies on, not only SKILL.md.

        Finding: hashing the body alone left verify.py outside the binding, so the file
        that decides whether a skill passes could be swapped without invalidating the
        ticket or the recorded trust. Every file in the skill directory except meta.yaml
        is covered, in sorted order so the digest is stable.
        """
        skill_dir = self.path_for(name)
        digest = hashlib.sha256()
        if skill_dir.is_dir():
            for path in sorted(skill_dir.iterdir()):
                if path.name == "meta.yaml" or not path.is_file():
                    continue
                digest.update(path.name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
        return digest.hexdigest()

    def begin_exercise(self, name: str) -> ExerciseTicket:
        """Issue a single-use ticket bound to the skill state observed right now."""
        meta = self.load_meta(name)
        ticket = ExerciseTicket(
            skill=name,
            version=meta.version,
            content_hash=self.content_hash(name),
            nonce=secrets.token_hex(16),
            issued_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._outstanding.setdefault(name, set()).add(ticket.nonce)
        return ticket

    def mark_exercised(
        self, ticket: ExerciseTicket, *, returncode: int, command: str
    ) -> SkillMeta:
        """The ONLY code path that sets `exercised` to true. Nothing else may flip it.

        Requires a ticket this registry issued and has not yet consumed, a zero exit status,
        and a skill whose version and content still match what the ticket saw.
        """
        name = ticket.skill
        with self._lock:
            if ticket.nonce not in self._outstanding.get(name, set()):
                raise RegistryError(
                    f"refusing to mark {name!r} exercised: ticket is unknown or already "
                    f"consumed"
                )
            self._outstanding[name].discard(ticket.nonce)

            if returncode != 0:
                raise RegistryError(
                    f"refusing to mark {name!r} exercised: run exited {returncode}"
                )

            meta = self.load_meta(name)
            if (
                meta.version != ticket.version
                or self.content_hash(name) != ticket.content_hash
            ):
                # The skill was re-minted while the run was in flight, so this pass is
                # evidence about content that is no longer on disk.
                raise RegistryError(
                    f"refusing to mark {name!r} exercised: skill changed during the run "
                    f"(ticket saw v{ticket.version}, disk has v{meta.version}); "
                    f"re-exercise it"
                )

            updated = replace(
                meta,
                exercised=True,
                exercised_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                exercised_by=command,
                exercised_hash=ticket.content_hash,
            )
            self._record_version(name, updated.version, ticket.content_hash)
            self._write_meta(name, updated)
            return updated

    def reset_trust(self, name: str) -> SkillMeta:
        """Re-minting revokes trust. Same single writer, so the three fields cannot drift."""
        meta = self.load_meta(name)
        updated = replace(
            meta,
            exercised=False,
            exercised_at=None,
            exercised_by=None,
            exercised_hash=None,
        )
        self._write_meta(name, updated)
        return updated

    # ---- minting --------------------------------------------------------------

    def mint(
        self,
        name: str,
        digest: Digest,
        skill_body: str,
        extra_files: dict[str, str] | None = None,
        minted_from: str = "research",
        amendment: dict | None = None,
    ) -> SkillMeta:
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
        previous_content = ""
        carried_amendments: tuple = ()
        if (skill_dir / "meta.yaml").is_file():
            existing = self.load_meta(name)
            previous_version = existing.version
            previous_content = self.content_hash(name)
            # Amendment history accumulates. A later amend must not erase an earlier one,
            # which is the same erasure step 1b exists to prevent.
            carried_amendments = existing.amendments

        # Finding 3. Revoke trust BEFORE touching content, so a crash mid-write can only
        # leave new content marked untrusted, never new content under old passing evidence.
        if previous_version:
            self._write_meta(
                name,
                replace(
                    self.load_meta(name),
                    exercised=False,
                    exercised_at=None,
                    exercised_by=None,
                    exercised_hash=None,
                ),
            )
            with self._lock:
                self._outstanding.pop(name, None)

        (skill_dir / "SKILL.md").write_text(skill_body, encoding="utf-8")
        (skill_dir / "citations.md").write_text(
            "# Citations\n\n"
            "Every method rule this skill encodes traces to a source here.\n\n"
            + "\n".join(c.to_markdown() for c in digest.grounded_citations()),
            encoding="utf-8",
        )
        # Files a previous version wrote that this one does not are removed, so a stale
        # verify.py from an earlier mint cannot be what a later version is judged by.
        written = {"SKILL.md", "citations.md", "meta.yaml"} | set((extra_files or {}))
        for existing in skill_dir.iterdir():
            if existing.is_file() and existing.name not in written:
                existing.unlink()

        for filename, content in (extra_files or {}).items():
            if "/" in filename or filename.startswith("."):
                raise RegistryError(f"invalid skill file name {filename!r}")
            (skill_dir / filename).write_text(content, encoding="utf-8")

        # A re-mint that produces identical content is not a new version of the skill.
        # Bumping anyway would put two version numbers on one body of content, which makes
        # a record naming either of them say nothing the other does not. Trust is still
        # revoked above, because a re-mint means the skill has to re-earn it regardless.
        unchanged = previous_content and self.content_hash(name) == previous_content
        meta = SkillMeta(
            name=name,
            version=previous_version if unchanged else previous_version + 1,
            minted_from=minted_from,
            exercised=False,
            exercised_at=None,
            exercised_by=None,
            exercised_hash=None,
            citations=len(digest.grounded_citations()),
            amendments=carried_amendments + (
                (tuple(sorted(amendment.items())),) if amendment else ()
            ),
        )
        self._write_meta(name, meta)
        return meta

    # ---- version ledger --------------------------------------------------------

    def ledger_path(self) -> Path:
        return self.root / LEDGER_NAME

    def read_ledger(self) -> list[dict]:
        path = self.ledger_path()
        if not path.is_file():
            return []
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _record_version(self, name: str, version: int, content_hash: str) -> None:
        """Append to the ledger, refusing anything that makes a version ambiguous.

        Checked BEFORE the trust record is written, so a violation leaves the skill
        untrusted rather than trusted under an ambiguous version.
        """
        entries = self.read_ledger()
        entry = {"name": name, "version": version, "content_hash": content_hash}
        if entry in entries:
            return          # idempotent: re-exercising identical content is not a conflict
        check_version_injectivity(entries + [entry])
        with self.ledger_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

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
