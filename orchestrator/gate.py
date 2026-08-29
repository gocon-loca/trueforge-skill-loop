"""The exercise gate: the one place a skill can earn trust.

A minted skill is untrusted until it has completed one successful run. The gate runs the
skill's verification command against the deterministic offline path, and only a passing
run produces the evidence the registry will accept.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.registry import Registry, RegistryError, SkillMeta

DEFAULT_EXERCISE_COMMAND = ("make", "exercise")


@dataclass(frozen=True)
class ExerciseResult:
    skill: str
    command: str
    passed: bool
    returncode: int
    stdout: str
    stderr: str
    meta: SkillMeta | None = None

    def summary(self) -> str:
        verdict = "passed" if self.passed else "FAILED"
        return f"exercise {verdict}: {self.skill} via `{self.command}` (rc={self.returncode})"


class ExerciseGate:
    def __init__(
        self,
        registry: Registry,
        workdir: Path | str,
        command: tuple[str, ...] | None = None,
        timeout: int = 300,
    ) -> None:
        """`command=None` means each skill is verified by the command it declares in its
        own SKILL.md. Passing an explicit command overrides that, which is for tests and
        for callers that deliberately verify every skill the same way."""
        self.registry = registry
        self.workdir = Path(workdir)
        self.command = tuple(command) if command is not None else None
        self.timeout = timeout

    def exercise(self, name: str) -> ExerciseResult:
        """Run the offline verification for `name`. Trust is recorded only on a pass."""
        # Refuse before running anything. Exercising a skill that is not in the registry
        # would burn a real command run and then fail at the write, which reads as a gate
        # failure when it is actually a missing or misspelled skill.
        if not (self.registry.path_for(name) / "meta.yaml").is_file():
            return ExerciseResult(
                skill=name,
                command=shlex.join(self.command) if self.command else "(undetermined)",
                passed=False,
                returncode=127,
                stdout="",
                stderr=f"no skill named {name!r} in {self.registry.root}; nothing to exercise",
            )

        # A skill with no declared, allowlisted verification cannot be exercised, and so
        # cannot become trusted. That is a gate failure, not an exception to the gate.
        if self.command is not None:
            command = self.command
        else:
            try:
                command = self.registry.read_verification_command(name)
            except RegistryError as exc:
                return ExerciseResult(
                    skill=name,
                    command="(undeclared)",
                    passed=False,
                    returncode=126,
                    stdout="",
                    stderr=str(exc),
                )

        printable = shlex.join(command)

        # Bind this run to the skill state as it is right now. A re-mint while the command
        # is in flight invalidates the ticket rather than inheriting its trust.
        try:
            ticket = self.registry.begin_exercise(name)
        except RegistryError as exc:
            return ExerciseResult(
                skill=name, command=printable, passed=False, returncode=126,
                stdout="", stderr=str(exc),
            )

        try:
            completed = subprocess.run(
                command,
                cwd=str(self.workdir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ExerciseResult(
                skill=name,
                command=printable,
                passed=False,
                returncode=124,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr=f"exercise timed out after {self.timeout}s",
            )
        except OSError as exc:
            # Finding 9. A missing or non-executable verifier used to propagate and abort
            # the caller. An unlaunchable command is a failed gate, not a crash.
            return ExerciseResult(
                skill=name,
                command=printable,
                passed=False,
                returncode=127,
                stdout="",
                stderr=f"could not launch verification command: {exc}",
            )

        passed = completed.returncode == 0
        meta = None
        if passed:
            # The run happened here, so the report is made here. The registry decides
            # whether to honour it, against the ticket it issued before the run.
            try:
                meta = self.registry.mark_exercised(
                    ticket, returncode=completed.returncode, command=printable
                )
            except RegistryError as exc:
                return ExerciseResult(
                    skill=name, command=printable, passed=False,
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=f"run passed but trust was refused: {exc}",
                )
        return ExerciseResult(
            skill=name,
            command=printable,
            passed=passed,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            meta=meta,
        )
