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

from orchestrator.registry import ExerciseEvidence, Registry, SkillMeta

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
        command: tuple[str, ...] = DEFAULT_EXERCISE_COMMAND,
        timeout: int = 300,
    ) -> None:
        self.registry = registry
        self.workdir = Path(workdir)
        self.command = tuple(command)
        self.timeout = timeout

    def exercise(self, name: str) -> ExerciseResult:
        """Run the offline verification for `name`. Trust is recorded only on a pass."""
        printable = shlex.join(self.command)

        # Refuse before running anything. Exercising a skill that is not in the registry
        # would burn a real command run and then fail at the write, which reads as a gate
        # failure when it is actually a missing or misspelled skill.
        if not (self.registry.path_for(name) / "meta.yaml").is_file():
            return ExerciseResult(
                skill=name,
                command=printable,
                passed=False,
                returncode=127,
                stdout="",
                stderr=f"no skill named {name!r} in {self.registry.root}; nothing to exercise",
            )

        try:
            completed = subprocess.run(
                self.command,
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
                stdout=exc.stdout or "",
                stderr=f"exercise timed out after {self.timeout}s",
            )

        passed = completed.returncode == 0
        meta = None
        if passed:
            # The run happened here, so the evidence is produced here. The registry records
            # it; it does not decide it.
            meta = self.registry.mark_exercised(
                name, ExerciseEvidence.now(printable, passed=True)
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
