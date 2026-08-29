"""Retrieval over the skill registry: one lookup, ranked candidates, scores attached.

This is the step the mint/amend/skip procedure needs and did not have. Nothing consulted the
library before minting, so a gap that an existing skill already answered produced a new skill
anyway, and two skills came to hold the same rule from two papers.

Three parts, deliberately separable.

**A structured signature per skill**, declared rather than inferred. Task type, inputs,
outputs, provenance. A signature parsed out of prose is a guess about what a skill is for,
and a guess is what retrieval is supposed to replace.

**An embedding**, behind a protocol. The shipped implementation is deterministic, stdlib
only, and needs no model, no download and no network. That is a deliberate choice rather than
a limitation to apologise for: this repository's strongest property is that it clones and runs
with no credentials, and Q1's own acceptance test is that a clean clone returns scored
candidates. A hosted embedding model would trade that for accuracy nobody can check offline.
The protocol is here so a real model can be substituted the way the research executor was,
without touching the caller.

**A ranked lookup** returning every candidate with its score and the components the score came
from, because a ranking whose reasoning is invisible cannot inform a decision record, and Q2
requires the scores that informed a choice to be written down.

The version ledger is the state history for this registry. It is read here, not duplicated.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml

TOKEN = re.compile(r"[a-z0-9]+")

# Words that carry no discriminating signal in this corpus. Kept short and explicit: a long
# hand-tuned stop list is a way of fitting the retriever to the four skills that exist today.
STOP = frozenset("""
a an and are as at be by for from in into is it its of on or that the this to with
skill skills rule rules use used using when where which while
""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


@dataclass(frozen=True)
class SkillSignature:
    """What a skill is for, declared by the skill rather than guessed from its prose."""

    name: str
    version: int
    task_type: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    provenance: str
    citations: int
    exercised: bool
    text: str = ""          # the searchable body: description, applicability, rules

    def as_document(self) -> str:
        """The body text retrieval matches against. Signature fields are NOT included.

        An earlier version repeated the declared signature into this string, which meant the
        `body` component of a score silently contained the `signature` component it is
        reported beside. Two numbers that look independent and are not is worse than one
        number, because a reader decomposes the score and draws a conclusion the arithmetic
        does not support. The signature is scored separately and weighted there.
        """
        return self.text

    def declared_text(self) -> str:
        return " ".join([self.task_type, *self.inputs, *self.outputs])


@runtime_checkable
class Embedder(Protocol):
    """`fit(documents)` then `embed(text) -> vector`. Substitute a real model here."""

    def fit(self, documents: list[str]) -> None: ...
    def embed(self, text: str) -> dict[str, float]: ...


class TfidfEmbedder:
    """Deterministic sparse TF-IDF. No model, no download, no network, no randomness.

    Chosen so that `make retrieve` works on a clean clone with nothing installed beyond the
    repository's one dependency. Two identical inputs always produce identical scores, which
    matters because Q2 records these scores as the evidence for a decision, and evidence that
    changes between runs is not evidence.
    """

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._fitted = False

    def fit(self, documents: list[str]) -> None:
        n = len(documents)
        seen: Counter[str] = Counter()
        for doc in documents:
            seen.update(set(tokenize(doc)))
        # smoothed idf, so a term in every document scores near zero rather than exactly zero
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in seen.items()}
        self._fitted = True

    def embed(self, text: str) -> dict[str, float]:
        if not self._fitted:
            raise RuntimeError("embedder used before fit(); call fit on the corpus first")
        counts = Counter(tokenize(text))
        if not counts:
            return {}
        longest = max(counts.values())
        vec = {
            # A term absent from the corpus carries no evidence about which skill matches.
            # Defaulting it to 1.0 gave it more weight than terms that actually appear, so a
            # query full of unknown words drowned out its one real signal.
            t: (0.5 + 0.5 * c / longest) * self._idf.get(t, 0.0)
            for t, c in counts.items()
        }
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm else {}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Dot product. Correct as cosine ONLY because TfidfEmbedder returns unit vectors.

    Stated because it is an assumption a substituted embedder could silently break: a model
    returning unnormalised vectors would make every score wrong in a way nothing here checks.
    """
    if not a or not b:
        return 0.0
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    return sum(v * larger.get(t, 0.0) for t, v in smaller.items())


@dataclass
class Candidate:
    """A ranked result, carrying why it ranked where it did.

    `score` is what a caller sorts on. `components` is what a decision record quotes, because
    Q2 requires the scores that informed a choice to be written down, and one number with no
    decomposition explains nothing later.
    """

    signature: SkillSignature
    score: float
    components: dict[str, float] = field(default_factory=dict)
    matched_terms: tuple[str, ...] = ()

    def as_record(self) -> dict:
        return {
            "skill": self.signature.name,
            "version": self.signature.version,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "matched_terms": list(self.matched_terms),
            "exercised": self.signature.exercised,
            "provenance": self.signature.provenance,
        }


class SkillIndex:
    """One lookup over the registry. Built from what the registry already records."""

    def __init__(self, registry_root: Path | str, embedder: Embedder | None = None) -> None:
        self.root = Path(registry_root)
        self.embedder = embedder or TfidfEmbedder()
        self.signatures: list[SkillSignature] = []
        self._vectors: dict[str, dict[str, float]] = {}

    # ---- building -------------------------------------------------------------

    def _read_signature(self, skill_dir: Path) -> SkillSignature | None:
        meta_path = skill_dir / "meta.yaml"
        skill_path = skill_dir / "SKILL.md"
        if not meta_path.is_file() or not skill_path.is_file():
            return None
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        body = skill_path.read_text(encoding="utf-8")

        declared = meta.get("signature") or {}
        return SkillSignature(
            name=meta.get("name", skill_dir.name),
            version=int(meta.get("version", 0)),
            task_type=declared.get("task_type", ""),
            inputs=tuple(declared.get("inputs", ())),
            outputs=tuple(declared.get("outputs", ())),
            provenance=meta.get("minted_from", "unknown"),
            citations=int(meta.get("citations", 0)),
            exercised=bool(meta.get("exercised", False)),
            text=self._searchable(body),
        )

    @staticmethod
    def _searchable(body: str) -> str:
        """Description, applicability and rules. Not Verification, which is machinery."""
        keep = []
        m = re.search(r"^description:\s*(.+)$", body, re.MULTILINE)
        if m:
            keep.append(m.group(1))
        for header in ("When this applies", "Method", "Constraints"):
            sec = re.search(rf"^## {header}\s*$(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
            if sec:
                keep.append(sec.group(1))
        return " ".join(keep)

    def unsigned(self) -> list[str]:
        """Skills declaring no signature. They still match on body text, but they cannot
        match on the axis that is weighted highest, so a caller should know they are there
        rather than wonder why they never rank."""
        return [s.name for s in self.signatures if not s.task_type]

    def build(self) -> "SkillIndex":
        self.signatures = []
        if self.root.is_dir():
            for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
                if d.name.startswith("_"):
                    continue
                sig = self._read_signature(d)
                if sig:
                    self.signatures.append(sig)
        names = [s.name for s in self.signatures]
        if len(set(names)) != len(names):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(
                f"registry has duplicate skill names {dupes}; vectors are keyed by name, so "
                f"one would silently alias the other and both would score as whichever was "
                f"indexed last"
            )
        docs = [s.as_document() for s in self.signatures]
        self.embedder.fit(docs or [""])
        self._vectors = {
            s.name: self.embedder.embed(d) for s, d in zip(self.signatures, docs)
        }
        return self

    # ---- the version ledger is the state history; read it, do not rebuild it ----

    def ledger(self) -> list[dict]:
        path = self.root / "version-ledger.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # ---- lookup ---------------------------------------------------------------

    def search(self, task_description: str, limit: int | None = None,
               emit: bool = True) -> list[Candidate]:
        """Rank every skill against a task description. Returns all of them, scored.

        Every candidate is returned rather than only those above a threshold. A caller
        deciding between use-existing, amend, mint and raw-tool needs to see that the best
        score was poor, and a filtered list hides exactly that.
        """
        query = self.embedder.embed(task_description)
        query_terms = set(query)

        out = []
        for sig in self.signatures:
            vec = self._vectors.get(sig.name, {})
            body = cosine(query, vec)
            declared = self.embedder.embed(sig.declared_text())
            signature_match = cosine(query, declared)
            # Trust is not relevance, so it is a separate component rather than folded into
            # the score. An untrusted skill can still be the right skill to amend.
            components = {
                "body": body,
                "signature": signature_match,
                "trust": 1.0 if sig.exercised else 0.0,
            }
            score = 0.6 * body + 0.4 * signature_match
            overlap = tuple(sorted(query_terms & set(vec))[:8])
            out.append(Candidate(sig, score, components, overlap))

        out.sort(key=lambda c: (-c.score, c.signature.name))
        ranked = out[:limit] if limit else out

        # E3. One consultation event per candidate scored, not one per lookup: the dashboard
        # asks how often a rule was consulted and at what score, and a single event per
        # lookup could not answer either. Emission is best effort, because a retrieval that
        # fails because a log is unwritable would be a worse failure than a missing event.
        if emit:
            try:
                from orchestrator import events as _events

                for rank, c in enumerate(ranked, start=1):
                    _events.append(
                        _events.CONSULTATION,
                        skill=c.signature.name,
                        payload={
                            "task": task_description[:200],
                            "score": round(c.score, 4),
                            "rank": rank,
                            "components": {k: round(v, 4) for k, v in c.components.items()},
                            "source": "live",
                        },
                    )
            except Exception:
                pass

        return ranked
